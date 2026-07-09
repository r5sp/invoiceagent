"""Deterministic invoice review rules, per Joe's review procedures:

1.  Consultant is not overbilling a task vs. the contract value.               -> OVERBILLED
2.  Flag when a task exceeds the warning threshold (default 75%) billed.        -> THRESHOLD_WARNING
3.  Consultant is billing the unit rates specified in the contract.             -> RATE_MISMATCH
4.  Consultant is not billing for work outside their contracted tasks.         -> NOT_IN_CONTRACT
5.  Billed-to-date = prior billed + this period; prior billed on the invoice
    matches last month's billed-to-date.                                      -> PRIOR_BILLED_MISMATCH
6.  T&M line-item math (quantity * rate = amount) is correct.                   -> MATH_ERROR (line)
7.  Subtotal / recap math is correct.                                          -> MATH_ERROR (invoice/task)
8.  No one person billed >8 hrs/day or >40 hrs/week (absent overtime notes).    -> DAILY_HOURS / WEEKLY_HOURS
9.  Invoiced inspection dates match an uploaded daily/monthly report.          -> INSPECTION_DATE_MISMATCH
10. Cost codes match the contract's Exhibit B cost codes.                      -> COST_CODE_MISMATCH
11. Flag the most expensive invoice to date, or excessive hours vs. history.   -> MOST_EXPENSIVE
12. Reimbursable markup matches the contract rate.                            -> MARKUP_MISMATCH
"""

import json
import re
from collections import defaultdict
from datetime import date

from app.config import settings
from app.models import Contract, Invoice, Project
from app.schemas import BillingSummaryResponse, TaskSummaryRow

_OVERTIME_RE = re.compile(r"\bo\.?t\.?\b|overtime", re.IGNORECASE)
_INSPECTION_RE = re.compile(r"inspect|field observ|daily log|monitor", re.IGNORECASE)

AMOUNT_TOLERANCE = 1.00
RATE_TOLERANCE = 0.01
MARKUP_TOLERANCE_PCT = 0.5


def _chron_key(invoice: Invoice):
    return (invoice.period_start or invoice.invoice_date or invoice.uploaded_at.date(), invoice.id)


def latest_contract(project: Project) -> Contract | None:
    if not project.contracts:
        return None
    return max(project.contracts, key=lambda c: c.uploaded_at)


def _billed_this_period_for_task(invoice: Invoice, task_id: int) -> float:
    total = 0.0
    for item in invoice.line_items:
        if item.contract_task_id != task_id:
            continue
        total += item.billed_this_period if item.billed_this_period is not None else item.amount
    return total


def _stated_field_for_task(invoice: Invoice, task_id: int, field: str) -> float | None:
    for item in invoice.line_items:
        if item.contract_task_id == task_id and getattr(item, field) is not None:
            return getattr(item, field)
    return None


def build_task_ledger(project: Project) -> dict[int, dict]:
    """Per contract_task_id: {'baseline': float, 'entries': [(invoice, billed_this_period), ...]}.

    'baseline' seeds from the first uploaded invoice's stated 'previously billed' for that task —
    contracts are usually already in progress when Joe starts tracking them in this tool, so the
    first invoice's prior-billed figure is trusted as the pre-existing history rather than assumed
    to be zero. Continuity is only checked from the second tracked invoice onward.
    """
    invoices_sorted = sorted(project.invoices, key=_chron_key)
    contract = latest_contract(project)
    ledger: dict[int, dict] = {t.id: {"baseline": 0.0, "entries": []} for t in (contract.tasks if contract else [])}
    for invoice in invoices_sorted:
        task_ids = {item.contract_task_id for item in invoice.line_items if item.contract_task_id}
        for task_id in task_ids:
            entry = ledger.setdefault(task_id, {"baseline": 0.0, "entries": []})
            if not entry["entries"]:
                stated_prior = _stated_field_for_task(invoice, task_id, "previously_billed")
                if stated_prior is not None:
                    entry["baseline"] = stated_prior
            entry["entries"].append((invoice, _billed_this_period_for_task(invoice, task_id)))
    return ledger


def _cumulative_before(ledger_entry: dict, invoice_id: int) -> float:
    total = ledger_entry["baseline"]
    for inv, btp in ledger_entry["entries"]:
        if inv.id == invoice_id:
            break
        total += btp
    return total


def _is_seeding_invoice(ledger_entry: dict, invoice_id: int) -> bool:
    """True if this invoice is the first tracked entry for the task (its prior-billed seeded the baseline)."""
    return bool(ledger_entry["entries"]) and ledger_entry["entries"][0][0].id == invoice_id


def _week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return (iso[0], iso[1])


def review_invoice(project: Project, invoice: Invoice) -> list[dict]:
    """Returns a list of flag dicts: {contract_task_id, rule_code, severity, message}."""
    flags: list[dict] = []
    contract = latest_contract(project)
    tasks_by_id = {t.id: t for t in (contract.tasks if contract else [])}
    ledger = build_task_ledger(project)

    # --- Line-item level checks -------------------------------------------------
    hours_by_person_day: dict[tuple[str, date], float] = defaultdict(float)
    hours_has_ot: dict[tuple[str, date], bool] = defaultdict(bool)
    hours_by_person_week: dict[tuple[str, tuple[int, int]], float] = defaultdict(float)

    for item in invoice.line_items:
        task = tasks_by_id.get(item.contract_task_id) if item.contract_task_id else None

        if item.contract_task_id is None:
            flags.append(
                {
                    "contract_task_id": None,
                    "rule_code": "NOT_IN_CONTRACT",
                    "severity": "critical",
                    "message": f"Line item “{item.description}” (${item.amount:,.2f}) doesn't match any "
                    "task in the contract's fee schedule — confirm this work is authorized before paying it.",
                }
            )
        elif task and item.raw_cost_code and task.cost_code:
            if item.raw_cost_code.strip().split("/")[0].strip() != task.cost_code.strip().split("/")[0].strip():
                flags.append(
                    {
                        "contract_task_id": task.id,
                        "rule_code": "COST_CODE_MISMATCH",
                        "severity": "warning",
                        "message": f"Task {task.task_number}: invoice cost code '{item.raw_cost_code}' doesn't "
                        f"match the contract's cost code '{task.cost_code}'.",
                    }
                )

        if task and item.unit_rate is not None and task.unit_rate is not None:
            if abs(item.unit_rate - task.unit_rate) > RATE_TOLERANCE:
                flags.append(
                    {
                        "contract_task_id": task.id,
                        "rule_code": "RATE_MISMATCH",
                        "severity": "critical",
                        "message": f"Task {task.task_number}: billed at ${item.unit_rate:,.2f}/{task.unit_type or 'unit'} "
                        f"but the contract rate is ${task.unit_rate:,.2f}/{task.unit_type or 'unit'}.",
                    }
                )

        if item.quantity is not None and item.unit_rate is not None:
            expected = item.quantity * item.unit_rate
            if abs(expected - item.amount) > AMOUNT_TOLERANCE:
                flags.append(
                    {
                        "contract_task_id": item.contract_task_id,
                        "rule_code": "MATH_ERROR",
                        "severity": "warning",
                        "message": f"Line item “{item.description}”: {item.quantity} x "
                        f"${item.unit_rate:,.2f} = ${expected:,.2f}, but the invoice shows ${item.amount:,.2f}.",
                    }
                )

        if item.person_name and item.unit_type == "hour" and item.quantity and item.work_date:
            key_day = (item.person_name, item.work_date)
            hours_by_person_day[key_day] += item.quantity
            if _OVERTIME_RE.search(item.description):
                hours_has_ot[key_day] = True
            hours_by_person_week[(item.person_name, _week_key(item.work_date))] += item.quantity

    for (person, work_date), hours in hours_by_person_day.items():
        if hours > settings.max_hours_per_day and not hours_has_ot[(person, work_date)]:
            flags.append(
                {
                    "contract_task_id": None,
                    "rule_code": "DAILY_HOURS_EXCEEDED",
                    "severity": "warning",
                    "message": f"{person} was billed {hours:g} hours on {work_date.isoformat()} — over the "
                    f"{settings.max_hours_per_day:g}-hour/day threshold with no overtime noted.",
                }
            )
    for (person, _week), hours in hours_by_person_week.items():
        if hours > settings.max_hours_per_week:
            flags.append(
                {
                    "contract_task_id": None,
                    "rule_code": "WEEKLY_HOURS_EXCEEDED",
                    "severity": "warning",
                    "message": f"{person} was billed {hours:g} hours in one week — over the "
                    f"{settings.max_hours_per_week:g}-hour/week threshold.",
                }
            )

    # --- Inspection-date cross-check --------------------------------------------
    reports = [
        r
        for r in project.inspection_reports
        if not (invoice.period_start and r.period_end and r.period_end < invoice.period_start)
        and not (invoice.period_end and r.period_start and r.period_start > invoice.period_end)
    ]
    if reports:
        reported_dates: set[str] = set()
        for r in reports:
            if r.inspection_dates_json:
                reported_dates.update(json.loads(r.inspection_dates_json))
        for item in invoice.line_items:
            if item.work_date and _INSPECTION_RE.search(item.description):
                if item.work_date.isoformat() not in reported_dates:
                    flags.append(
                        {
                            "contract_task_id": item.contract_task_id,
                            "rule_code": "INSPECTION_DATE_MISMATCH",
                            "severity": "warning",
                            "message": f"Inspection billed on {item.work_date.isoformat()} doesn't appear in any "
                            "uploaded field/inspection report for this period.",
                        }
                    )

    # --- Task-level (contract-value / continuity / trend) checks ---------------
    task_ids_on_invoice = {item.contract_task_id for item in invoice.line_items if item.contract_task_id}
    for task_id in task_ids_on_invoice:
        task = tasks_by_id.get(task_id)
        if not task:
            continue
        ledger_entry = ledger.get(task_id, {"baseline": 0.0, "entries": []})
        prior = _cumulative_before(ledger_entry, invoice.id)
        this_period = _billed_this_period_for_task(invoice, task_id)
        cumulative = prior + this_period
        is_seeding_invoice = _is_seeding_invoice(ledger_entry, invoice.id)

        if task.estimated_fee:
            pct = cumulative / task.estimated_fee
            if cumulative > task.estimated_fee + AMOUNT_TOLERANCE:
                flags.append(
                    {
                        "contract_task_id": task.id,
                        "rule_code": "OVERBILLED",
                        "severity": "critical",
                        "message": f"Task {task.task_number} ({task.description[:60]}) is billed to "
                        f"${cumulative:,.2f} against a ${task.estimated_fee:,.2f} contract value — "
                        f"{pct:.1%} of the task total.",
                    }
                )
            elif pct >= settings.billed_warning_threshold:
                flags.append(
                    {
                        "contract_task_id": task.id,
                        "rule_code": "THRESHOLD_WARNING",
                        "severity": "warning",
                        "message": f"Task {task.task_number} ({task.description[:60]}) is {pct:.1%} billed "
                        f"(${cumulative:,.2f} of ${task.estimated_fee:,.2f}) — approaching the task limit.",
                    }
                )

        stated_prior = _stated_field_for_task(invoice, task_id, "previously_billed")
        if stated_prior is not None and not is_seeding_invoice and abs(stated_prior - prior) > AMOUNT_TOLERANCE:
            flags.append(
                {
                    "contract_task_id": task.id,
                    "rule_code": "PRIOR_BILLED_MISMATCH",
                    "severity": "critical",
                    "message": f"Task {task.task_number}: invoice states prior billed of ${stated_prior:,.2f}, but "
                    f"the last invoice we have on file for this task totaled ${prior:,.2f}.",
                }
            )

        stated_total = _stated_field_for_task(invoice, task_id, "total_billed_to_date")
        if stated_total is not None and abs(stated_total - cumulative) > AMOUNT_TOLERANCE:
            flags.append(
                {
                    "contract_task_id": task.id,
                    "rule_code": "MATH_ERROR",
                    "severity": "warning",
                    "message": f"Task {task.task_number}: invoice's 'total billed to date' of ${stated_total:,.2f} "
                    f"doesn't equal prior + this period (${cumulative:,.2f}).",
                }
            )

        earlier_amounts = [btp for inv, btp in ledger_entry["entries"] if inv.id != invoice.id]
        if earlier_amounts and this_period > max(earlier_amounts) and this_period > 0:
            flags.append(
                {
                    "contract_task_id": task.id,
                    "rule_code": "MOST_EXPENSIVE",
                    "severity": "info",
                    "message": f"Task {task.task_number}: this period's ${this_period:,.2f} is the highest billed "
                    f"in a single period to date (previous high: ${max(earlier_amounts):,.2f}).",
                }
            )

    # --- Invoice-level subtotal check -------------------------------------------
    computed_total = sum(
        (item.billed_this_period if item.billed_this_period is not None else item.amount)
        for item in invoice.line_items
    )
    if invoice.total_amount is not None and abs(computed_total - invoice.total_amount) > AMOUNT_TOLERANCE:
        flags.append(
            {
                "contract_task_id": None,
                "rule_code": "MATH_ERROR",
                "severity": "warning",
                "message": f"Line items sum to ${computed_total:,.2f} but the invoice total is "
                f"${invoice.total_amount:,.2f}.",
            }
        )

    # --- Markup on reimbursables -------------------------------------------------
    if invoice.reimbursable_markup_billed is not None and contract and contract.default_markup_pct is not None:
        if abs(invoice.reimbursable_markup_billed - contract.default_markup_pct) > MARKUP_TOLERANCE_PCT:
            flags.append(
                {
                    "contract_task_id": None,
                    "rule_code": "MARKUP_MISMATCH",
                    "severity": "warning",
                    "message": f"Reimbursables billed with a {invoice.reimbursable_markup_billed:g}% markup, but "
                    f"the contract specifies {contract.default_markup_pct:g}%.",
                }
            )

    return flags


def summarize_billing(project: Project) -> BillingSummaryResponse:
    """Schedule-of-values summary: one row per contract task, as of the latest invoice."""
    contract = latest_contract(project)
    tasks = contract.tasks if contract else []
    ledger = build_task_ledger(project)

    rows: list[TaskSummaryRow] = []
    for task in tasks:
        ledger_entry = ledger.get(task.id, {"baseline": 0.0, "entries": []})
        entries = ledger_entry["entries"]
        billed_to_date = ledger_entry["baseline"] + sum(btp for _inv, btp in entries)
        billed_this_period = entries[-1][1] if entries else 0.0
        prior_billed = billed_to_date - billed_this_period
        pct_billed = (billed_to_date / task.estimated_fee) if task.estimated_fee else 0.0
        remaining = task.estimated_fee - billed_to_date

        flag_level = None
        if pct_billed >= settings.billed_critical_threshold:
            flag_level = "critical"
        elif pct_billed >= settings.billed_warning_threshold:
            flag_level = "warning"

        rows.append(
            TaskSummaryRow(
                task_number=task.task_number,
                cost_code=task.cost_code,
                description=task.description,
                fee_type=task.fee_type,
                estimated_fee=task.estimated_fee,
                prior_billed=prior_billed,
                billed_this_period=billed_this_period,
                billed_to_date=billed_to_date,
                pct_billed=pct_billed,
                remaining=remaining,
                is_active=task.is_active,
                flag_level=flag_level,
            )
        )

    return BillingSummaryResponse(
        rows=rows,
        contract_total=sum(t.estimated_fee for t in tasks),
        total_billed_to_date=sum(r.billed_to_date for r in rows),
        total_remaining=sum(r.remaining for r in rows),
    )
