import sqlalchemy as sa
import os
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from src.db.model import Base

load_dotenv()

engine = sa.create_engine(os.getenv("DB_URL"))
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create tables that don't exist yet. Safe to call repeatedly."""
    Base.metadata.create_all(engine)

