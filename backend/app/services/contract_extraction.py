"""Parse a contract's Exhibit B / fee schedule into structured ContractTask rows.

Two strategies, tried in order:
1. LLM extraction over the full contract text (general — handles any consultant's format).
2. Heuristic table parser over pdfplumber-extracted tables (offline fallback, tuned to the
   common 'Task | Location | Category Code | Task Description | Fee' schedule layout).

Whichever produces a non-empty task list wins; if the LLM path raises (no API key, bad
JSON, rate limit) we fall back to the heuristic silently.
"""

import re

from app.schemas import ContractExtractionResult, ContractTaskExtract
from app.services.llm_client import call_json_llm, has_valid_api_key
from app.services.parsing_utils import clean_cell, parse_currency

CONTRACT_SYSTEM_PROMPT = """You are a construction/consulting contract compensation specialist. You extract the \
Schedule of Values / Exhibit B (Compensation) fee schedule from a consultant contract or addendum so it can be \
tracked against monthly invoices.

CRITICAL RULES:
1. Extract every task/line item in the fee schedule, including from every addendum present in the document. \
Use the task number exactly as printed (e.g. "11", "22").
2. fee_type is "lump_sum" if the task is a fixed not-to-exceed lump sum, or "tm" (time & materials / unit rate) if \
billed per day/month/hour against a unit rate.
3. unit_type is "day", "month", "hour", "lump_sum", or "other" — infer from language like "daily rate of $X" \
(day), "monthly rate of $X" (month), "hourly rate" (hour).
4. unit_rate is the dollar unit rate if stated (e.g. "daily rate of $790" -> 790). Null if not a unit-rate task.
5. estimated_fee is the total budgeted/not-to-exceed dollar amount for that task.
6. cost_code is the accounting/category code shown for the task (e.g. "3100-0230"), if any.
7. If a task's notes say billing was superseded or moved to a different task number (e.g. "No further billing \
after Addendum 3. Bill to Task 22"), set is_active=false and superseded_by_task_number to that new task number. \
Otherwise is_active=true.
8. Do not invent tasks or dollar amounts that are not in the document. Return ONLY valid JSON, no markdown."""

CONTRACT_USER_TEMPLATE = """Extract the fee schedule from this contract. Return strict JSON matching this schema:

{{
  "label": string|null,               // e.g. "Addendum #3" or the contract title
  "not_to_exceed_total": number|null, // the overall agreement/contract not-to-exceed total, if stated
  "default_markup_pct": number|null,  // markup percentage on reimbursable expenses, if stated (e.g. 10 for 10%)
  "tasks": [
    {{
      "task_number": string,
      "cost_code": string|null,
      "description": string,
      "fee_type": "lump_sum"|"tm",
      "unit_type": "day"|"month"|"hour"|"lump_sum"|"other"|null,
      "unit_rate": number|null,
      "estimated_fee": number,
      "markup_pct": number|null,
      "is_active": boolean,
      "superseded_by_task_number": string|null,
      "notes": string|null
    }}
  ]
}}

CONTRACT TEXT:
---
{contract_text}
---"""


_UNIT_RATE_RE = re.compile(
    r"(daily|monthly|hourly)\s+rate\s+of\s*\$?([\d,]+(?:\.\d+)?)", re.IGNORECASE
)
_LUMP_SUM_RE = re.compile(r"lump\s*sum", re.IGNORECASE)
_SUPERSEDE_RE = re.compile(
    r"(?:no further billing[^.]*\.?\s*)?bill\s+to\s+task\s+(\d+)", re.IGNORECASE
)
_NO_FURTHER_BILLING_RE = re.compile(r"no further billing", re.IGNORECASE)
_MARKUP_RE = re.compile(r"markup\s+of\s*([\d.]+)\s*%", re.IGNORECASE)
_COST_CODE_RE = re.compile(r"\b\d{4}-\d{4}(?:\s*/\s*[A-Z0-9 \-]+[A-Z0-9])?\b")
_CURRENCY_LOOKING_RE = re.compile(r"^\(?\$?\s*-?[\d,]*\.?\d*\)?%?$")


def _looks_like_currency(cell: str) -> bool:
    """A cell that's plausibly a dollar amount — no letters, just digits/$/,/./()/-.

    Guards against parse_currency's aggressive digit-stripping misreading ordinary text
    (e.g. 'Task 1: Field Observation...' contains a bare '1' and would otherwise parse as $1).
    """
    return bool(cell) and bool(_CURRENCY_LOOKING_RE.match(cell))


def _infer_unit(description: str) -> tuple[str, str | None, float | None]:
    """Return (fee_type, unit_type, unit_rate) inferred from a task's free-text description."""
    match = _UNIT_RATE_RE.search(description)
    if match:
        unit_word, rate_str = match.groups()
        unit_type = {"daily": "day", "monthly": "month", "hourly": "hour"}[unit_word.lower()]
        return "tm", unit_type, parse_currency(rate_str)
    if _LUMP_SUM_RE.search(description):
        return "lump_sum", "lump_sum", None
    return "tm", None, None


def _infer_notes(description: str) -> tuple[bool, str | None, str | None]:
    """Return (is_active, superseded_by_task_number, notes) from supersede language."""
    supersede_match = _SUPERSEDE_RE.search(description)
    if supersede_match:
        return False, supersede_match.group(1), description
    if _NO_FURTHER_BILLING_RE.search(description):
        return False, None, description
    return True, None, None


_SKIP_TEXT_RE = re.compile(
    r"^(base|agreement|location|category code|task$|task description|consultant.s estimated fee.*)$",
    re.IGNORECASE,
)
_SECTION_BREAK_RE = re.compile(r"subtotal|not to exceed|regimen services\b|^\d+$", re.IGNORECASE)


def _flush_task(buf: dict) -> ContractTaskExtract | None:
    if not buf.get("task_number"):
        return None
    description = " ".join(buf["description_parts"]).strip()
    if not description:
        return None
    fee_type, unit_type, unit_rate = _infer_unit(description)
    is_active, superseded_by, notes = _infer_notes(description)
    return ContractTaskExtract(
        task_number=buf["task_number"],
        cost_code=buf.get("cost_code"),
        description=description,
        fee_type=fee_type,
        unit_type=unit_type,
        unit_rate=unit_rate,
        estimated_fee=buf.get("estimated_fee") or 0.0,
        is_active=is_active,
        superseded_by_task_number=superseded_by,
        notes=notes,
    )


def extract_contract_heuristic(raw_text: str, tables: list[list[list[str | None]]]) -> ContractExtractionResult:
    """Table-based fallback extraction — tuned to 'Task | Location | Category Code | Description | Fee' layouts.

    pdfplumber splits each logical task row into several physical rows wherever the PDF wraps a
    cell's text, and a bare task number can land on any one of them. So rather than requiring the
    task number in column 0 of a single row, this sweeps every row, accumulating description/cost
    code/fee fragments into a buffer for the current task until the next task-number row (or a
    section-break row like a subtotal) starts a new one.
    """
    tasks: list[ContractTaskExtract] = []
    seen_task_numbers: set[str] = set()
    buf: dict = {"task_number": None, "cost_code": None, "description_parts": [], "estimated_fee": None}

    for table in tables:
        if not table or len(table) < 2:
            continue
        header = [clean_cell(c).lower() for c in table[0]]
        if not any("task" in h for h in header) or not any("fee" in h for h in header):
            continue
        # Skip billing-sheet/invoice-shaped tables (e.g. a blank billing-sheet template printed
        # inside the contract itself) — they share the word "fee" but aren't the Exhibit B schedule.
        if any("previously billed" in h or "billed this period" in h for h in header):
            continue

        # Each matching table is a distinct page's fee-schedule table — flush any dangling task
        # before starting a fresh one so nothing bleeds across table/page boundaries.
        flushed = _flush_task(buf)
        if flushed and flushed.task_number not in seen_task_numbers:
            tasks.append(flushed)
            seen_task_numbers.add(flushed.task_number)
        buf = {"task_number": None, "cost_code": None, "description_parts": [], "estimated_fee": None}

        for row in table[1:]:
            cells = [clean_cell(c) for c in row]
            if not any(cells):
                continue
            joined = " ".join(cells)

            if re.search(r"subtotal|not to exceed|regimen services", joined, re.IGNORECASE):
                flushed = _flush_task(buf)
                if flushed and flushed.task_number not in seen_task_numbers:
                    tasks.append(flushed)
                    seen_task_numbers.add(flushed.task_number)
                buf = {"task_number": None, "cost_code": None, "description_parts": [], "estimated_fee": None}
                continue

            # The task number only ever appears in column 0 — a later column (e.g. "Location")
            # can also be a bare 1-3 digit number, so scanning every cell would misfire on it.
            new_task_number = cells[0] if re.fullmatch(r"\d{1,3}", cells[0]) else None

            if new_task_number and new_task_number != buf["task_number"] and buf["description_parts"]:
                flushed = _flush_task(buf)
                if flushed and flushed.task_number not in seen_task_numbers:
                    tasks.append(flushed)
                    seen_task_numbers.add(flushed.task_number)
                buf = {"task_number": None, "cost_code": None, "description_parts": [], "estimated_fee": None}

            if new_task_number:
                buf["task_number"] = new_task_number

            cost_code_match = _COST_CODE_RE.search(joined)
            if cost_code_match and not buf["cost_code"]:
                buf["cost_code"] = cost_code_match.group(0)

            for cell in cells:
                if not cell or cell == new_task_number:
                    continue
                if _SKIP_TEXT_RE.match(cell) or _COST_CODE_RE.fullmatch(cell) or re.fullmatch(r"\d{1,3}", cell):
                    continue
                if _looks_like_currency(cell):
                    fee_val = parse_currency(cell)
                    if fee_val is not None:
                        if fee_val != 0.0:
                            # Accumulate rather than overwrite: a task number sometimes covers two
                            # cost components split across rows (e.g. 'maintenance' + 'deployment'
                            # sub-items both nominally under the same task).
                            buf["estimated_fee"] = (buf["estimated_fee"] or 0.0) + fee_val
                        continue
                buf["description_parts"].append(cell)

    flushed = _flush_task(buf)
    if flushed and flushed.task_number not in seen_task_numbers:
        tasks.append(flushed)

    tasks.sort(key=lambda t: int(t.task_number) if t.task_number.isdigit() else 0)

    not_to_exceed_matches = list(re.finditer(r"^AGREEMENT NOT TO EXCEED\D{0,20}\$?\s*([\d,]+(?:\.\d+)?)", raw_text, re.IGNORECASE | re.MULTILINE))
    not_to_exceed_total = parse_currency(not_to_exceed_matches[-1].group(1)) if not_to_exceed_matches else None
    markup_match = _MARKUP_RE.search(raw_text)
    default_markup_pct = float(markup_match.group(1)) if markup_match else None

    return ContractExtractionResult(
        label=None,
        not_to_exceed_total=not_to_exceed_total,
        default_markup_pct=default_markup_pct,
        tasks=tasks,
    )


def extract_contract_tasks(
    raw_text: str, tables: list[list[list[str | None]]]
) -> tuple[ContractExtractionResult, str]:
    """Returns (result, method) where method is 'llm' or 'heuristic'."""
    if has_valid_api_key():
        try:
            result = call_json_llm(
                CONTRACT_SYSTEM_PROMPT,
                CONTRACT_USER_TEMPLATE.format(contract_text=raw_text),
                ContractExtractionResult,
            )
            if result.tasks:
                return result, "llm"
        except Exception:
            pass

    return extract_contract_heuristic(raw_text, tables), "heuristic"
