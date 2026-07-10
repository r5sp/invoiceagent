"""Database engine and session management."""

from sqlalchemy import create_engine, inspect, text
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


def _add_column_if_missing(table: str, column: str, coltype: str) -> None:
    """Idempotent additive migration that works on both SQLite and Postgres.

    create_all() only CREATEs missing tables — it never ALTERs an existing one to add a column,
    so a persistent (Postgres) DB from a prior deploy would otherwise be missing new columns and
    500 on every read/insert. Runs on all dialects, guarded for the not-yet-created table.
    """
    insp = inspect(engine)
    if not insp.has_table(table):
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    if column in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight additive migrations (create_all won't ALTER an existing table).
    float_type = "FLOAT" if DATABASE_URL.startswith("sqlite") else "DOUBLE PRECISION"
    _add_column_if_missing("invoice_line_items", "contract_amount", float_type)
    _add_column_if_missing("review_flags", "line_item_id", "INTEGER")
