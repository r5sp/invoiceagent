"""Billing summary (JSON) and downloadable Excel billing sheet."""

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Invoice, User
from app.routers.projects import get_owned_project
from app.schemas import BillingSummaryResponse, EmailDraftResponse
from app.services.billing_sheet import generate_billing_workbook
from app.services.email_draft import draft_revision_email
from app.services.review_engine import summarize_billing

router = APIRouter(prefix="/api/projects/{project_id}", tags=["billing"])


@router.get("/billing-summary", response_model=BillingSummaryResponse)
def billing_summary(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    return summarize_billing(project)


@router.get("/billing-sheet.xlsx")
def download_billing_sheet(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    wb = generate_billing_workbook(project)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{project.name.replace(' ', '_')}_Billing_Sheet.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/invoices/{invoice_id}/email-draft", response_model=EmailDraftResponse)
def email_draft(
    project_id: int, invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = get_owned_project(project_id, db, user)
    invoice = db.get(Invoice, invoice_id)
    if not invoice or invoice.project_id != project_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return draft_revision_email(project, invoice)
