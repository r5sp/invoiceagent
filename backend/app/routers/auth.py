"""Authentication routes: email register/login, restricted to the allowed domain."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.auth import create_access_token, hash_password, is_allowed_email, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str | None
    auth_provider: str

    model_config = {"from_attributes": True}


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_expire_hours * 3600,
        path="/",
    )


def _auth_response(user: User) -> dict:
    token = create_access_token(user.id, user.email)
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.post("/register")
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if not is_allowed_email(email):
        raise HTTPException(
            status_code=403,
            detail=f"Only @{settings.allowed_email_domain} email addresses can register.",
        )

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        email=email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
        auth_provider="email",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    payload = _auth_response(user)
    _set_auth_cookie(response, payload["access_token"])
    return payload


@router.post("/login")
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if not is_allowed_email(email):
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to @{settings.allowed_email_domain} accounts.",
        )

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    payload = _auth_response(user)
    _set_auth_cookie(response, payload["access_token"])
    return payload


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        "access_token",
        path="/",
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
    )
    return {"message": "Logged out"}
