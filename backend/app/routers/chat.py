"""Open-ended project chat — full project context + persisted history (the 'memory')."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ChatMessage, User
from app.routers.projects import get_owned_project
from app.schemas import ChatMessageResponse, ChatRequest
from app.services.chat import get_chat_reply

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])

MAX_HISTORY_MESSAGES = 20


@router.get("", response_model=list[ChatMessageResponse])
def get_chat_history(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(project_id, db, user)
    return project.chat_messages


@router.post("", response_model=ChatMessageResponse)
def send_chat_message(
    project_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_owned_project(project_id, db, user)

    user_msg = ChatMessage(project_id=project.id, role="user", content=body.message)
    db.add(user_msg)
    db.commit()

    history = [
        {"role": m.role, "content": m.content} for m in project.chat_messages[-MAX_HISTORY_MESSAGES:-1]
    ]
    reply = get_chat_reply(project, history, body.message)

    assistant_msg = ChatMessage(project_id=project.id, role="assistant", content=reply)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg
