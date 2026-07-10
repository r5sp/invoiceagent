"""Parse an uploaded invoice PDF into structured line items.

Two invoice shapes show up in practice:

- "task_correlated": the consultant already submits a billing-sheet-style table with
  Cost Code / Task Description / Estimated Fee / Previously Billed / Billed This Period /
  Total Billed to Date columns (common when the contract requires it, e.g. Exhibit B says
  "Owner hereby provides Consultant the following form of billing sheet..."). We parse this
  directly with a table heuristic — the numbers are already computed, so we trust them and
  just check them (see review_engine).

- "tm_receipt": a time & materials invoice that is NOT pre-correlated to contract tasks —
  a flat list of dated line items (the CTS "restaurant receipt" case, or task-sectioned
  invoices like '022A'/'022B'). This requires an LLM to read free-form line items and
  section headers.
"""

import re

from app.schemas import InvoiceExtractionResult, TaskCorrelationExtract
from app.services.llm_client import call_json_llm, has_valid_api_key
from app.services.parsing_utils import clean_cell, parse_currency, parse_date, parse_period_range

INVOICE_SYSTEM_PROMPT = """You are a construction/consulting invoice auditor. You extract every billable line item \
from a time & materials (T&M) invoice so it can be checked against a contract's fee schedule.

CRITICAL RULES:
1. Extract EVERY line item — every dated entry, every person, every task section. Do not summarize or merge rows.
2. If the invoice is organized into sections labeled by task number (e.g. "TASK 22 - ..."), set raw_task_number \
to that task's number for every line item under that section.
3. If a line item states a person's name performing work, set person_name.
4. quantity is the billed quantity (hours, days, or months) and unit_rate is the dollar rate per unit, when stated. \
amount is the extended dollar amount for that line (quantity * unit_rate, or as stated).
5. category is "reimbursable" for pass-through expenses/materials (mileage, lab fees passed through, equipment \
rental billed at cost), "labor" for personnel/day-rate/hourly work, "expense" for anything else billed as a flat fee.
6. work_date should be an ISO date (YYYY-MM-DD) if a specific date is given for the line item. If only a date \
range is given for the whole invoice (e.g. "April-June 2026"), leave work_date null for that line.
7. Extract invoice_number, invoice_date, period_start, period_end (ISO dates), subtotal, total_amount, and if \
stated, reimbursable_amount and reimbursable_markup_billed (the % markup actually charged, as billed — e.g. 10 \
for 10%, from language like 'plus 10% markup').
8. Do not invent numbers. Return ONLY valid JSON, no markdown."""

INVOICE_USER_TEMPLATE = """Extract every line item from this invoice. Return strict JSON matching this schema:

{{
  "invoice_number": string|null,
  "invoice_date": string|null,       // ISO date
  "period_start": string|null,       // ISO date
  "period_end": string|null,         // ISO date
  "subtotal": number|null,
  "total_amount": number|null,
  "reimbursable_amount": number|null,
  "reimbursable_markup_billed": number|null,
  "line_items": [
    {{
      "raw_task_number": string|null,
      "raw_cost_code": string|null,
      "description": string,
      "work_date": string|null,
      "person_name": string|null,
      "quantity": number|null,
      "unit_type": "day"|"month"|"hour"|"lump_sum"|"other"|null,
      "unit_rate": number|null,
      "amount": number,
      "category": "labor"|"reimbursable"|"expense"
    }}
  ]
}}

INVOICE TEXT:
---
{invoice_text}
---"""

_HEADER_MARKERS = {
    "previously billed": "previously_billed",
    "billed this period": "billed_this_period",
    "current billed": "billed_this_period",
    "total billed to date": "total_billed_to_date",
    "cost code": "cost_code",
    "task description": "description",
    "description": "description",
    "estimated fee": "estimated_fee",
    "fee": "estimated_fee",
    "item no": "item_no",
    "balance remaining": "balance_remaining",
}

_INVOICE_NUMBER_RE = re.compile(r"Invoice\s*(?:No\.?|number)\.?:?\s*([A-Za-z0-9\-]+)", re.IGNORECASE)
_INVOICE_DATE_RE = re.compile(r"Invoice\s*Date:?\s*([A-Za-z0-9,/ ]+?)(?:\n|$)", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"^\s*Date\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})\s*$", re.IGNORECASE | re.MULTILINE)
_PERIOD_RE = re.compile(
    r"(?:Billing\s*Period|Period):?\s*([A-Za-z0-9,\-/ ]+?)(?:\n|$)", re.IGNORECASE
)
_SERVICES_THROUGH_RE = re.compile(
    r"Professional\s+Services\s+Through\s+([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", re.IGNORECASE
)
_TOTAL_RE = re.compile(r"TOTAL\s+INVOICE\s+AMOUNT\D{0,10}\$?\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_INVOICE_TOTAL_RE = re.compile(r"Invoice\s+total\D{0,10}\$?\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)

# A dollar/percent value column: digits with exactly two decimals, optional $, commas, or
# accounting-negative parens. Deliberately does NOT match task numbers ("T6A1"), cost codes
# ("2100-0450"), or bare integers ("Park 2") so they stay in the description.
_VALUE_TOKEN_RE = re.compile(r"^\(?\$?-?[\d,]+\.\d{2}\)?$")
# ACLA-style task numbers embedded in the description: T6A1, T10A2, T18A3, T19A3::
_TASK_NUM_RE = re.compile(r"^(T\d+[A-Za-z]?\d*)", re.IGNORECASE)
_COST_CODE_RE = re.compile(r"(\d{4}-\d{3,4})")
_CONTINUATION_STOP = ("total", "invoice", "thank", "page", "associate", "for", "job", "date", "project")


def _split_trailing_values(tokens: list[str]) -> tuple[str, list[float]]:
    """Split a reconstructed visual row into (description, [trailing numeric column values])."""
    n = len(tokens)
    while n > 0 and _VALUE_TOKEN_RE.match(tokens[n - 1]):
        n -= 1
    desc = " ".join(tokens[:n]).strip()
    values = [parse_currency(t) for t in tokens[n:]]
    return desc, [v for v in values if v is not None]


def _looks_like_task_row(desc: str) -> bool:
    return bool(_TASK_NUM_RE.match(desc)) or desc.strip().upper().startswith("REIMBURSABLE")


def detect_and_extract_acla_summary(
    word_rows: list[list[str]],
) -> list[TaskCorrelationExtract] | None:
    """Parse a borderless ACLA-style billing summary from coordinate-reconstructed rows.

    Handles the two layouts seen in practice, keyed off the trailing-value count:
    - 5 columns: Contract Amount | Percent Complete | Remaining | Prior Billed | Current Billed
    - 3 columns: Contract Amt | Total Billed | Current Billed
    Task number and cost code are pulled out of the description text (they are not their own
    columns), merging the wrapped continuation line that often carries the cost code.
    """
    parsed = [_split_trailing_values(r) for r in word_rows if r]

    # Which layout? Take the modal trailing-value count among task-numbered rows.
    counts: dict[int, int] = {}
    for desc, values in parsed:
        if _TASK_NUM_RE.match(desc) and len(values) in (3, 5):
            counts[len(values)] = counts.get(len(values), 0) + 1
    if not counts:
        return None
    ncols = max(counts, key=lambda k: counts[k])
    if counts[ncols] < 2:  # need a couple of real task rows to trust this is an ACLA summary
        return None

    rows: list[TaskCorrelationExtract] = []
    seen_task_numbers: set[str] = set()
    i = 0
    while i < len(parsed):
        desc, values = parsed[i]
        if not (_looks_like_task_row(desc) and len(values) == ncols):
            i += 1
            continue
        if desc.strip().lower().startswith("total"):
            i += 1
            continue

        # Merge wrapped continuation lines (they carry the rest of the description / cost code).
        merged = desc
        j = i + 1
        while j < len(parsed):
            next_desc, next_values = parsed[j]
            first = next_desc.split(" ", 1)[0].lower() if next_desc else ""
            if next_values or _looks_like_task_row(next_desc) or first.startswith(_CONTINUATION_STOP):
                break
            merged = f"{merged} {next_desc}".strip()
            j += 1

        task_match = _TASK_NUM_RE.match(merged)
        task_number = task_match.group(1).upper() if task_match else None
        cost_match = _COST_CODE_RE.search(merged)
        cost_code = cost_match.group(1) if cost_match else None

        if ncols == 5:
            contract, _pct, _remaining, prior, current = values
            total_billed = (prior or 0.0) + (current or 0.0)
        else:  # ncols == 3
            contract, total_billed, current = values
            prior = (total_billed or 0.0) - (current or 0.0)

        if task_number and task_number in seen_task_numbers:
            i = j
            continue
        if task_number:
            seen_task_numbers.add(task_number)

        rows.append(
            TaskCorrelationExtract(
                raw_task_number=task_number,
                raw_cost_code=cost_code,
                description=merged,
                previously_billed=prior,
                billed_this_period=current,
                total_billed_to_date=total_billed,
                estimated_fee=contract,
            )
        )
        i = j

    return rows or None


def _find_billing_sheet_table(
    tables: list[list[list[str | None]]],
) -> tuple[list[list[str]], dict[int, str]] | None:
    """Find a table whose header row matches the billing-sheet column layout."""
    for table in tables:
        if not table or len(table) < 2:
            continue
        header_cells = [clean_cell(c).lower() for c in table[0]]
        col_map: dict[int, str] = {}
        for idx, cell in enumerate(header_cells):
            if "%" in cell:
                continue  # e.g. "% Billed to Date" must never shadow a dollar-amount column
            for marker, field in _HEADER_MARKERS.items():
                if marker in cell:
                    col_map[idx] = field
                    break
        has_prior = "previously_billed" in col_map.values()
        has_current = "billed_this_period" in col_map.values()
        has_desc = "description" in col_map.values() or "cost_code" in col_map.values()
        if has_prior and has_current and has_desc:
            cleaned_table = [[clean_cell(c) for c in row] for row in table]
            return cleaned_table, col_map
    return None


def detect_and_extract_task_correlated(
    tables: list[list[list[str | None]]],
) -> list[TaskCorrelationExtract] | None:
    found = _find_billing_sheet_table(tables)
    if not found:
        return None
    table, col_map = found

    rows: list[TaskCorrelationExtract] = []
    for row in table[1:]:
        if len(row) <= max(col_map, default=-1):
            continue
        values = {field: row[idx] for idx, field in col_map.items()}
        description = values.get("description", "")
        if not description and not values.get("cost_code"):
            continue
        # Section header rows (e.g. "BASE REGIMEN SERVICES") have no numeric columns — skip.
        if parse_currency(values.get("estimated_fee")) is None and parse_currency(values.get("total_billed_to_date")) is None:
            continue

        rows.append(
            TaskCorrelationExtract(
                raw_task_number=values.get("item_no") or None,
                raw_cost_code=values.get("cost_code") or None,
                description=description or values.get("cost_code", ""),
                previously_billed=parse_currency(values.get("previously_billed")),
                billed_this_period=parse_currency(values.get("billed_this_period")),
                total_billed_to_date=parse_currency(values.get("total_billed_to_date")),
                estimated_fee=parse_currency(values.get("estimated_fee")),
            )
        )
    return rows or None


def extract_invoice_metadata_heuristic(raw_text: str) -> dict:
    invoice_number = None
    if m := _INVOICE_NUMBER_RE.search(raw_text):
        invoice_number = m.group(1).strip()
    invoice_date = None
    if m := _INVOICE_DATE_RE.search(raw_text):
        invoice_date = parse_date(m.group(1).strip())
    if invoice_date is None and (m := _DATE_LINE_RE.search(raw_text)):
        invoice_date = parse_date(m.group(1).strip())
    period_start, period_end = None, None
    if m := _PERIOD_RE.search(raw_text):
        period_start, period_end = parse_period_range(m.group(1).strip())
    if period_end is None and (m := _SERVICES_THROUGH_RE.search(raw_text)):
        period_end = parse_date(m.group(1).strip())
    total_amount = None
    if m := _TOTAL_RE.search(raw_text):
        total_amount = parse_currency(m.group(1))
    elif m := _INVOICE_TOTAL_RE.search(raw_text):
        total_amount = parse_currency(m.group(1))
    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "period_start": period_start,
        "period_end": period_end,
        "subtotal": None,
        "total_amount": total_amount,
        "reimbursable_amount": None,
        "reimbursable_markup_billed": None,
    }


def extract_invoice_tm_receipt_llm(raw_text: str) -> InvoiceExtractionResult:
    if not has_valid_api_key():
        raise RuntimeError(
            "This invoice isn't in the standard billing-sheet format, so it needs AI parsing — "
            "set OPENAI_API_KEY on the server to enable it."
        )
    return call_json_llm(
        INVOICE_SYSTEM_PROMPT,
        INVOICE_USER_TEMPLATE.format(invoice_text=raw_text),
        InvoiceExtractionResult,
    )


def extract_invoice(
    raw_text: str,
    tables: list[list[list[str | None]]],
    word_rows: list[list[str]] | None = None,
) -> tuple[str, list[TaskCorrelationExtract] | None, list, dict]:
    """Returns (format, task_rows_or_none, tm_line_items, metadata).

    Tries the cheapest parsers first, only falling back to the LLM for genuinely
    unstructured invoices:
      1. ruled billing-sheet table (pdfplumber tables) — e.g. Albion 021/022
      2. borderless coordinate-reconstructed summary — e.g. ACLA 10775/10776
      3. LLM line-item extraction — task-sectioned T&M / "restaurant receipt" (CTS)
    """
    task_rows = detect_and_extract_task_correlated(tables)
    if task_rows:
        metadata = extract_invoice_metadata_heuristic(raw_text)
        return "task_correlated", task_rows, [], metadata

    if word_rows:
        acla_rows = detect_and_extract_acla_summary(word_rows)
        if acla_rows:
            metadata = extract_invoice_metadata_heuristic(raw_text)
            return "task_correlated", acla_rows, [], metadata

    result = extract_invoice_tm_receipt_llm(raw_text)
    metadata = {
        "invoice_number": result.invoice_number,
        "invoice_date": parse_date(result.invoice_date),
        "period_start": parse_date(result.period_start),
        "period_end": parse_date(result.period_end),
        "subtotal": result.subtotal,
        "total_amount": result.total_amount,
        "reimbursable_amount": result.reimbursable_amount,
        "reimbursable_markup_billed": result.reimbursable_markup_billed,
    }
    return "tm_receipt", None, result.line_items, metadata
