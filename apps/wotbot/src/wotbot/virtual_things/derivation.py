"""Declare the derivation of computed affordances inside the Thing Description.

A ``computed`` property or action derives its value from the real Things its handler
reads through the injected ``wot`` client. That dependency is already extracted for
capability scoping (see :mod:`wotbot.virtual_things.capabilities`); here we also record
it *in the TD itself* as a PROV-O ``prov:wasDerivedFrom`` edge from the affordance to
each source Thing. A derived Thing then becomes self-describing: the dependency is a
real edge in the RDF graph, discoverable with ``things_sparql`` instead of buried in
handler code.

Only Things the handler *reads* (``readProperty``) count as derivation inputs, so the
provenance claim stays honest — an action that merely invokes another Thing is acting,
not deriving a value, and gets no edge.

The ``prov`` namespace is injected as an inline ``@context`` prefix map, never a remote
context URL: the RDF materializer (see :mod:`wotbot.rdf.contexts`) only resolves the
TD 1.1 context remotely and rejects any other remote context. This mirrors how the
enrichment flow injects the SAREF/SOSA/QUDT prefixes.
"""

from __future__ import annotations

from typing import Any

PROV_PREFIX = "prov"
PROV_NAMESPACE = "http://www.w3.org/ns/prov#"
DERIVED_FROM = "prov:wasDerivedFrom"

_SECTION_BY_AFFORDANCE = {"property": "properties", "action": "actions"}


def annotate_computed_derivations(td: dict[str, Any], bindings: list[Any]) -> dict[str, Any]:
    """Return the TD with a ``prov:wasDerivedFrom`` edge per computed affordance.

    For each ``computed`` binding, link its affordance to the source Things the handler
    reads (taken from the binding's resolved ``capabilities``). The TD is returned
    unchanged when no binding contributes a read source, so the annotation never lies.
    """
    result = dict(td)
    annotated_any = False
    for binding in bindings:
        if getattr(binding, "kind", None) != "computed":
            continue
        section = _SECTION_BY_AFFORDANCE.get(getattr(binding, "affordance_type", ""))
        if section is None:
            continue
        sources = _read_sources(binding)
        if not sources:
            continue
        affordances = result.get(section)
        if not isinstance(affordances, dict):
            continue
        target = affordances.get(binding.affordance_name)
        if not isinstance(target, dict):
            continue
        updated = dict(affordances)
        updated[binding.affordance_name] = _with_derived_from(target, sources)
        result[section] = updated
        annotated_any = True

    if annotated_any:
        result = ensure_prov_context(result)
    return result


def ensure_prov_context(td: dict[str, Any]) -> dict[str, Any]:
    """Ensure the TD ``@context`` carries the ``prov`` prefix as an inline prefix map."""
    context = td.get("@context")
    if isinstance(context, list):
        items = list(context)
    elif context is None:
        items = []
    else:
        items = [context]

    new_items: list[Any] = []
    injected = False
    for item in items:
        if isinstance(item, dict) and not injected:
            item = {**item, PROV_PREFIX: PROV_NAMESPACE}
            injected = True
        new_items.append(item)
    if not injected:
        new_items.append({PROV_PREFIX: PROV_NAMESPACE})

    result = dict(td)
    result["@context"] = new_items
    return result


def _read_sources(binding: Any) -> list[str]:
    sources: list[str] = []
    for capability in getattr(binding, "capabilities", None) or []:
        ops = getattr(capability, "ops", None) or []
        if "readProperty" in ops:
            thing_id = getattr(capability, "thing_id", None)
            if isinstance(thing_id, str) and thing_id and thing_id not in sources:
                sources.append(thing_id)
    return sources


def _with_derived_from(target: dict[str, Any], sources: list[str]) -> dict[str, Any]:
    annotated = dict(target)
    refs = _as_ref_list(annotated.get(DERIVED_FROM))
    seen = {ref.get("@id") for ref in refs if isinstance(ref, dict)}
    for thing_id in sources:
        if thing_id not in seen:
            refs.append({"@id": thing_id})
            seen.add(thing_id)
    annotated[DERIVED_FROM] = refs
    return annotated


def _as_ref_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value]
    if isinstance(value, dict):
        return [value]
    return []
