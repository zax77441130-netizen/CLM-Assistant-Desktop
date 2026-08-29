from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import RuntimeSettings, get_settings


class Base(DeclarativeBase):
    pass


def build_engine(settings: RuntimeSettings | None = None) -> Engine:
    active_settings = settings or get_settings()
    return create_engine(active_settings.database_url, connect_args={"check_same_thread": False})


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
