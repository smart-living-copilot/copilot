"""Export the copilot <-> virtual-servient wire contract as JSON Schema.

The servient consumes a narrow view of a virtual Thing definition
(:class:`VirtualThingServientView`). Rather than hand-maintaining the matching
TypeScript types in two places, we treat the Pydantic model as the single source
of truth and generate the servient's ``types.generated.ts`` from this schema.

Usage::

    python -m copilot.virtual_things.contract_export            # print schema
    python -m copilot.virtual_things.contract_export <out.json>  # write schema

A drift check regenerates the schema and the derived TypeScript and fails if the
working tree changed (see ``apps/virtual-servient`` ``gen:types`` script).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from copilot.virtual_things.schemas import VirtualThingServientView


def servient_contract_schema() -> dict[str, Any]:
    """Return the JSON Schema for the servient-facing definition view."""
    schema = VirtualThingServientView.model_json_schema()
    # json-schema-to-typescript names the root type after ``title``; pin it so the
    # generated type is stable regardless of Pydantic's defaulting.
    schema["title"] = "VirtualThingServientView"
    return schema


def main(argv: list[str]) -> int:
    schema = servient_contract_schema()
    payload = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if len(argv) > 1:
        Path(argv[1]).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
