"""Database engine and session management."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


def _normalize_db_url(url: str) -> str:
    """Render/Heroku hand out 'postgres://' URLs, but SQLAlchemy 2.x needs 'postgresql://'.

    Set DATABASE_URL to a managed Postgres connection string for persistent storage; leave it
    unset to use the default local SQLite file (fine for a demo, but wiped on each redeploy).
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = _normalize_db_url(settings.database_url)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight additive migrations for existing SQLite databases (create_all won't ALTER).
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(invoice_line_items)")).fetchall()}
            if cols and "contract_amount" not in cols:
                conn.execute(text("ALTER TABLE invoice_line_items ADD COLUMN contract_amount FLOAT"))
