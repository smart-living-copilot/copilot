from __future__ import annotations

from typing import Protocol


class _ResourceHealthRepo(Protocol):
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
    if hasattr(repo, "set_job_resource_health"):
        await repo.set_job_resource_health(  # type: ignore[attr-defined]
            job_id,
            resource=resource,
            status=status,
            message=message,
        )
