"""Semantic enrichment helpers for Thing Description metadata.

The package loads enrichment configuration and applies vocabulary/SHACL-backed
annotations used by catalog indexing and discovery workflows.
"""

from wotbot.catalog.enrichment.config import load_enrichment_config
from wotbot.catalog.enrichment.models import EnrichmentResult
from wotbot.catalog.enrichment.service import EnrichmentError, enrich_thing_document

__all__ = [
    "EnrichmentError",
    "EnrichmentResult",
    "enrich_thing_document",
    "load_enrichment_config",
]
