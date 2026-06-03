"""Virtual record job utilities.

This package provides record schemas, identifier helpers, virtual-record persistence,
and Thing Description rendering used by prompt jobs that write structured
`VirtualRecord` output.
"""

from __future__ import annotations

from copilot.jobs.records.db import VirtualRecord, VirtualRecordThing
from copilot.jobs.records.http import virtual_record_http_error
from copilot.jobs.records.ids import (
    VIRTUAL_RECORD_THING_PREFIX,
    is_virtual_record_thing_id,
    make_virtual_record_thing_id,
)
from copilot.jobs.records.schema import validate_record_schema
from copilot.jobs.records.store import VirtualRecordStore
from copilot.jobs.records.td import build_virtual_record_td

__all__ = [
    "VIRTUAL_RECORD_THING_PREFIX",
    "VirtualRecord",
    "VirtualRecordStore",
    "VirtualRecordThing",
    "build_virtual_record_td",
    "is_virtual_record_thing_id",
    "make_virtual_record_thing_id",
    "validate_record_schema",
    "virtual_record_http_error",
]
