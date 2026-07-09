"""Project CRUD — a project is one consultant engagement/contract tracked over time."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Project, User
from app.schemas import ProjectCreateRequest, ProjectDetailResponse, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


def get_owned_project(project_id: int, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if not project or (project.owner_id is not None and project.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Project).filter(Project.owner_id == user.id).order_by(Project.created_at.desc()).all()


@router.post("", response_model=ProjectResponse)
def create_project(
    body: ProjectCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = Project(owner_id=user.id, name=body.name.strip(), consultant_name=(body.consultant_name or None))
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_owned_project(project_id, db, user)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    db.delete(project)
    db.commit()
    return {"message": "Project deleted"}
