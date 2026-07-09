"""Upload and parse a contract's Exhibit B fee schedule."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Contract, ContractTask, User
from app.routers.projects import get_owned_project
from app.schemas import ContractResponse
from app.services.contract_extraction import extract_contract_tasks
from app.services.file_parser import extract_tables_from_pdf, extract_text, validate_file_type

router = APIRouter(prefix="/api/projects/{project_id}/contracts", tags=["contracts"])


@router.get("", response_model=list[ContractResponse])
def list_contracts(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    return project.contracts


@router.post("", response_model=ContractResponse)
def upload_contract(
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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"contract_{project_id}_{file.filename}").write_bytes(content)

    result, _method = extract_contract_tasks(raw_text, tables)
    if not result.tasks:
        raise HTTPException(
            status_code=422,
            detail="Couldn't find a fee schedule (Exhibit B) in this document. Configure OPENAI_API_KEY for "
            "more robust parsing, or confirm the contract includes a task/fee table.",
        )

    contract = Contract(
        project_id=project.id,
        file_name=file.filename,
        raw_text=raw_text,
        label=result.label,
        not_to_exceed_total=result.not_to_exceed_total,
        default_markup_pct=result.default_markup_pct,
        status="parsed",
    )
    db.add(contract)
    db.flush()

    for i, t in enumerate(result.tasks):
        db.add(
            ContractTask(
                contract_id=contract.id,
                sort_order=i,
                task_number=t.task_number,
                cost_code=t.cost_code,
                description=t.description,
                fee_type=t.fee_type,
                unit_type=t.unit_type,
                unit_rate=t.unit_rate,
                estimated_fee=t.estimated_fee,
                markup_pct=t.markup_pct,
                is_active=t.is_active,
                superseded_by_task_number=t.superseded_by_task_number,
                notes=t.notes,
            )
        )

    db.commit()
    db.refresh(contract)
    return contract
