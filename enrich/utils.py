"""Shared helpers and constants used across enrich submodules."""

import time
import logging

from rdflib import Graph, RDF, OWL
from SPARQLWrapper import SPARQLWrapper, JSON

from config import ONT_IRI, DBPEDIA_ENDPOINT, DBPEDIA_TIMEOUT_S, DBPEDIA_THROTTLE_S
from graph_utils import add_individual, add_relation, has_type, local_name  # noqa: F401
from populate import get_dbpedia_mappings  # noqa: F401

log = logging.getLogger(__name__)

# DBpedia resource prefix (used to construct URIs from local names)
_DBP_RESOURCE = "http://dbpedia.org/resource/"

# Maximum entities per SPARQL VALUES clause (prevents query timeouts)
_SPARQL_CHUNK_SIZE = 50

# Classes that are subclasses of TouristAttraction in our schema.
# Hotel is deliberately excluded: Hotel ⊑ Accommodation ⊥ TouristAttraction.
TOURIST_ATTRACTION_CLASSES = {
    "Beach", "Park", "Volcano", "Museum", "Temple",
    "Festival", "ReligiousCeremony",
    "TraditionalDance", "TraditionalHouse",
}

# Maps a keyword (searched in DBpedia category URIs) to our Activity individual.
CATEGORY_TO_ACTIVITY = {
    # WaterSport
    "surf":     "Surfing",
    "snorkel":  "Snorkeling",
    "diving":   "Diving",
    "scuba":    "Diving",
    "sail":     "Sailing",
    "kayak":    "Kayaking",
    # MountainSport
    "hik":      "Hiking",
    "trek":     "Hiking",
    # Sightseeing / Cultural
    "sight":    "Sightseeing",
    "cultur":   "Cultural_Tour",
    "museum":   "Cultural_Tour",
    "temple":   "Cultural_Tour",
    "ceremon":  "Cultural_Tour",
    "ritual":   "Cultural_Tour",
    "festival": "Cultural_Tour",
}

# Maps DBpedia resource URIs to our Activity individuals.
DBPEDIA_RESOURCE_TO_ACTIVITY = {
    f"{_DBP_RESOURCE}Surfing":      "Surfing",
    f"{_DBP_RESOURCE}Snorkeling":   "Snorkeling",
    f"{_DBP_RESOURCE}Scuba_diving": "Diving",
    f"{_DBP_RESOURCE}Sailing":      "Sailing",
    f"{_DBP_RESOURCE}Kayaking":     "Kayaking",
    f"{_DBP_RESOURCE}Hiking":       "Hiking",
}

# Maps each activity name to its specific OWL leaf class in schema.owl.
ACTIVITY_OWL_CLASS: dict[str, str] = {
    "Surfing":       "Surfing",
    "Snorkeling":    "Snorkeling",
    "Diving":        "Diving",
    "Sailing":       "Sailing",
    "Kayaking":      "Kayaking",
    "Hiking":        "Hiking",
    "Sightseeing":   "Activities",   # no dedicated leaf class in schema
    "Cultural_Tour": "Activities",   # no dedicated leaf class in schema
}

# When DBpedia provides no activity info, assign these defaults by class.
DEFAULT_ACTIVITIES_BY_CLASS = {
    "Beach":             ["Surfing", "Snorkeling", "Sailing", "Kayaking"],
    "Temple":            ["Cultural_Tour"],
    "Museum":            ["Cultural_Tour"],
    "Festival":          ["Cultural_Tour", "Sightseeing"],
    "ReligiousCeremony": ["Cultural_Tour"],
    "Park":              ["Sightseeing", "Hiking"],
    "TraditionalDance":  ["Cultural_Tour"],
    "TraditionalHouse":  ["Cultural_Tour"],
}

# Capital city per province (used for hasTouristAttraction hub edges).
CAPITAL_OF_PROVINCE = {
    "Bali":               "Denpasar",
    "West_Nusa_Tenggara": "Mataram",
    "East_Nusa_Tenggara": "Kupang",
}

# ─────────────────────────────────────────────────────────────────────────────
# SPARQL helpers
# ─────────────────────────────────────────────────────────────────────────────
_sparql = SPARQLWrapper(DBPEDIA_ENDPOINT)
_sparql.setReturnFormat(JSON)
_sparql.setTimeout(DBPEDIA_TIMEOUT_S)


def _run_sparql(query: str) -> list[dict]:
    """Execute a SPARQL query against DBpedia and return the result bindings.

    Returns an empty list on timeout or any other error, so callers
    don't need to handle exceptions.
    """
    _sparql.setQuery(query)
    try:
        return _sparql.query().convert()["results"]["bindings"]
    except Exception as error:
        log.warning("Enrichment query failed: %s", error)
        return []
    finally:
        time.sleep(DBPEDIA_THROTTLE_S)


def _make_values_clause(uris: list[str]) -> str:
    """Build a SPARQL VALUES string like '<uri1> <uri2> <uri3>'.

    Example:
        >>> _make_values_clause(["http://dbpedia.org/resource/Bali"])
        '<http://dbpedia.org/resource/Bali>'
    """
    return " ".join(f"<{uri}>" for uri in uris)


# ─────────────────────────────────────────────────────────────────────────────
# Graph inspection helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get_all_individual_names(graph: Graph) -> set[str]:
    """Return the local names (after '#') of all ontology individuals."""
    names: set[str] = set()
    for subject, _, _ in graph.triples((None, RDF.type, None)):
        iri = str(subject)
        if iri.startswith(ONT_IRI):
            names.add(iri[len(ONT_IRI):])
    return names


def _get_ontology_class(graph: Graph, individual_name: str) -> str | None:
    """Return the ontology class name for an individual, or None."""
    from config import ONT
    for _, _, type_uri in graph.triples((ONT[individual_name], RDF.type, None)):
        type_str = str(type_uri)
        if type_str.startswith(ONT_IRI) and type_uri != OWL.NamedIndividual:
            return type_str[len(ONT_IRI):]
    return None


def _collect_entities_by_class(
    graph: Graph,
    target_classes: set[str],
    local_to_dbpedia: dict[str, str],
) -> dict[str, str]:
    """Collect entities of specific classes that have DBpedia URIs.

    Returns:
        dict mapping DBpedia URI -> ontology local name.
    """
    all_names = _get_all_individual_names(graph)
    result: dict[str, str] = {}

    for name in all_names:
        entity_class = _get_ontology_class(graph, name)
        if entity_class in target_classes and name in local_to_dbpedia:
            dbpedia_uri = local_to_dbpedia[name]
            result[dbpedia_uri] = name

    return result


def _add_cultural_individuals(
    graph: Graph,
    entries: list[dict],
    owl_class: str,
    label: str,
    activities: list[str] | None = None,
) -> None:
    """Shared helper for TouristAttraction subclass population.

    Each entry gets rdf:type, locatedIn, one or more hasActivity links, and a
    hub link from the provincial capital. Hub links are wired manually here
    because add_attraction_hubs() runs before these manual steps.

    activities defaults to ["Cultural_Tour"] if not specified.
    """
    if activities is None:
        activities = ["Cultural_Tour"]
    count = 0
    for entry in entries:
        name     = entry["name"]
        province = entry["locatedIn"]
        add_individual(graph, owl_class, name)
        add_relation(graph, name, "locatedIn", province)
        for activity in activities:
            add_relation(graph, name, "hasActivity", activity)
        capital = CAPITAL_OF_PROVINCE.get(province)
        if capital and has_type(graph, capital, "City"):
            add_relation(graph, capital, "hasTouristAttraction", name)
        count += 1
    log.info("  -> %d individuals added", count)
