from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from wotbot.core.database import DatabaseConnection, get_session_factory


def get_db_connection(request: Request) -> Iterator[DatabaseConnection]:
    connection_pool = request.app.state.connection_pool
    with connection_pool.connection() as connection:
        yield connection


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory = getattr(request.app.state, "orm_session_factory", None)
    if session_factory is None:
        session_factory = get_session_factory()

    with session_factory() as session:
        yield session


def verify_internal_api_key(request: Request) -> None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None or not settings.internal_api_key:
        return

    expected = f"Bearer {settings.internal_api_key}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


DatabaseDep = Annotated[DatabaseConnection, Depends(get_db_connection)]
SessionDep = Annotated[Session, Depends(get_db_session)]
