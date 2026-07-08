"""Virtual Thing definition, binding, dispatch, and validation support.

The package owns wotbot's abstract virtual Thing model: persisted Thing
Descriptions, incremental affordance authoring, per-affordance bindings, computed
handler execution, emitted event evaluation, explicit emission requests, and the
internal API used by virtual-servient. Materialized record Things are registered
here as ``record`` bindings, while standalone computed and emitted Things use
handler code executed through code-executor.
"""

from wotbot.virtual_things.dispatcher import VirtualThingDispatcher
from wotbot.virtual_things.handler import VirtualThingHandlerError
from wotbot.virtual_things.ids import (
    VIRTUAL_THING_PREFIX,
    is_virtual_thing_id,
    make_virtual_thing_id,
)
from wotbot.virtual_things.schemas import (
    DefineVirtualThingRequest,
    VirtualThingBindingSpec,
    VirtualThingCapability,
    VirtualThingDefinition,
    VirtualThingTrigger,
)
from wotbot.virtual_things.store import VirtualThingStore
from wotbot.virtual_things.validator import VirtualThingValidator

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
