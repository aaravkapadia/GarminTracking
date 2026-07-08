import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sqlalchemy as sa
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from src.db.model import Base

load_dotenv()


def _normalize_db_url(url: str) -> str:
    """Route Postgres URLs through the pure-Python pg8000 driver.

    Railway hands out ``postgresql://…`` (sometimes ``postgres://``), which
    SQLAlchemy would drive with psycopg2 — a C extension that needs Postgres
    build headers and breaks the Nixpacks build. pg8000 is pure Python, so we
    rewrite the scheme to ``postgresql+pg8000`` and drop the ``sslmode`` query
    param (pg8000 doesn't accept it). SQLite and other URLs pass through
    unchanged.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


engine = sa.create_engine(_normalize_db_url(os.getenv("DB_URL")))
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create tables that don't exist yet. Safe to call repeatedly."""
    Base.metadata.create_all(engine)

