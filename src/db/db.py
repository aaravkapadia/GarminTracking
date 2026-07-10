""" 
Initalize db and normalize url
"""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sqlalchemy as sa
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from src.db.model import Base

load_dotenv()


def _normalize_db_url(url: str) -> str:
    """
    Normalize URL for Railway
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "sslmode"]
        url = urlunsplit(parts._replace(query=urlencode(query)))
    return url


_DB_URL = os.getenv("DB_URL")
if not _DB_URL:
    raise RuntimeError(
        "DB_URL is not set."
    )

engine = sa.create_engine(_normalize_db_url(_DB_URL))
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create tables that don't exist yet."""
    Base.metadata.create_all(engine)

