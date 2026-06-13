"""Virtual Thing definition, binding, dispatch, and validation support.

The package owns copilot's abstract virtual Thing model: persisted Thing
Descriptions, incremental affordance authoring, per-affordance bindings, computed
handler execution, emitted event evaluation, explicit emission requests, and the
internal API used by virtual-servient. Materialized record Things are registered
here as ``record`` bindings, while standalone computed and emitted Things use
handler code executed through code-executor.
"""

from copilot.virtual_things.dispatcher import VirtualThingDispatcher
from copilot.virtual_things.handler import VirtualThingHandlerError
from copilot.virtual_things.ids import (
    VIRTUAL_THING_PREFIX,
    is_virtual_thing_id,
    make_virtual_thing_id,
)
from copilot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingBindingSpec,
    VirtualThingCapability,
    VirtualThingDefinition,
    VirtualThingTrigger,
)
from copilot.virtual_things.store import VirtualThingStore
from copilot.virtual_things.validator import VirtualThingValidator

__all__ = [
    "VIRTUAL_THING_PREFIX",
    "DefineVirtualThingRequest",
    "VirtualThingBindingSpec",
    "VirtualThingCapability",
    "VirtualThingDefinition",
    "VirtualThingDispatcher",
    "VirtualThingHandlerError",
    "VirtualThingStore",
    "VirtualThingTrigger",
    "VirtualThingValidator",
    "is_virtual_thing_id",
    "make_virtual_thing_id",
]
