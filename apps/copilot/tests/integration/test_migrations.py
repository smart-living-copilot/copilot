from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest

pytestmark = pytest.mark.integration


def _alembic_config() -> Config:
    app_root = Path(__file__).resolve().parents[2]
    config = Config(str(app_root / "alembic.ini"))
    config.set_main_option("script_location", str(app_root / "migrations"))
    return config


def test_alembic_metadata_has_no_pending_schema_drift(jobs_integration_environment) -> None:
    command.check(_alembic_config())
