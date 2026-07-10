"""Regression tests for the borderless ACLA-style invoice summary parser.

These mirror the two real layouts (invoice 10775 and 10776 for PPS Prequel Park / The Point)
using synthetic coordinate-reconstructed rows, so the parser can't silently regress without
needing the consultant's PDFs in the repo.
"""

from types import SimpleNamespace

from app.services.invoice_extraction import (
    detect_and_extract_acla_summary,
    extract_invoice_metadata_heuristic,
    looks_like_invoice,
)
from app.services.review_engine import _standalone_task_flags


# Layout A: Description | Contract Amount | Percent Complete | Remaining | Prior Billed | Current Billed
ACLA_5COL_ROWS = [
    ["Contract", "Percent", "Prior", "Current"],
    ["Description", "Amount", "Complete", "Remaining", "Billed", "Billed"],
    ["T6A1", "Construction", "Documents:", "Job", "Parks", "2",
     "164,000.00", "66.19", "55,443.75", "71,556.25", "37,000.00"],
    ["(Prequel", "Park)", "Cost", "Code:2100-0450"],
    ["T10A2:", "DD", "Lighting", "Site:", "Park", "2", "(Prequel", "Park)", "Cost",
     "39,000.00", "60.00", "15,600.00", "19,500.00", "3,900.00"],
    ["Code:", "2100-0450"],
    ["T14A2:", "CD", "MEP", "Site:", "Park", "2", "(Prequel", "Park)", "Cost",
     "3,500.00", "25.00", "2,625.00", "0.00", "875.00"],
    ["Code:", "2100-0500"],
    ["Total", "214,450.00", "63.65", "77,952.50", "94,006.25", "42,491.25"],
]

# Layout B: Description | Contract Amt | Total Billed | Current Billed
ACLA_3COL_ROWS = [
    ["Contract", "Total", "Current"],
    ["Description", "Amt", "Billed", "Billed"],
    ["T18A3:", "Shoreline", "Finishes:Phase", "2", "(Shoreline)", "Cost", "Code:", "2100-0450",
     "8,000.00", "3,750.00", "600.00"],
    ["T20A3:", "PERMITTING", "JOB:", "PARKS", "2", "(PREQUEL", "PARK)", "COST", "CODE:", "2100-0450",
     "20,000.00", "12,260.00", "9,472.50"],
    ["REIMBURSABLE", "(PERMITTING)", "27.42", "27.42", "0.00"],
    ["Total", "112,537.42", "123,509.92", "10,972.50"],
]


def _by_task(rows):
    return {r.raw_task_number: r for r in rows}


def test_acla_5col_layout():
    rows = detect_and_extract_acla_summary(ACLA_5COL_ROWS)
    assert rows is not None
    by = _by_task(rows)
    # Total row must be skipped.
    assert "TOTAL" not in {(t or "").upper() for t in by}
    assert set(by) == {"T6A1", "T10A2", "T14A2"}

    t6 = by["T6A1"]
    assert t6.raw_cost_code == "2100-0450"  # pulled from the wrapped continuation line
    assert t6.estimated_fee == 164000.0
    assert t6.previously_billed == 71556.25
    assert t6.billed_this_period == 37000.0
    assert t6.total_billed_to_date == 108556.25  # prior + current

    assert by["T14A2"].raw_cost_code == "2100-0500"
    assert by["T14A2"].previously_billed == 0.0


def test_acla_3col_layout_and_reimbursable():
    rows = detect_and_extract_acla_summary(ACLA_3COL_ROWS)
    assert rows is not None
    by = _by_task(rows)
    assert "T18A3" in by and "T20A3" in by

    t20 = by["T20A3"]
    assert t20.estimated_fee == 20000.0
    assert t20.total_billed_to_date == 12260.0
    assert t20.billed_this_period == 9472.5
    assert t20.previously_billed == 2787.5  # total - current

    # Reimbursable line has no task number but is still captured.
    reimb = [r for r in rows if r.raw_task_number is None]
    assert len(reimb) == 1
    assert reimb[0].total_billed_to_date == 27.42


def test_non_acla_rows_return_none():
    # A plain document with no T-numbered value rows must not be misdetected.
    assert detect_and_extract_acla_summary([["Hello", "world"], ["Some", "prose", "here"]]) is None


def test_looks_like_invoice_distinguishes_from_contract():
    assert looks_like_invoice("Associate Capital Invoice number 10776\nDate 06/03/2026") == "10776"
    assert looks_like_invoice("Invoice total 10,972.50") == ""  # invoice, no number found
    # A contract/agreement must NOT be flagged as an invoice.
    assert looks_like_invoice("CONSULTANT AGREEMENT — Exhibit B, Compensation. Task 1 ...") is None


def _line(**kw):
    base = dict(
        raw_task_number=None, description="", contract_amount=None,
        previously_billed=None, billed_this_period=None, total_billed_to_date=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_standalone_flags_at_and_over_limit():
    # Fully billed → at-limit critical.
    flags = _standalone_task_flags(_line(raw_task_number="T3A1", contract_amount=42000.0, total_billed_to_date=42000.0))
    assert any(f["rule_code"] == "THRESHOLD_WARNING" and f["severity"] == "critical" for f in flags)

    # Overbilled → OVERBILLED critical.
    over = _standalone_task_flags(_line(raw_task_number="T9", contract_amount=1000.0, total_billed_to_date=1500.0))
    assert any(f["rule_code"] == "OVERBILLED" for f in over)

    # Comfortably under threshold → no flag.
    under = _standalone_task_flags(_line(raw_task_number="T18A3", contract_amount=8000.0, total_billed_to_date=3750.0))
    assert under == []


def test_standalone_flags_internal_math():
    bad = _standalone_task_flags(
        _line(raw_task_number="T1", previously_billed=100.0, billed_this_period=50.0, total_billed_to_date=200.0)
    )
    assert any(f["rule_code"] == "MATH_ERROR" for f in bad)


def test_acla_metadata_field_names():
    text = (
        "Associate Capital Invoice number 10775\n"
        "Date 06/03/2026\n"
        "For Professional Services Through 05/31/2026\n"
        "Invoice total 42,491.25\n"
    )
    meta = extract_invoice_metadata_heuristic(text)
    assert meta["invoice_number"] == "10775"
    assert str(meta["invoice_date"]) == "2026-06-03"
    assert str(meta["period_end"]) == "2026-05-31"
    assert meta["total_amount"] == 42491.25
