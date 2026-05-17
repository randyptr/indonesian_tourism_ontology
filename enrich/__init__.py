"""Auto-enrich the ontology graph by querying DBpedia for relationships.

After population, each individual only has rdf:type and one locatedIn edge.
This package discovers additional relationships automatically by querying
DBpedia's wikiPageWikiLink and dct:subject properties.

Enrichment pipeline (in order):
    1. add_country_backbone     — Province -> locatedInCountry -> Indonesia
    2. add_bali_island          — Create Bali_Island (DBpedia has "Bali" as Province)
    3. add_island_province      — Island -> locatedInProvince -> Province
    4. add_location_links       — entity -> locatedIn/locatedInIsland/locatedInCity (via wikiLink)
    5. add_activity_individuals — Create Activity individuals (Surfing, Diving, etc.)
    6. add_activity_links       — entity -> hasActivity -> Activity (via categories)
    7. add_activity_fallbacks   — Assign default activities to entities without any
    8. add_attraction_hubs      — City -> hasTouristAttraction -> TouristAttractions in province
    9. add_accommodation_hubs   — City -> hasAccommodation -> Hotels in same province
    10. add_visitor_counts      — TouristAttraction -> numberOfVisitors -> xsd:integer (from DBpedia)
    11. add_curated_ratings     — TouristAttraction -> hasRating -> xsd:decimal (curated)
    12. add_manual_transportation       — Transportation individuals + City -> hasTransportation links
    13. add_manual_festivals            — Festival individuals for NTB/NTT (DBpedia coverage is poor)
    14. add_manual_traditional_dances   — TraditionalDance individuals + hub links
    15. add_manual_traditional_houses   — TraditionalHouse individuals + hub links
    16. add_manual_beaches              — Beach individuals for NTB/NTT + Bali gaps
    17. add_manual_religious_ceremonies — ReligiousCeremony individuals (all 3 provinces)
    18. add_manual_temples              — Temple individuals (Bali supplements + NTB/NTT)
"""

# Re-export public API so all existing imports work unchanged:
#   from enrich import enrich_all, CAPITAL_OF_PROVINCE, ALL_ENRICHERS

from enrich.main import enrich_all, ALL_ENRICHERS, _PHASE_LABELS  # noqa: F401
from enrich.utils import CAPITAL_OF_PROVINCE  # noqa: F401

__all__ = [
    "enrich_all",
    "ALL_ENRICHERS",
    "_PHASE_LABELS",
    "CAPITAL_OF_PROVINCE",
]
