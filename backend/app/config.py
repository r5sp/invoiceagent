"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


class Settings(BaseSettings):
    database_url: str = f"sqlite:///{BASE_DIR / 'invoiceagent.db'}"

    # OpenAI — required for contract/invoice parsing and chat
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Auth
    require_auth: bool = True
    allowed_email_domain: str = "fifthspace.com"
    jwt_secret: str = "change-this-to-a-long-random-secret"
    jwt_expire_hours: int = 72
    cookie_secure: bool = False

    # URLs
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # Production
    serve_frontend: bool = False
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Review rule thresholds
    billed_warning_threshold: float = 0.75
    billed_critical_threshold: float = 1.0
    max_hours_per_day: float = 8.0
    max_hours_per_week: float = 40.0

    class Config:
        env_file = BASE_DIR.parent / ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cookie_samesite(self) -> str:
        """Cross-domain deploys (e.g. Vercel + Render) need SameSite=None."""
        if self.frontend_url.rstrip("/") != self.backend_url.rstrip("/"):
            return "none"
        return "lax"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.cookie_secure or self.cookie_samesite == "none"


settings = Settings()
