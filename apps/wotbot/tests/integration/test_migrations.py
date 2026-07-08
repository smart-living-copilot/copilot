from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
import pytest

pytestmark = pytest.mark.integration


def _alembic_config() -> Config:
    # Mirror the runtime: the config + migrations ship inside the package and the
    # ini resolves ``script_location`` via ``%(here)s``.
    return Config(str(files("wotbot") / "alembic.ini"))


def test_alembic_metadata_has_no_pending_schema_drift(jobs_integration_environment) -> None:
    command.check(_alembic_config())
