"""Invoice Agent — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIST, UPLOAD_DIR, settings
from app.database import init_db
from app.routers import auth, billing, chat, contracts, inspection_reports, invoices, projects

_PLACEHOLDER_JWT_SECRET = "change-this-to-a-long-random-secret"


def _enforce_production_safety() -> None:
    """Fail closed rather than ever serve the @fifthspace.com lock in a forgeable state.

    When auth is required (production), refuse to boot if JWT_SECRET is still the public
    placeholder — otherwise anyone reading the repo could forge a valid session and bypass the
    domain restriction entirely. Render's render.yaml generates a real secret automatically.
    """
    if settings.require_auth and settings.jwt_secret == _PLACEHOLDER_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is still the default placeholder while REQUIRE_AUTH=true. Set JWT_SECRET "
            "to a long random value before starting in production (the domain lock is not secure "
            "without it)."
        )


_enforce_production_safety()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Invoice Agent",
    description="Fifth Space consultant invoice review — parses contracts and invoices, builds the "
    "billing sheet, and flags issues per Joe's review procedures.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(contracts.router)
app.include_router(invoices.router)
app.include_router(inspection_reports.router)
app.include_router(billing.router)
app.include_router(chat.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if settings.serve_frontend and FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
