from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from copilot.core.database import DatabaseConnection


def get_db_connection(request: Request) -> Iterator[DatabaseConnection]:
    connection_pool = request.app.state.connection_pool
    with connection_pool.connection() as connection:
        yield connection


DatabaseDep = Annotated[DatabaseConnection, Depends(get_db_connection)]
