"""Upload, parse, correlate, and review an invoice against the project's contract."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Invoice, InvoiceLineItem, ReviewFlag, User
from app.routers.projects import get_owned_project
from app.schemas import InvoiceResponse
from app.services.correlation import correlate_line_items
from app.services.file_parser import (
    extract_tables_from_pdf,
    extract_text,
    extract_word_rows_from_pdf,
    validate_file_type,
)
from app.services.invoice_extraction import extract_invoice
from app.services.parsing_utils import parse_date
from app.services.review_engine import latest_contract, review_invoice

router = APIRouter(prefix="/api/projects/{project_id}/invoices", tags=["invoices"])


@router.get("", response_model=list[InvoiceResponse])
def list_invoices(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    return sorted(project.invoices, key=lambda i: (i.period_start or i.uploaded_at.date(), i.id))


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    project_id: int, invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_owned_project(project_id, db, user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.project_id != project_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _line_dicts_from_extraction(fmt: str, task_rows, tm_items) -> list[dict]:
    line_dicts: list[dict] = []
    if fmt == "task_correlated":
        for row in task_rows:
            line_dicts.append(
                {
                    "raw_task_number": row.raw_task_number,
                    "raw_cost_code": row.raw_cost_code,
                    "description": row.description,
                    "work_date": None,
                    "person_name": None,
                    "quantity": None,
                    "unit_type": None,
                    "unit_rate": None,
                    "amount": row.billed_this_period or 0.0,
                    "previously_billed": row.previously_billed,
                    "billed_this_period": row.billed_this_period,
                    "total_billed_to_date": row.total_billed_to_date,
                    "contract_amount": row.estimated_fee,
                    "category": "labor",
                }
            )
    else:
        for item in tm_items:
            line_dicts.append(
                {
                    "raw_task_number": item.raw_task_number,
                    "raw_cost_code": item.raw_cost_code,
                    "description": item.description,
                    "work_date": parse_date(item.work_date),
                    "person_name": item.person_name,
                    "quantity": item.quantity,
                    "unit_type": item.unit_type,
                    "unit_rate": item.unit_rate,
                    "amount": item.amount,
                    "previously_billed": None,
                    "billed_this_period": None,
                    "total_billed_to_date": None,
                    "contract_amount": None,
                    "category": item.category,
                }
            )
    return line_dicts


@router.post("", response_model=InvoiceResponse)
def upload_invoice(
    project_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_owned_project(project_id, db, user)

    try:
        ext = validate_file_type(file.filename, file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content = file.file.read()
    raw_text = extract_text(content, ext)
    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in this document.")
    tables = extract_tables_from_pdf(content) if ext == ".pdf" else []
    word_rows = extract_word_rows_from_pdf(content) if ext == ".pdf" else []

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"invoice_{project_id}_{file.filename}").write_bytes(content)

    try:
        fmt, task_rows, tm_items, metadata = extract_invoice(raw_text, tables, word_rows)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    invoice = Invoice(
        project_id=project.id,
        file_name=file.filename,
        raw_text=raw_text,
        invoice_number=metadata.get("invoice_number"),
        invoice_date=metadata.get("invoice_date"),
        period_start=metadata.get("period_start"),
        period_end=metadata.get("period_end"),
        invoice_format=fmt,
        subtotal=metadata.get("subtotal"),
        total_amount=metadata.get("total_amount"),
        reimbursable_amount=metadata.get("reimbursable_amount"),
        reimbursable_markup_billed=metadata.get("reimbursable_markup_billed"),
        status="parsed",
    )
    db.add(invoice)
    db.flush()

    contract = latest_contract(project)
    tasks = contract.tasks if contract else []
    line_dicts = _line_dicts_from_extraction(fmt, task_rows, tm_items)
    correlate_line_items(line_dicts, tasks)

    for d in line_dicts:
        db.add(
            InvoiceLineItem(
                invoice_id=invoice.id,
                contract_task_id=d.get("contract_task_id"),
                raw_task_number=d.get("raw_task_number"),
                raw_cost_code=d.get("raw_cost_code"),
                description=d["description"],
                work_date=d.get("work_date"),
                person_name=d.get("person_name"),
                quantity=d.get("quantity"),
                unit_type=d.get("unit_type"),
                unit_rate=d.get("unit_rate"),
                amount=d.get("amount") or 0.0,
                previously_billed=d.get("previously_billed"),
                billed_this_period=d.get("billed_this_period"),
                total_billed_to_date=d.get("total_billed_to_date"),
                contract_amount=d.get("contract_amount"),
                category=d.get("category", "labor"),
                correlation_confidence=d.get("correlation_confidence"),
            )
        )
    db.commit()
    db.refresh(invoice)
    db.refresh(project)

    flags = review_invoice(project, invoice)
    for f in flags:
        db.add(
            ReviewFlag(
                invoice_id=invoice.id,
                contract_task_id=f.get("contract_task_id"),
                rule_code=f["rule_code"],
                severity=f["severity"],
                message=f["message"],
            )
        )
    invoice.status = "reviewed"
    db.commit()
    db.refresh(invoice)
    return invoice


@router.delete("/{invoice_id}")
def delete_invoice(
    project_id: int, invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_owned_project(project_id, db, user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.project_id != project_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    return {"message": "Invoice deleted"}
