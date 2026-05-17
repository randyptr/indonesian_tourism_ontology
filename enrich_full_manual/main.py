"""Apply curated_data.py to a populated ontology graph.

No SPARQL, no DBpedia. Reads from curated_data.py and writes triples.
Run order matters where noted in `enrich_all`.
"""

import logging

from rdflib import Literal, RDF, XSD

from config import ONT, PROVINCES, ACTIVITIES
from graph_utils import add_individual, add_relation, has_type, local_name
from curated_data import (
    ISLAND_TO_PROVINCE, EXTRA_CITIES, EXTRA_LINKS, VISITOR_COUNTS,
    PARKS_MANUAL, BEACHES_MANUAL,
    TRADITIONAL_DANCES, TRADITIONAL_HOUSES,
    RELIGIOUS_CEREMONIES, TEMPLES, FESTIVALS, TRANSPORTATION,
    RATINGS, ENTRY_FEE, PARK_ESTABLISHED_YEAR,
)

log = logging.getLogger(__name__)


CAPITAL_OF_PROVINCE = {
    "Bali":               "Denpasar",
    "West_Nusa_Tenggara": "Mataram",
    "East_Nusa_Tenggara": "Kupang",
}

ACTIVITY_OWL_CLASS = {
    "Surfing":      "WaterSport",
    "Snorkeling":   "WaterSport",
    "Diving":       "WaterSport",
    "Sailing":      "WaterSport",
    "Kayaking":     "WaterSport",
    "Hiking":       "MountainSport",
    "Sightseeing":  "Activities",
    "Cultural_Tour": "Activities",
}

WATER_SPORTS = ["Surfing", "Snorkeling", "Sailing", "Kayaking"]

TOURIST_ATTRACTION_CLASSES = (
    "Beach", "Park", "Volcano", "Museum", "Temple",
    "Festival", "ReligiousCeremony",
    "TraditionalDance", "TraditionalHouse",
)

# (curated_list, owl_class, default_activities)
CURATED_GROUPS = (
    (PARKS_MANUAL,         "Park",              ("Sightseeing", "Hiking")),
    (BEACHES_MANUAL,       "Beach",             tuple(WATER_SPORTS)),
    (TRADITIONAL_DANCES,   "TraditionalDance",  ("Cultural_Tour",)),
    (TRADITIONAL_HOUSES,   "TraditionalHouse",  ("Cultural_Tour",)),
    (RELIGIOUS_CEREMONIES, "ReligiousCeremony", ("Cultural_Tour",)),
    (TEMPLES,              "Temple",            ("Cultural_Tour",)),
    (FESTIVALS,            "Festival",          ("Cultural_Tour", "Sightseeing")),
)

# Fallback activities for DBpedia-populated attractions that no other step covers.
FALLBACK_ACTIVITIES = {
    "Beach":   WATER_SPORTS,
    "Park":    ["Sightseeing", "Hiking"],
    "Museum":  ["Cultural_Tour"],
    "Temple":  ["Cultural_Tour"],
    "Volcano": ["Hiking", "Sightseeing"],
}


def enrich_all(graph) -> None:
    """Run every enrichment step in order."""
    _add_backbone(graph)
    _link_islands_to_provinces(graph)
    _create_activity_individuals(graph)
    _add_extra_cities(graph)
    _add_curated_attractions(graph)
    _add_transportation(graph)
    _attach_fallback_activities(graph)
    _add_capital_hubs(graph)
    _add_data_properties(graph)
    _apply_extra_links(graph)


def _add_backbone(graph) -> None:
    """Country + 3 provinces, plus Bali_Island (DBpedia types Bali as Province)."""
    log.info("[Backbone]")
    add_individual(graph, "Country", "Indonesia")
    for province in PROVINCES.values():
        add_individual(graph, "Province", province)
        add_relation(graph, province, "locatedInCountry", "Indonesia")
    add_individual(graph, "Island", "Bali_Island")
    add_relation(graph, "Bali_Island", "locatedInProvince", "Bali")


def _link_islands_to_provinces(graph) -> None:
    log.info("[Island -> Province]")
    for island, province in ISLAND_TO_PROVINCE.items():
        if has_type(graph, island, "Island"):
            add_relation(graph, island, "locatedInProvince", province)


def _create_activity_individuals(graph) -> None:
    """Each activity is typed as its parent class to avoid OWL punning."""
    log.info("[Activity Individuals]")
    for activity in ACTIVITIES:
        owl_class = ACTIVITY_OWL_CLASS.get(activity, "Activities")
        add_individual(graph, owl_class, activity)


def _add_extra_cities(graph) -> None:
    log.info("[Extra Cities]")
    for entry in EXTRA_CITIES:
        name = entry["name"]
        if has_type(graph, name, "City"):
            continue
        add_individual(graph, "City", name)
        add_relation(graph, name, "locatedIn",         entry["locatedIn"])
        add_relation(graph, name, "locatedInIsland",   entry["locatedInIsland"])
        add_relation(graph, name, "locatedInProvince", entry["locatedInProvince"])


def _add_curated_attractions(graph) -> None:
    """All cultural individual lists share the same shape."""
    log.info("[Curated Attractions]")
    for entries, owl_class, activities in CURATED_GROUPS:
        for entry in entries:
            _create_attraction(graph, entry, owl_class, activities)


def _create_attraction(graph, entry, owl_class, activities) -> None:
    name     = entry["name"]
    province = entry["locatedIn"]
    add_individual(graph, owl_class, name)
    add_relation(graph, name, "locatedIn", province)
    for activity in activities:
        add_relation(graph, name, "hasActivity", activity)
    capital = CAPITAL_OF_PROVINCE.get(province)
    if capital and has_type(graph, capital, "City"):
        add_relation(graph, capital, "hasTouristAttraction", name)


def _add_transportation(graph) -> None:
    log.info("[Transportation]")
    for entry in TRANSPORTATION:
        name     = entry["name"]
        province = entry["locatedIn"]
        add_individual(graph, entry["type"], name)
        add_relation(graph, name, "locatedIn", province)
        capital = CAPITAL_OF_PROVINCE.get(province)
        if capital and has_type(graph, capital, "City"):
            add_relation(graph, capital, "hasTransportation", name)


def _attach_fallback_activities(graph) -> None:
    """Give every attraction at least one hasActivity edge."""
    log.info("[Fallback Activities]")
    for cls, activities in FALLBACK_ACTIVITIES.items():
        for subj, _, _ in graph.triples((None, RDF.type, ONT[cls])):
            if any(graph.triples((subj, ONT.hasActivity, None))):
                continue
            name = local_name(subj)
            for activity in activities:
                add_relation(graph, name, "hasActivity", activity)


def _add_capital_hubs(graph) -> None:
    """Capital city -> attractions / accommodations in the same province."""
    log.info("[Capital Hubs]")
    for province, capital in CAPITAL_OF_PROVINCE.items():
        if not has_type(graph, capital, "City"):
            continue
        for cls in TOURIST_ATTRACTION_CLASSES:
            for subj, _, _ in graph.triples((None, RDF.type, ONT[cls])):
                if (subj, ONT.locatedIn, ONT[province]) in graph:
                    graph.add((ONT[capital], ONT.hasTouristAttraction, subj))
        for subj, _, _ in graph.triples((None, RDF.type, ONT.Hotel)):
            if (subj, ONT.locatedIn, ONT[province]) in graph:
                graph.add((ONT[capital], ONT.hasAccommodation, subj))


def _add_data_properties(graph) -> None:
    """hasRating, hasEntryFee, establishedYear, numberOfVisitors from curated_data."""
    log.info("[Data Properties]")
    for cls, ratings in RATINGS.items():
        for individual, value in ratings.items():
            if has_type(graph, individual, cls):
                graph.add((ONT[individual], ONT.hasRating,
                           Literal(value, datatype=XSD.decimal)))

    for individual, flag in ENTRY_FEE.items():
        if (ONT[individual], None, None) in graph:
            graph.add((ONT[individual], ONT.hasEntryFee,
                       Literal(bool(flag), datatype=XSD.boolean)))

    for park, year in PARK_ESTABLISHED_YEAR.items():
        if has_type(graph, park, "Park"):
            graph.add((ONT[park], ONT.establishedYear,
                       Literal(int(year), datatype=XSD.integer)))

    for park, count in VISITOR_COUNTS.items():
        if has_type(graph, park, "Park"):
            graph.add((ONT[park], ONT.numberOfVisitors,
                       Literal(int(count), datatype=XSD.integer)))


def _apply_extra_links(graph) -> None:
    log.info("[Extra Links]")
    for s, p, o in EXTRA_LINKS:
        add_relation(graph, s, p, o)


__all__ = ["enrich_all", "CAPITAL_OF_PROVINCE"]
