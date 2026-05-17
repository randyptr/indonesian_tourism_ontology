"""Auto-enrich the ontology graph by querying DBpedia and applying curated data.

After population, each individual only has rdf:type and one locatedIn edge.
This package discovers additional relationships automatically via DBpedia
SPARQL queries and supplements them with curated data from `curated_data.py`.

Phases (single source of truth for ordering: `enrich.main.ALL_ENRICHERS`):
    backbone  — Country/Island backbone (Bali fix)
    relation  — DBpedia-driven location, activity, and hub edges
    property  — visitor counts, ratings, entry fees, established years
    manual    — Curated individuals (transport, festivals, dances, houses,
                beaches, ceremonies, temples) and patches (extra cities/links)

Iterate ALL_ENRICHERS to see the exact callable order.
"""

# Re-export public API so all existing imports work unchanged:
#   from enrich import enrich_all, CAPITAL_OF_PROVINCE, ALL_ENRICHERS

from enrich.main import enrich_all, ALL_ENRICHERS, PHASE_LABELS
from enrich.utils import CAPITAL_OF_PROVINCE

__all__ = [
    "enrich_all",
    "ALL_ENRICHERS",
    "PHASE_LABELS",
    "CAPITAL_OF_PROVINCE",
]
