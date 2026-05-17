"""ALL_ENRICHERS list and enrich_all() orchestrator."""

import logging

from rdflib import Graph

from enrich.backbone import add_country_backbone, add_bali_island
from enrich.relations import (
    add_island_province,
    add_location_links,
    add_activity_individuals,
    add_activity_links,
    add_activity_fallbacks,
    add_attraction_hubs,
    add_accommodation_hubs,
)
from enrich.properties import (
    add_manual_parks,
    add_visitor_counts,
    add_curated_ratings,
    add_curated_entry_fees,
    add_park_established_years,
)
from enrich.manual import (
    add_manual_transportation,
    add_manual_festivals,
    add_manual_traditional_dances,
    add_manual_traditional_houses,
    add_manual_beaches,
    add_manual_religious_ceremonies,
    add_manual_temples,
)

log = logging.getLogger(__name__)

ALL_ENRICHERS = [

    # Backbone
    "backbone",
    add_country_backbone,
    add_bali_island,

    # Relation enrichment (DBpedia)
    "relation",
    add_island_province,
    add_location_links,
    add_activity_individuals,
    add_activity_links,
    add_activity_fallbacks,
    add_attraction_hubs,
    add_accommodation_hubs,

    # Property enrichment (curated)
    "property",
    add_manual_parks,               
    add_visitor_counts,
    add_curated_ratings,
    add_curated_entry_fees,
    add_park_established_years,

    # Manual individuals (curated_data)
    "manual",
    add_manual_transportation,
    add_manual_festivals,
    add_manual_traditional_dances,
    add_manual_traditional_houses,
    add_manual_beaches,
    add_manual_religious_ceremonies,
    add_manual_temples,
]

_PHASE_LABELS = {
    "backbone": "Backbone",
    "relation": "Relation Enrichment  (DBpedia)",
    "property": "Property Enrichment  (curated)",
    "manual":   "Manual Individuals   (curated_data)",
}


def enrich_all(graph: Graph) -> None:
    """Run all enrichment steps in order.

    Each step is independent and can be skipped/reordered, except:
        - add_activity_individuals must run before add_activity_links
        - add_activity_links must run before add_activity_fallbacks
        - add_location_links should run before add_attraction_hubs and
          add_accommodation_hubs (both hubs depend on locatedIn edges)
        - add_manual_parks must run before the three property steps
    """
    for step in ALL_ENRICHERS:
        if isinstance(step, str):
            log.info("")
            log.info("[%s]", _PHASE_LABELS.get(step, step))
        else:
            step(graph)
