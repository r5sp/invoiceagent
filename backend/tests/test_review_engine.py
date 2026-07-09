from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Contract, ContractTask, Invoice, InvoiceLineItem, Project
from app.services.review_engine import review_invoice, summarize_billing


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def make_project_with_task(db, estimated_fee=1000.0, unit_rate=100.0, markup_pct=None):
    project = Project(name="Test Project")
    db.add(project)
    db.flush()

    contract = Contract(project_id=project.id, file_name="contract.pdf", default_markup_pct=markup_pct)
    db.add(contract)
    db.flush()

    task = ContractTask(
        contract_id=contract.id,
        sort_order=0,
        task_number="1",
        cost_code="3100-0230",
        description="Field inspection",
        fee_type="tm",
        unit_type="day",
        unit_rate=unit_rate,
        estimated_fee=estimated_fee,
    )
    db.add(task)
    db.commit()
    db.refresh(project)
    return project, contract, task


def add_task_correlated_invoice(db, project, task, period_start, previously_billed, billed_this_period, total_billed_to_date=None):
    invoice = Invoice(
        project_id=project.id,
        file_name=f"invoice-{period_start}.pdf",
        invoice_number=str(period_start),
        period_start=period_start,
        period_end=period_start,
        invoice_format="task_correlated",
    )
    db.add(invoice)
    db.flush()
    total = total_billed_to_date if total_billed_to_date is not None else previously_billed + billed_this_period
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=task.id,
            description=task.description,
            amount=billed_this_period,
            previously_billed=previously_billed,
            billed_this_period=billed_this_period,
            total_billed_to_date=total,
        )
    )
    db.commit()
    db.refresh(project)
    return invoice


def test_first_invoice_seeds_baseline_no_false_prior_mismatch(db):
    project, contract, task = make_project_with_task(db, estimated_fee=100_000)
    invoice = add_task_correlated_invoice(
        db, project, task, date(2026, 1, 1), previously_billed=50_000, billed_this_period=0
    )
    flags = review_invoice(project, invoice)
    assert not any(f["rule_code"] == "PRIOR_BILLED_MISMATCH" for f in flags)


def test_second_invoice_continuity_ok(db):
    project, contract, task = make_project_with_task(db, estimated_fee=100_000)
    add_task_correlated_invoice(db, project, task, date(2026, 1, 1), previously_billed=50_000, billed_this_period=10_000)
    db.refresh(project)
    invoice2 = add_task_correlated_invoice(
        db, project, task, date(2026, 4, 1), previously_billed=60_000, billed_this_period=5_000
    )
    flags = review_invoice(project, invoice2)
    assert not any(f["rule_code"] == "PRIOR_BILLED_MISMATCH" for f in flags)


def test_second_invoice_continuity_mismatch_flagged(db):
    project, contract, task = make_project_with_task(db, estimated_fee=100_000)
    add_task_correlated_invoice(db, project, task, date(2026, 1, 1), previously_billed=50_000, billed_this_period=10_000)
    db.refresh(project)
    # States prior billed as 999,999 instead of the real 60,000 — should be flagged.
    invoice2 = add_task_correlated_invoice(
        db, project, task, date(2026, 4, 1), previously_billed=999_999, billed_this_period=5_000
    )
    flags = review_invoice(project, invoice2)
    mismatch = [f for f in flags if f["rule_code"] == "PRIOR_BILLED_MISMATCH"]
    assert len(mismatch) == 1
    assert "999,999" in mismatch[0]["message"]


def test_overbilled_flagged(db):
    project, contract, task = make_project_with_task(db, estimated_fee=10_000)
    invoice = add_task_correlated_invoice(
        db, project, task, date(2026, 1, 1), previously_billed=9_000, billed_this_period=5_000
    )
    flags = review_invoice(project, invoice)
    overbilled = [f for f in flags if f["rule_code"] == "OVERBILLED"]
    assert len(overbilled) == 1
    assert "184" in overbilled[0]["message"] or "140" in overbilled[0]["message"]


def test_threshold_warning_at_75_pct(db):
    project, contract, task = make_project_with_task(db, estimated_fee=10_000)
    invoice = add_task_correlated_invoice(
        db, project, task, date(2026, 1, 1), previously_billed=7_500, billed_this_period=0
    )
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "THRESHOLD_WARNING" for f in flags)


def test_rate_mismatch_flagged(db):
    project, contract, task = make_project_with_task(db, estimated_fee=10_000, unit_rate=100.0)
    invoice = Invoice(project_id=project.id, file_name="tm.pdf", invoice_format="tm_receipt")
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=task.id,
            description="inspection",
            quantity=2,
            unit_rate=150.0,
            amount=300.0,
        )
    )
    db.commit()
    db.refresh(project)
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "RATE_MISMATCH" for f in flags)


def test_not_in_contract_flagged(db):
    project, contract, task = make_project_with_task(db)
    invoice = Invoice(project_id=project.id, file_name="tm.pdf", invoice_format="tm_receipt")
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=None,
            description="unrelated work not in contract",
            amount=500.0,
        )
    )
    db.commit()
    db.refresh(project)
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "NOT_IN_CONTRACT" for f in flags)


def test_line_item_math_error_flagged(db):
    project, contract, task = make_project_with_task(db, unit_rate=100.0)
    invoice = Invoice(project_id=project.id, file_name="tm.pdf", invoice_format="tm_receipt")
    db.add(invoice)
    db.flush()
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=task.id,
            description="inspection",
            quantity=3,
            unit_rate=100.0,
            amount=999.0,  # should be 300
        )
    )
    db.commit()
    db.refresh(project)
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "MATH_ERROR" for f in flags)


def test_daily_hours_exceeded_flagged(db):
    project, contract, task = make_project_with_task(db)
    invoice = Invoice(project_id=project.id, file_name="tm.pdf", invoice_format="tm_receipt")
    db.add(invoice)
    db.flush()
    work_date = date(2026, 5, 1)
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=task.id,
            description="inspection AM",
            person_name="Jane Doe",
            unit_type="hour",
            quantity=6,
            work_date=work_date,
            amount=600.0,
        )
    )
    db.add(
        InvoiceLineItem(
            invoice_id=invoice.id,
            contract_task_id=task.id,
            description="inspection PM",
            person_name="Jane Doe",
            unit_type="hour",
            quantity=5,
            work_date=work_date,
            amount=500.0,
        )
    )
    db.commit()
    db.refresh(project)
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "DAILY_HOURS_EXCEEDED" for f in flags)


def test_markup_mismatch_flagged(db):
    project, contract, task = make_project_with_task(db, markup_pct=10.0)
    invoice = Invoice(
        project_id=project.id,
        file_name="tm.pdf",
        invoice_format="tm_receipt",
        reimbursable_markup_billed=25.0,
    )
    db.add(invoice)
    db.commit()
    db.refresh(project)
    flags = review_invoice(project, invoice)
    assert any(f["rule_code"] == "MARKUP_MISMATCH" for f in flags)


def test_summarize_billing_totals(db):
    project, contract, task = make_project_with_task(db, estimated_fee=10_000)
    add_task_correlated_invoice(db, project, task, date(2026, 1, 1), previously_billed=5_000, billed_this_period=1_000)
    db.refresh(project)
    summary = summarize_billing(project)
    assert summary.contract_total == 10_000
    assert summary.total_billed_to_date == 6_000
    row = summary.rows[0]
    assert row.prior_billed == 5_000
    assert row.billed_this_period == 1_000
    assert row.pct_billed == pytest.approx(0.6)
