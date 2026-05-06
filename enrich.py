"""Enrich the graph with relational triples after population.

Population only adds rdf:type (and a single locatedIn → Province for some
classes). Without object-property triples, individuals are isolated in the
graph. This module injects:

    • Country backbone           Province → locatedInCountry → Indonesia
    • Island ↔ Province          Island   → locatedInProvince → Province
    • City → Island              City     → locatedInIsland → Island
    • Park/Volcano/Museum/...    → locatedIn → Province + Island
    • TouristAttraction graph    City     → hasTouristAttraction → ...
    • Activity vocabulary        Beach/Park/Volcano/Museum → hasActivity → Activity

Each step is a small, self-contained function so callers can skip / reorder.
All domain knowledge lives in `config.py`.

Schema constraints honored:
    • locatedInIsland  domain=City — used only for City individuals.
    • hasActivity      domain=TouristAttraction, range=Activities (plural).
    • Hotel ⊑ Accommodation (disjoint with TouristAttraction) — never object
      of hasTouristAttraction or hasActivity.
    • hasAccommodation skipped entirely: it is owl:equivalentProperty to
      travel.owl#hasAccommodation whose domain (travel:Destination) clashes
      with our City and triggers an inconsistency.
    • originatesFrom skipped: schema declares its domain as Food.
"""

import logging

from rdflib import Graph, RDF

from config import (
    ONT, PROVINCES, CAPITAL_OF_PROVINCE,
    ISLAND_TO_PROVINCE, CITY_TO_ISLAND, BEACH_TO_ISLAND,
    BEACH_TO_PROVINCE, PARK_LOCATION, VOLCANO_LOCATION,
    ACTIVITIES, ACTIVITY_LINKS, EXTRA_ACTIVITY_LINKS,
    TOURIST_ATTRACTION_CLASSES,
)
from graph_utils import add_individual, add_rel, has_type, local_name

log = logging.getLogger(__name__)


# ── 1. Country & Province backbone ────────────────────────────────────────────
def add_country_backbone(g: Graph) -> None:
    add_individual(g, "Country", "Indonesia")
    for prov_full in PROVINCES.values():
        add_individual(g, "Province", prov_full)
        add_rel(g, prov_full, "locatedInCountry", "Indonesia")


# ── 2. Islands ────────────────────────────────────────────────────────────────
def add_islands(g: Graph) -> None:
    """Bali_Island doesn't come from DBpedia (Bali is a Province there);
    add it manually, then wire every Island to its Province."""
    add_individual(g, "Island", "Bali_Island")
    for island, prov in ISLAND_TO_PROVINCE.items():
        if has_type(g, island, "Island"):
            add_rel(g, island, "locatedInProvince", prov)


# ── 3. Cities → Island ────────────────────────────────────────────────────────
def add_city_islands(g: Graph) -> None:
    for city, island in CITY_TO_ISLAND.items():
        if (ONT[city], None, None) in g:
            add_rel(g, city, "locatedInIsland", island)


# ── 4-9. Attractions → Province + Island (using `locatedIn` parent property) ─
def add_beach_locations(g: Graph) -> None:
    for beach, island in BEACH_TO_ISLAND.items():
        if has_type(g, beach, "Beach"):
            add_rel(g, beach, "locatedIn", island)
    for beach, prov in BEACH_TO_PROVINCE.items():
        if has_type(g, beach, "Beach"):
            add_rel(g, beach, "locatedIn", prov)

def add_park_locations(g: Graph) -> None:
    for park, (prov, island) in PARK_LOCATION.items():
        if has_type(g, park, "Park"):
            add_rel(g, park, "locatedIn", prov)
            add_rel(g, park, "locatedIn", island)

def add_volcano_locations(g: Graph) -> None:
    for volcano, (prov, island) in VOLCANO_LOCATION.items():
        if has_type(g, volcano, "Volcano"):
            add_rel(g, volcano, "locatedIn", prov)
            add_rel(g, volcano, "locatedIn", island)

def _add_bali_locations_for_class(g: Graph, cls: str, *, also_island: bool) -> None:
    """Generic helper: every individual of `cls` is in Bali (the population
    queries for Museum/Festival/Hotel target Bali only)."""
    for s, _, _ in g.triples((None, RDF.type, ONT[cls])):
        name = local_name(s)
        add_rel(g, name, "locatedIn", "Bali")
        if also_island:
            add_rel(g, name, "locatedIn", "Bali_Island")

def add_museum_locations(g: Graph) -> None:
    _add_bali_locations_for_class(g, "Museum", also_island=True)

def add_temple_locations(g: Graph) -> None:
    """Temples are all from Bali queries — add province + island."""
    _add_bali_locations_for_class(g, "Temple", also_island=True)

def add_festival_locations(g: Graph) -> None:
    _add_bali_locations_for_class(g, "Festival", also_island=False)

def add_hotel_locations(g: Graph) -> None:
    _add_bali_locations_for_class(g, "Hotel", also_island=True)


# ── 10. Activity vocabulary ───────────────────────────────────────────────────
def add_activities(g: Graph) -> None:
    """Create Activity individuals (typed Activities, plural) and link them
    to relevant attractions via hasActivity."""
    for act in ACTIVITIES:
        add_individual(g, "Activities", act)

    # Specific attraction → activity links (Beach→Surfing, Park→Sightseeing, …)
    for act, (attr_class, items) in ACTIVITY_LINKS.items():
        targets = items
        if targets is None:  # link to every individual of attr_class
            targets = [local_name(s)
                       for s, _, _ in g.triples((None, RDF.type, ONT[attr_class]))]
        for item in targets:
            if has_type(g, item, attr_class):
                add_rel(g, item, "hasActivity", act)

    # Class-wide activity links (Temple→Cultural_Tour, Festival→Cultural_Tour, …)
    for cls, acts in EXTRA_ACTIVITY_LINKS.items():
        for s, _, _ in g.triples((None, RDF.type, ONT[cls])):
            name = local_name(s)
            for act in acts:
                add_rel(g, name, "hasActivity", act)


# ── 11. City → hasTouristAttraction (hub edges) ──────────────────────────────
def add_tourist_attraction_hub(g: Graph) -> None:
    """Each capital city is linked to every TouristAttraction in its province.
    Hotel is excluded (it's Accommodation, disjoint with TouristAttraction)."""
    for prov_name, capital in CAPITAL_OF_PROVINCE.items():
        if not has_type(g, capital, "City"):
            continue
        for cls in TOURIST_ATTRACTION_CLASSES:
            for s, _, _ in g.triples((None, RDF.type, ONT[cls])):
                if (s, ONT.locatedIn, ONT[prov_name]) in g:
                    g.add((ONT[capital], ONT.hasTouristAttraction, s))


# ── Public API ────────────────────────────────────────────────────────────────
ALL_ENRICHERS = [
    add_country_backbone,
    add_islands,
    add_city_islands,
    add_beach_locations,
    add_park_locations,
    add_volcano_locations,
    add_museum_locations,
    add_temple_locations,
    add_festival_locations,
    add_hotel_locations,
    add_activities,
    add_tourist_attraction_hub,
]


def enrich_all(g: Graph) -> None:
    """Run every enrichment step in order."""
    for fn in ALL_ENRICHERS:
        fn(g)
