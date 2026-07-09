"""Upload a daily/monthly field report used to cross-check invoiced inspection dates."""

import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.database import get_db
from app.dependencies import get_current_user
from app.models import InspectionReport, User
from app.routers.projects import get_owned_project
from app.services.file_parser import extract_text, validate_file_type
from app.services.inspection_extraction import extract_inspection_dates
from app.services.parsing_utils import parse_date

router = APIRouter(prefix="/api/projects/{project_id}/inspection-reports", tags=["inspection-reports"])


class InspectionReportResponse(BaseModel):
    id: int
    file_name: str
    period_start: str | None
    period_end: str | None
    inspection_dates: list[str]

    model_config = {"from_attributes": True}


def _to_response(report: InspectionReport) -> InspectionReportResponse:
    return InspectionReportResponse(
        id=report.id,
        file_name=report.file_name,
        period_start=report.period_start.isoformat() if report.period_start else None,
        period_end=report.period_end.isoformat() if report.period_end else None,
        inspection_dates=json.loads(report.inspection_dates_json) if report.inspection_dates_json else [],
    )


@router.get("", response_model=list[InspectionReportResponse])
def list_inspection_reports(
    project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = get_owned_project(project_id, db, user)
    return [_to_response(r) for r in project.inspection_reports]


@router.post("", response_model=InspectionReportResponse)
def upload_inspection_report(
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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"inspection_{project_id}_{file.filename}").write_bytes(content)

    extracted = extract_inspection_dates(raw_text)

    report = InspectionReport(
        project_id=project.id,
        file_name=file.filename,
        raw_text=raw_text,
        period_start=parse_date(extracted.period_start),
        period_end=parse_date(extracted.period_end),
        inspection_dates_json=json.dumps(extracted.inspection_dates),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.delete("/{report_id}")
def delete_inspection_report(
    project_id: int, report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    get_owned_project(project_id, db, user)
    report = db.get(InspectionReport, report_id)
    if not report or report.project_id != project_id:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"message": "Report deleted"}
