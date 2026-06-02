from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from copilot.core.config import get_settings

DatabaseConnection = psycopg.Connection[DictRow]
_MIGRATION_LOCK_KEY = (1_936_286_819, 1)


def psycopg_conninfo(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


def sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


@lru_cache()
def get_connection_pool() -> ConnectionPool[DatabaseConnection]:
    return ConnectionPool(
        conninfo=psycopg_conninfo(get_settings().DATABASE_URL),
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=10,
        open=True,
    )


@lru_cache()
def get_sqlalchemy_engine() -> Engine:
    return create_engine(sqlalchemy_url(get_settings().DATABASE_URL), pool_pre_ping=True)


@lru_cache()
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_sqlalchemy_engine(), expire_on_commit=False)


def get_connection() -> Iterator[DatabaseConnection]:
    """FastAPI dependency yielding a pooled Postgres connection."""
    with get_connection_pool().connection() as connection:
        yield connection


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a SQLAlchemy ORM session."""
    with get_session_factory() as session:
        yield session


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    app_root = Path(__file__).resolve().parents[3]
    config = Config(str(app_root / "alembic.ini"))
    config.set_main_option("script_location", str(app_root / "migrations"))
    with psycopg.connect(psycopg_conninfo(get_settings().DATABASE_URL)) as connection:
        connection.execute("SELECT pg_advisory_lock(%s, %s)", _MIGRATION_LOCK_KEY)
        try:
            command.upgrade(config, "head")
        finally:
            connection.execute("SELECT pg_advisory_unlock(%s, %s)", _MIGRATION_LOCK_KEY)


def init_db() -> None:
    """Create or update the Postgres schema owned by the copilot service."""
    _run_alembic_upgrade()
