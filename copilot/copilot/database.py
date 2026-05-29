from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from copilot.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache()
def get_engine():
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        future=True,
    )


@lru_cache()
def get_session_factory():
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def init_db() -> None:
    Base.metadata.create_all(get_engine())
