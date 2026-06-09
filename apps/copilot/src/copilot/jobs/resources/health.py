from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class _ResourceHealthRepo(Protocol):
    """Minimal store protocol needed to persist per-resource job health."""

    async def set_job_resource_health(
        self,
        job_id: str,
        *,
        resource: str,
        status: str,
        message: str | None = None,
    ) -> object: ...


async def mark_resource_health(
    repo: object,
    job_id: str,
    resource: str,
    status: str,
    message: str | None = None,
) -> None:
    if isinstance(repo, _ResourceHealthRepo):
        await repo.set_job_resource_health(
            job_id,
            resource=resource,
            status=status,
            message=message,
        )
