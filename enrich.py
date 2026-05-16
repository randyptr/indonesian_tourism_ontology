"""Auto-enrich the ontology graph by querying DBpedia for relationships.

After population, each individual only has rdf:type and one locatedIn edge.
This module discovers additional relationships automatically by querying
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
    11. add_curated_ratings     — TouristAttraction -> hasRating -> xsd:decimal (from curate_properties.py)
    12. add_manual_transportation       — Transportation individuals + City -> hasTransportation links
    13. add_manual_festivals            — Festival individuals for NTB/NTT (DBpedia coverage is poor)
    14. add_manual_traditional_dances   — TraditionalDance individuals + hub links
    15. add_manual_traditional_houses   — TraditionalHouse individuals + hub links
    16. add_manual_beaches              — Beach individuals for NTB/NTT + Bali gaps
    17. add_manual_religious_ceremonies — ReligiousCeremony individuals (all 3 provinces)
    18. add_manual_temples              — Temple individuals (Bali supplements + NTB/NTT)

Schema constraints we must respect:
    - locatedInIsland:   domain = City (only City can use this property)
    - locatedInProvince: domain = Island (only Island can use this property)
    - locatedInCity:     domain = TouristAttraction | Accommodation (attractions and hotels)
    - hasActivity:       domain = TouristAttraction, range = Activities
    - hasAccommodation:  domain = City, range = Accommodation
    - hasTouristAttraction: domain = City, range = TouristAttraction
    - Hotel is subclass of Accommodation, which is disjoint with TouristAttraction
      -> Hotel must NEVER be object of hasTouristAttraction or subject of hasActivity
      -> Hotel CAN be subject of locatedInCity (domain includes Accommodation)
"""

import time
import logging

from rdflib import Graph, RDF, OWL, Literal, XSD
from SPARQLWrapper import SPARQLWrapper, JSON

from config import (
    ONT, ONT_IRI, PROVINCES,
    DBPEDIA_ENDPOINT, DBPEDIA_TIMEOUT_S, DBPEDIA_THROTTLE_S,
    ACTIVITIES,
)
from graph_utils import add_individual, add_relation, has_type, local_name
from populate import get_dbpedia_mappings
from curated_data import (
    RATINGS, ENTRY_FEE, PARK_ESTABLISHED_YEAR,
    TRANSPORTATION, FESTIVALS,
    TRADITIONAL_DANCES, TRADITIONAL_HOUSES,
    BEACHES_MANUAL, RELIGIOUS_CEREMONIES, TEMPLES,
)

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
# Example: a beach with category "Surfing_locations_in_Indonesia" -> Surfing.
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
# Used for wikiPageWikiLink-based activity discovery.
# Example: if Komodo_National_Park links to dbr:Scuba_diving -> Diving.
DBPEDIA_RESOURCE_TO_ACTIVITY = {
    f"{_DBP_RESOURCE}Surfing":      "Surfing",
    f"{_DBP_RESOURCE}Snorkeling":   "Snorkeling",
    f"{_DBP_RESOURCE}Scuba_diving": "Diving",
    f"{_DBP_RESOURCE}Sailing":      "Sailing",
    f"{_DBP_RESOURCE}Kayaking":     "Kayaking",
    f"{_DBP_RESOURCE}Hiking":       "Hiking",
}

# Maps each activity name to its specific OWL leaf class in schema.owl.
# Activities with a dedicated subclass are typed precisely so HermiT infers
# the WaterSport / MountainSport grouping via subclass reasoning.
# Example: Surfing rdf:type Surfing -> HermiT infers WaterSport, Activities
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
# Example: every Temple gets Cultural_Tour if it had no DBpedia activity link.
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
    """Return the local names (after '#') of all ontology individuals.

    Example return: {"Pandawa_Beach", "Bali", "Mount_Agung", ...}
    """
    names: set[str] = set()
    for subject, _, _ in graph.triples((None, RDF.type, None)):
        iri = str(subject)
        if iri.startswith(ONT_IRI):
            names.add(iri[len(ONT_IRI):])
    return names


def _get_ontology_class(graph: Graph, individual_name: str) -> str | None:
    """Return the ontology class name for an individual, or None.

    Skips owl:NamedIndividual (every individual has this type).

    Example:
        >>> _get_ontology_class(g, "Pandawa_Beach")
        "Beach"
    """
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

    Example return: {
        "http://dbpedia.org/resource/Pandawa_Beach": "Pandawa_Beach",
        "http://dbpedia.org/resource/Mount_Agung": "Mount_Agung",
    }
    """
    all_names = _get_all_individual_names(graph)
    result: dict[str, str] = {}

    for name in all_names:
        entity_class = _get_ontology_class(graph, name)
        if entity_class in target_classes and name in local_to_dbpedia:
            dbpedia_uri = local_to_dbpedia[name]
            result[dbpedia_uri] = name

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Country backbone
# ─────────────────────────────────────────────────────────────────────────────
def add_country_backbone(graph: Graph) -> None:
    """Create Indonesia as Country and link the 3 provinces to it.

    Also explicitly re-asserts rdf:type ONT.Province for each province.
    populate_provinces() may type them with dbo:Province (DBpedia namespace)
    rather than ONT.Province — without this re-assertion, build_entity_type_map
    in graph_embedding.py won't find them (it filters by ONT_IRI prefix), so
    Province entities are invisible in the t-SNE plot and link predictions.

    Triples added (per province):
        Indonesia            rdf:type         Country
        <Province>           rdf:type         Province   ← guaranteed ONT namespace
        <Province>           locatedInCountry Indonesia
    """
    log.info("[Country Backbone]")
    add_individual(graph, "Country", "Indonesia")
    for province_name in PROVINCES.values():
        add_individual(graph, "Province", province_name)   # ensures ONT.Province type
        add_relation(graph, province_name, "locatedInCountry", "Indonesia")
    log.info("  -> 3 provinces typed as ONT.Province and linked to Indonesia")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Bali_Island (manual fix)
# ─────────────────────────────────────────────────────────────────────────────
def add_bali_island(graph: Graph) -> None:
    """Create Bali_Island as an Island individual.

    Why manual: DBpedia's "Bali" is typed as dbo:Province, not dbo:Island.
    But our ontology needs an Island entity for Bali so that City individuals
    in Bali can use locatedInIsland -> Bali_Island (domain = City).
    """
    log.info("[Bali Island Fix]")
    add_individual(graph, "Island", "Bali_Island")
    add_relation(graph, "Bali_Island", "locatedInProvince", "Bali")
    log.info("  + Bali_Island (DBpedia types Bali as Province, not Island)")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Island -> Province links
# ─────────────────────────────────────────────────────────────────────────────
def add_island_province(graph: Graph) -> None:
    """Link each Island to its Province using DBpedia's isPartOf and wikiLinks.

    Queries DBpedia for relationships between our Island individuals and
    our Province individuals. Uses locatedInProvince (domain = Island).

    Example result:
        Flores  locatedInProvince  East_Nusa_Tenggara
        Lombok  locatedInProvince  West_Nusa_Tenggara
    """
    log.info("[Island → Province Links]")
    dbpedia_to_local, local_to_dbpedia = get_dbpedia_mappings()
    all_names = _get_all_individual_names(graph)

    # Collect DBpedia URIs for our Island individuals
    island_dbpedia_uris = []
    for name in all_names:
        if has_type(graph, name, "Island") and name in local_to_dbpedia:
            island_dbpedia_uris.append(local_to_dbpedia[name])

    if not island_dbpedia_uris:
        return

    # Build DBpedia URIs for our 3 provinces
    province_dbpedia_uris = [
        f"{_DBP_RESOURCE}{province_name}"
        for province_name in PROVINCES.values()
    ]

    # Reverse lookup: DBpedia province URI -> our local name
    province_uri_to_local = {
        f"{_DBP_RESOURCE}{name}": name for name in PROVINCES.values()
    }

    # Query: which of our islands link to which of our provinces?
    results = _run_sparql(f"""
        SELECT ?island ?province WHERE {{
            VALUES ?island {{ {_make_values_clause(island_dbpedia_uris)} }}
            VALUES ?province {{ {_make_values_clause(province_dbpedia_uris)} }}
            {{ ?island <http://dbpedia.org/ontology/isPartOf> ?province }}
            UNION {{ ?island <http://dbpedia.org/ontology/wikiPageWikiLink> ?province }}
        }}
    """)

    # Add locatedInProvince triples for each match
    link_count = 0
    for row in results:
        island_uri = row["island"]["value"]
        province_uri = row["province"]["value"]
        island_name = dbpedia_to_local.get(island_uri)
        province_name = province_uri_to_local.get(province_uri)

        if island_name and province_name:
            add_relation(graph, island_name, "locatedInProvince", province_name)
            link_count += 1

    log.info("  -> %d links (DBpedia isPartOf + wikiLink)", link_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Auto-discover location links via wikiPageWikiLink
# ─────────────────────────────────────────────────────────────────────────────
def _build_location_targets(
    graph: Graph,
    local_to_dbpedia: dict[str, str],
) -> dict[str, str]:
    """Build a dict of DBpedia URI -> local name for all location entities.

    Location entities are Province, Island, and City individuals.
    These are the entities that other things can be "locatedIn".

    Returns:
        {"http://dbpedia.org/resource/Bali": "Bali",
         "http://dbpedia.org/resource/Flores": "Flores", ...}
    """
    location_classes = {"Province", "Island", "City"}
    all_names = _get_all_individual_names(graph)
    targets: dict[str, str] = {}

    for name in all_names:
        entity_class = _get_ontology_class(graph, name)
        if entity_class in location_classes and name in local_to_dbpedia:
            targets[local_to_dbpedia[name]] = name

    # Ensure all provinces are included as targets
    # (they may not have DBpedia URI mappings if added manually)
    for province_name in PROVINCES.values():
        province_uri = f"{_DBP_RESOURCE}{province_name}"
        targets[province_uri] = province_name

    return targets


def _choose_location_property(
    source_class: str | None,
    target_class: str | None,
) -> str | None:
    """Decide which ontology property to use for a location link.

    Rules based on schema domain/range constraints:
        - City          -> Island:            locatedInIsland   (domain = City)
        - City          -> City:              skip (not meaningful)
        - TouristAttraction subclass -> City: locatedInCity     (domain includes TouristAttraction)
        - Hotel         -> City:              locatedInCity     (domain includes Accommodation)
        - entity        -> Province or Island: locatedIn        (no domain restriction)
        - same-class links (Province->Province, etc.): skip

    Returns:
        Property local name, or None to skip this link entirely.
    """
    location_classes = {"Province", "Island", "City"}

    # Classes whose domain is allowed by locatedInCity
    locatedincity_eligible = TOURIST_ATTRACTION_CLASSES | {"Hotel"}

    # Skip same-type links (Province->Province, Island->Island, City->City)
    if source_class == target_class and source_class in location_classes:
        return None

    # City -> Island: use the specific sub-property
    if source_class == "City" and target_class == "Island":
        return "locatedInIsland"

    # TouristAttraction or Hotel -> City: use locatedInCity
    if source_class in locatedincity_eligible and target_class == "City":
        return "locatedInCity"

    # Anything -> Province or Island: use generic locatedIn
    if target_class in ("Province", "Island"):
        return "locatedIn"

    return None


def add_location_links(graph: Graph) -> None:
    """Discover location relationships by querying DBpedia wikiPageWikiLink.

    For each entity in our graph, checks if DBpedia has a wikiPageWikiLink
    to any of our location entities (Province, Island, City). If yes, adds
    the appropriate locatedIn / locatedInIsland triple.

    Example results:
        Pandawa_Beach  locatedIn       Bali           (Beach -> Province)
        Pandawa_Beach  locatedIn       Bali_Island    (Beach -> Island, via Badung)
        Badung_Regency locatedInIsland Bali_Island    (City -> Island)
    """
    log.info("[Location Links]")
    dbpedia_to_local, local_to_dbpedia = get_dbpedia_mappings()

    # Build source set: all entities with DBpedia URIs
    all_names = _get_all_individual_names(graph)
    source_entities: dict[str, str] = {}   # DBpedia URI -> local name
    for name in all_names:
        if name in local_to_dbpedia:
            source_entities[local_to_dbpedia[name]] = name

    # Build target set: location entities we can link TO
    location_targets = _build_location_targets(graph, local_to_dbpedia)

    if not source_entities or not location_targets:
        return

    # Query in chunks to avoid SPARQL timeout on large VALUES clauses
    source_uri_list = list(source_entities.keys())
    target_values_str = _make_values_clause(location_targets.keys())
    link_count = 0

    for chunk_start in range(0, len(source_uri_list), _SPARQL_CHUNK_SIZE):
        chunk_uris = source_uri_list[chunk_start:chunk_start + _SPARQL_CHUNK_SIZE]
        source_values_str = _make_values_clause(chunk_uris)

        rows = _run_sparql(f"""
            SELECT ?source ?target WHERE {{
                VALUES ?source {{ {source_values_str} }}
                VALUES ?target {{ {target_values_str} }}
                ?source <http://dbpedia.org/ontology/wikiPageWikiLink> ?target .
            }}
        """)

        for row in rows:
            source_uri = row["source"]["value"]
            target_uri = row["target"]["value"]
            source_name = source_entities.get(source_uri)
            target_name = location_targets.get(target_uri)

            # Skip self-links and missing mappings
            if not source_name or not target_name or source_name == target_name:
                continue

            source_class = _get_ontology_class(graph, source_name)
            target_class = _get_ontology_class(graph, target_name)
            property_name = _choose_location_property(source_class, target_class)

            if property_name:
                add_relation(graph, source_name, property_name, target_name)
                link_count += 1

    log.info("  -> %d links (wikiPageWikiLink)", link_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create Activity individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_activity_individuals(graph: Graph) -> None:
    """Create one Activity individual per entry in config.ACTIVITIES.

    Each individual is typed as its specific OWL leaf class (OWL 2 punning),
    so HermiT can infer the WaterSport / MountainSport grouping:

        Surfing   rdf:type Surfing   -> inferred: WaterSport, Activities
        Sailing   rdf:type Sailing   -> inferred: WaterSport, Activities
        Kayaking  rdf:type Kayaking  -> inferred: WaterSport, Activities
        Hiking    rdf:type Hiking    -> inferred: MountainSport, Activities
        Sightseeing / Cultural_Tour  -> typed as Activities (no leaf class)

    Creates: Surfing, Snorkeling, Diving, Sailing, Kayaking,
             Hiking, Sightseeing, Cultural_Tour
    """
    log.info("[Activity Individuals]")
    for activity_name in ACTIVITIES:
        owl_class = ACTIVITY_OWL_CLASS.get(activity_name, "Activities")
        add_individual(graph, owl_class, activity_name)
    log.info("  -> %d created: %s", len(ACTIVITIES), ", ".join(ACTIVITIES))


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Auto-discover hasActivity from DBpedia categories
# ─────────────────────────────────────────────────────────────────────────────
def _infer_activities_from_categories(
    category_results: list[dict],
    entity_uri_to_name: dict[str, str],
) -> set[tuple[str, str]]:
    """Match DBpedia category URIs against CATEGORY_TO_ACTIVITY keywords.

    Args:
        category_results: SPARQL rows with "entity" and "category" bindings.
        entity_uri_to_name: Maps DBpedia URI -> our local name.

    Returns:
        Set of (entity_name, activity_name) pairs to add.

    Example:
        If Dreamland_Beach has category "Surfing_locations_in_Indonesia",
        the keyword "surf" matches -> returns {("Dreamland_Beach", "Surfing")}.
    """
    pairs: set[tuple[str, str]] = set()

    for row in category_results:
        entity_uri = row["entity"]["value"]
        category_uri = row["category"]["value"].lower()
        entity_name = entity_uri_to_name.get(entity_uri)

        if not entity_name:
            continue

        for keyword, activity_name in CATEGORY_TO_ACTIVITY.items():
            if keyword in category_uri:
                pairs.add((entity_name, activity_name))

    return pairs


def _infer_activities_from_wikilinks(
    wikilink_results: list[dict],
    entity_uri_to_name: dict[str, str],
) -> set[tuple[str, str]]:
    """Match DBpedia wikiPageWikiLinks to known activity resources.

    Args:
        wikilink_results: SPARQL rows with "entity" and "activity" bindings.
        entity_uri_to_name: Maps DBpedia URI -> our local name.

    Returns:
        Set of (entity_name, activity_name) pairs to add.

    Example:
        If Komodo_National_Park links to dbr:Scuba_diving,
        returns {("Komodo_National_Park", "Diving")}.
    """
    pairs: set[tuple[str, str]] = set()

    for row in wikilink_results:
        entity_uri = row["entity"]["value"]
        activity_uri = row["activity"]["value"]
        entity_name = entity_uri_to_name.get(entity_uri)
        activity_name = DBPEDIA_RESOURCE_TO_ACTIVITY.get(activity_uri)

        if entity_name and activity_name:
            pairs.add((entity_name, activity_name))

    return pairs


def add_activity_links(graph: Graph) -> None:
    """Discover hasActivity links from DBpedia categories and wikiLinks.

    For each TouristAttraction in our graph:
        1. Fetch its dct:subject categories from DBpedia
        2. Fetch its wikiPageWikiLinks to known activity resources
        3. Match keywords/URIs to our Activity individuals
        4. Add hasActivity triples

    Example results:
        Dreamland_Beach  hasActivity  Surfing     (from category keyword)
        Komodo_NP        hasActivity  Diving      (from wikiLink to dbr:Scuba_diving)
    """
    log.info("[Activity Links]")
    _, local_to_dbpedia = get_dbpedia_mappings()

    # Collect TouristAttraction entities that have DBpedia URIs
    attraction_uri_to_name = _collect_entities_by_class(
        graph, TOURIST_ATTRACTION_CLASSES, local_to_dbpedia,
    )

    if not attraction_uri_to_name:
        log.info("  - no tourist attractions with DBpedia URIs")
        return

    attraction_values = _make_values_clause(attraction_uri_to_name.keys())

    # Query 1: Get all dct:subject categories for our attractions
    category_results = _run_sparql(f"""
        SELECT ?entity ?category WHERE {{
            VALUES ?entity {{ {attraction_values} }}
            ?entity <http://purl.org/dc/terms/subject> ?category .
        }}
    """)

    # Query 2: Get wikiPageWikiLinks to known activity resources
    activity_resource_values = _make_values_clause(
        DBPEDIA_RESOURCE_TO_ACTIVITY.keys()
    )
    wikilink_results = _run_sparql(f"""
        SELECT ?entity ?activity WHERE {{
            VALUES ?entity {{ {attraction_values} }}
            VALUES ?activity {{ {activity_resource_values} }}
            ?entity <http://dbpedia.org/ontology/wikiPageWikiLink> ?activity .
        }}
    """)

    # Combine results from both methods (set avoids duplicates)
    activity_pairs = _infer_activities_from_categories(
        category_results, attraction_uri_to_name,
    )
    activity_pairs |= _infer_activities_from_wikilinks(
        wikilink_results, attraction_uri_to_name,
    )

    # Add the triples to the graph
    for entity_name, activity_name in activity_pairs:
        add_relation(graph, entity_name, "hasActivity", activity_name)

    log.info("  -> %d links (DBpedia categories + wikiLinks)", len(activity_pairs))


# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Fallback activities for entities DBpedia didn't cover
# ─────────────────────────────────────────────────────────────────────────────
def add_activity_fallbacks(graph: Graph) -> None:
    """Assign default activities to entities that got none from DBpedia.

    DBpedia's category coverage is uneven — Balinese ceremonies rarely have
    activity-related categories. This fallback ensures every TouristAttraction
    has at least one hasActivity edge (important for embedding quality).

    Only adds if the entity has ZERO existing hasActivity triples.

    Example: a Temple with no DBpedia activity info gets Cultural_Tour.
    """
    log.info("[Activity Fallbacks]")
    link_count = 0

    for class_name, default_activities in DEFAULT_ACTIVITIES_BY_CLASS.items():
        for subject, _, _ in graph.triples((None, RDF.type, ONT[class_name])):
            # Check if this entity already has any hasActivity edge
            existing_activities = list(
                graph.triples((subject, ONT.hasActivity, None))
            )
            if existing_activities:
                continue  # Already has activities, skip

            entity_name = local_name(subject)
            for activity_name in default_activities:
                add_relation(graph, entity_name, "hasActivity", activity_name)
                link_count += 1

    log.info("  -> %d links assigned to entities with no DBpedia coverage", link_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 8: City -> hasTouristAttraction hub edges
# ─────────────────────────────────────────────────────────────────────────────
def add_attraction_hubs(graph: Graph) -> None:
    """Link each provincial capital to all TouristAttractions in its province.

    This creates hub edges that connect the graph structure:
        Denpasar hasTouristAttraction Pandawa_Beach
        Denpasar hasTouristAttraction Bali_Museum
        Kupang   hasTouristAttraction Komodo_National_Park

    Hotel is excluded because Hotel ⊑ Accommodation ⊥ TouristAttraction.

    Only links attractions that have locatedIn -> the same province as the city.
    """
    log.info("[Tourist Attraction Hubs]")
    link_count = 0

    for province_name, capital_name in CAPITAL_OF_PROVINCE.items():
        if not has_type(graph, capital_name, "City"):
            continue

        # Find all tourist attractions located in this province
        for attraction_class in TOURIST_ATTRACTION_CLASSES:
            for subject, _, _ in graph.triples((None, RDF.type, ONT[attraction_class])):
                is_in_province = (
                    subject, ONT.locatedIn, ONT[province_name]
                ) in graph
                if is_in_province:
                    graph.add((ONT[capital_name], ONT.hasTouristAttraction, subject))
                    link_count += 1

    log.info("  -> %d hub edges (City → hasTouristAttraction)", link_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 9: City -> hasAccommodation hub edges
# ─────────────────────────────────────────────────────────────────────────────
def add_accommodation_hubs(graph: Graph) -> None:
    """Link each provincial capital to all Hotels located in its province.

    This mirrors add_attraction_hubs() but for the Accommodation hierarchy:
        domain = City, range = Accommodation (Hotel ⊑ Accommodation)

    Example results:
        Denpasar hasAccommodation Amankila
        Denpasar hasAccommodation Tandjung_Sari
        Kupang   hasAccommodation <any NTT hotel>

    Only links hotels that have locatedIn -> the same province as the city.
    Hotels that have no locatedIn edge are skipped (can't determine province).
    """
    log.info("[Accommodation Hubs]")
    link_count = 0

    for province_name, capital_name in CAPITAL_OF_PROVINCE.items():
        if not has_type(graph, capital_name, "City"):
            continue

        # Find all Hotel individuals located in this province
        for subject, _, _ in graph.triples((None, RDF.type, ONT["Hotel"])):
            is_in_province = (subject, ONT.locatedIn, ONT[province_name]) in graph
            if is_in_province:
                graph.add((ONT[capital_name], ONT.hasAccommodation, subject))
                link_count += 1

    log.info("  -> %d hub edges (City → hasAccommodation)", link_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 10: numberOfVisitors data property
# ─────────────────────────────────────────────────────────────────────────────
def add_visitor_counts(graph: Graph) -> None:
    """Fetch annual visitor counts from DBpedia and add as data property triples.

    Queries DBpedia's dbo:numberOfVisitors for all TouristAttraction entities
    that have a DBpedia URI mapping. Adds triples of the form:
        ont:Komodo_National_Park  ont:numberOfVisitors  "45000"^^xsd:integer

    Only national parks tend to have this data on DBpedia — coverage is sparse
    (~4 entities in our region). The property is still useful for SPARQL queries
    like "find attractions with more than 10,000 annual visitors".
    """
    log.info("[Visitor Counts]")
    _, local_to_dbpedia = get_dbpedia_mappings()

    # Collect all TouristAttraction entities with DBpedia URIs
    attraction_uri_to_name = _collect_entities_by_class(
        graph, TOURIST_ATTRACTION_CLASSES, local_to_dbpedia,
    )

    if not attraction_uri_to_name:
        return

    attraction_values = _make_values_clause(attraction_uri_to_name.keys())

    rows = _run_sparql(f"""
        SELECT ?entity ?count WHERE {{
            VALUES ?entity {{ {attraction_values} }}
            ?entity <http://dbpedia.org/ontology/numberOfVisitors> ?count .
        }}
    """)

    added_count = 0
    for row in rows:
        entity_name = attraction_uri_to_name.get(row["entity"]["value"])
        if not entity_name:
            continue
        try:
            visitor_count = int(float(row["count"]["value"]))
        except ValueError:
            continue

        graph.add((
            ONT[entity_name],
            ONT.numberOfVisitors,
            Literal(visitor_count, datatype=XSD.integer),
        ))
        log.info("  + %s: %s visitors", entity_name, f"{visitor_count:,}")
        added_count += 1

    log.info("  -> %d values added", added_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 11: Curated hasRating data properties
# ─────────────────────────────────────────────────────────────────────────────
def add_curated_ratings(graph: Graph) -> None:
    """Add manually curated hasRating (xsd:decimal, scale 1–5) triples.

    Reads from curate_properties.RATINGS — a dict of class -> {individual: score}.
    Skips any individual that:
        - Does not exist in the graph (not yet populated, or wrong local name)
        - Is typed as Hotel: hasRating domain = TouristAttraction, and
          Hotel ⊑ Accommodation ⊥ TouristAttraction — adding hasRating to a
          hotel would cause HermiT to infer it is a TouristAttraction and
          produce an INCONSISTENT ontology.

    Example triple added:
        ont:Pandawa_Beach  ont:hasRating  "4.1"^^xsd:decimal
    """
    log.info("[Ratings]")
    added_count = 0
    skipped_missing: list[str] = []
    skipped_hotel: list[str] = []

    for class_name, ratings_dict in RATINGS.items():
        for individual_name, rating_value in ratings_dict.items():

            # Hotels cannot have hasRating (domain violation → inconsistency)
            if class_name == "Hotel":
                skipped_hotel.append(individual_name)
                continue

            # Skip if individual was not populated (e.g. name mismatch)
            if not has_type(graph, individual_name, class_name):
                skipped_missing.append(individual_name)
                continue

            graph.add((
                ONT[individual_name],
                ONT.hasRating,
                Literal(rating_value, datatype=XSD.decimal),
            ))
            added_count += 1

    log.info("  -> %d hasRating values added", added_count)
    if skipped_hotel:
        log.info("  - Hotel domain conflict: %s", ", ".join(skipped_hotel))
    if skipped_missing:
        log.info("  - not in graph: %s", ", ".join(skipped_missing))


# ─────────────────────────────────────────────────────────────────────────────
# Step 11b: Curated hasEntryFee (TouristAttraction -> xsd:boolean)
# ─────────────────────────────────────────────────────────────────────────────
def add_curated_entry_fees(graph: Graph) -> None:
    """Add manually curated hasEntryFee triples.

    Reads from curate_properties.ENTRY_FEE — {individual: bool}.
    Skips any individual missing from the graph, and any individual whose
    only type is Hotel/Accommodation (domain = TouristAttraction).

    Example triple added:
        ont:Komodo_National_Park  ont:hasEntryFee  "true"^^xsd:boolean
    """
    log.info("[Entry Fees]")
    added_count = 0
    skipped_missing: list[str] = []

    for individual_name, fee_flag in ENTRY_FEE.items():
        # Existence check: must be in graph as some kind of TouristAttraction
        # (Museum, Park, etc. all ⊑ TouristAttraction).
        if (ONT[individual_name], None, None) not in graph:
            skipped_missing.append(individual_name)
            continue

        graph.add((
            ONT[individual_name],
            ONT.hasEntryFee,
            Literal(bool(fee_flag), datatype=XSD.boolean),
        ))
        added_count += 1

    log.info("  -> %d hasEntryFee values added", added_count)
    if skipped_missing:
        log.info("  - not in graph: %s", ", ".join(skipped_missing))


# ─────────────────────────────────────────────────────────────────────────────
# Step 11c: Curated establishedYear for Parks (Park -> xsd:integer, Functional)
# ─────────────────────────────────────────────────────────────────────────────
def add_park_established_years(graph: Graph) -> None:
    """Add manually curated establishedYear triples for Parks.

    Reads from curate_properties.PARK_ESTABLISHED_YEAR — {park_name: year}.
    establishedYear is a FunctionalProperty with domain = Park, range = integer.
    Skips parks not in the graph.

    Example triple added:
        ont:Komodo_National_Park  ont:establishedYear  "1980"^^xsd:integer
    """
    log.info("[Established Years]")
    added_count = 0
    skipped_missing: list[str] = []

    for park_name, year in PARK_ESTABLISHED_YEAR.items():
        if not has_type(graph, park_name, "Park"):
            skipped_missing.append(park_name)
            continue

        graph.add((
            ONT[park_name],
            ONT.establishedYear,
            Literal(int(year), datatype=XSD.integer),
        ))
        added_count += 1

    log.info("  -> %d establishedYear values added", added_count)
    if skipped_missing:
        log.info("  - not in graph as Park: %s", ", ".join(skipped_missing))


# ─────────────────────────────────────────────────────────────────────────────
# Step 12: Manual Transportation individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_transportation(graph: Graph) -> None:
    """Add Transportation individuals from curate_individuals.TRANSPORTATION.

    For each entry:
        1. Creates the individual with its specific subclass (AirTransport,
           LandTransport, or WaterTransport).
        2. Adds locatedIn -> Province.
        3. Links the provincial capital to it via City -> hasTransportation.

    Example triples added:
        ont:Ngurah_Rai_International_Airport  rdf:type  ont:AirTransport
        ont:Ngurah_Rai_International_Airport  ont:locatedIn  ont:Bali
        ont:Denpasar  ont:hasTransportation  ont:Ngurah_Rai_International_Airport
    """
    log.info("[Transportation]")
    added_count = 0

    for entry in TRANSPORTATION:
        individual_name  = entry["name"]
        owl_class        = entry["type"]
        province_name    = entry["locatedIn"]

        # Create the individual and link to province
        add_individual(graph, owl_class, individual_name)
        add_relation(graph, individual_name, "locatedIn", province_name)

        # Link the provincial capital to this transportation node
        capital_name = CAPITAL_OF_PROVINCE.get(province_name)
        if capital_name and has_type(graph, capital_name, "City"):
            add_relation(graph, capital_name, "hasTransportation", individual_name)

        log.info("  + %s (%s, %s)", individual_name, owl_class, province_name)
        added_count += 1

    log.info("  -> %d individuals added", added_count)


# ─────────────────────────────────────────────────────────────────────────────
# Step 13: Manual Festival individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_festivals(graph: Graph) -> None:
    """Add Festival individuals for NTB and NTT from curate_individuals.FESTIVALS"""
    
    log.info("[Festivals (Manual — NTB/NTT)]")
    added_count = 0

    for entry in FESTIVALS:
        individual_name = entry["name"]
        province_name   = entry["locatedIn"]

        add_individual(graph, "Festival", individual_name)
        add_relation(graph, individual_name, "locatedIn", province_name)

        # Assign default activity directly — these won't be picked up by
        # add_activity_links() since they have no DBpedia URI
        add_relation(graph, individual_name, "hasActivity", "Cultural_Tour")

        log.info("  + %s (locatedIn: %s)", individual_name, province_name)
        added_count += 1

    log.info("  -> %d individuals added", added_count)


# ─────────────────────────────────────────────────────────────────────────────
# Steps 15–16: Manual TraditionalDance and TraditionalHouse individuals
# ─────────────────────────────────────────────────────────────────────────────
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
        log.info("  + %s (%s)", name, province)
        count += 1
    log.info("  -> %d individuals added", count)


def add_manual_traditional_dances(graph: Graph) -> None:
    """Add TraditionalDance individuals from curated_data.TRADITIONAL_DANCES."""
    log.info("[Traditional Dances]")
    _add_cultural_individuals(graph, TRADITIONAL_DANCES, "TraditionalDance", "traditional dances")


def add_manual_traditional_houses(graph: Graph) -> None:
    """Add TraditionalHouse individuals from curated_data.TRADITIONAL_HOUSES."""
    log.info("[Traditional Houses]")
    _add_cultural_individuals(graph, TRADITIONAL_HOUSES, "TraditionalHouse", "traditional houses")


# ─────────────────────────────────────────────────────────────────────────────
# Step 16: Manual Beach individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_beaches(graph: Graph) -> None:
    """Add Beach individuals from curated_data.BEACHES_MANUAL.

    Supplements DBpedia output: NTB and NTT beaches are rarely returned by the
    DBpedia populate step; Bali entries fill specific gaps. Each beach receives
    the full set of water-sport activity links so the embedding model sees
    meaningful hasActivity edges for these nodes.

    Each entry gets:
        rdf:type Beach
        locatedIn -> Province
        hasActivity -> Surfing, Snorkeling, Sailing, Kayaking
        City -> hasTouristAttraction -> Beach  (hub link)
    """
    log.info("[Beaches (Manual)]")
    _add_cultural_individuals(
        graph, BEACHES_MANUAL, "Beach", "beaches",
        activities=["Surfing", "Snorkeling", "Sailing", "Kayaking"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 17: Manual ReligiousCeremony individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_religious_ceremonies(graph: Graph) -> None:
    """Add ReligiousCeremony individuals from curated_data.RELIGIOUS_CEREMONIES.

    DBpedia returns near-zero structured results for ReligiousCeremony across
    all three provinces. All entries are therefore manual.

    Each entry gets:
        rdf:type ReligiousCeremony
        locatedIn -> Province
        hasActivity -> Cultural_Tour
        City -> hasTouristAttraction -> ReligiousCeremony  (hub link)
    """
    log.info("[Religious Ceremonies]")
    _add_cultural_individuals(
        graph, RELIGIOUS_CEREMONIES, "ReligiousCeremony", "religious ceremonies",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 18: Manual Temple individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_temples(graph: Graph) -> None:
    """Add Temple individuals from curated_data.TEMPLES.

    DBpedia covers some famous Bali temples; NTB and NTT have no structured
    Temple results. Bali entries here supplement DBpedia output — rdflib triples
    are idempotent so adding an existing individual's type/locatedIn is safe.

    Each entry gets:
        rdf:type Temple
        locatedIn -> Province
        hasActivity -> Cultural_Tour
        City -> hasTouristAttraction -> Temple  (hub link)
    """
    log.info("[Temples (Manual)]")
    _add_cultural_individuals(
        graph, TEMPLES, "Temple", "temples",
    )


ALL_ENRICHERS = [
    add_country_backbone,
    add_bali_island,
    add_island_province,
    add_location_links,             # adds locatedIn, locatedInIsland, locatedInCity
    add_activity_individuals,
    add_activity_links,
    add_activity_fallbacks,
    add_attraction_hubs,            # City -> hasTouristAttraction -> TouristAttraction
    add_accommodation_hubs,         # City -> hasAccommodation -> Hotel
    add_visitor_counts,             # TouristAttraction -> numberOfVisitors -> xsd:integer
    add_curated_ratings,            # TouristAttraction -> hasRating -> xsd:decimal
    add_curated_entry_fees,         # TouristAttraction -> hasEntryFee -> xsd:boolean
    add_park_established_years,     # Park -> establishedYear -> xsd:integer
    add_manual_transportation,      # Transportation individuals + City -> hasTransportation
    add_manual_festivals,              # Festival individuals for NTB/NTT
    add_manual_traditional_dances,     # TraditionalDance individuals + hub links
    add_manual_traditional_houses,     # TraditionalHouse individuals + hub links
    add_manual_beaches,                # Beach individuals for NTB/NTT + Bali gaps
    add_manual_religious_ceremonies,   # ReligiousCeremony individuals (all 3 provinces)
    add_manual_temples,                # Temple individuals (Bali supplements + NTB/NTT)
]


def enrich_all(graph: Graph) -> None:
    """Run all enrichment steps in order.

    Each step is independent and can be skipped/reordered, except:
        - add_activity_individuals must run before add_activity_links
        - add_activity_links must run before add_activity_fallbacks
        - add_location_links should run before add_attraction_hubs and
          add_accommodation_hubs (both hubs depend on locatedIn edges)
    """
    for enrichment_step in ALL_ENRICHERS:
        enrichment_step(graph)
