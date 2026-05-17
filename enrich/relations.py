"""Steps 3–9: Relation enrichment via DBpedia and hub edges."""

import logging

from rdflib import Graph, RDF

from config import ONT, ONT_IRI, PROVINCES, ACTIVITIES
from graph_utils import add_individual, add_relation, has_type, local_name
from populate import get_dbpedia_mappings
from enrich.utils import (
    _DBP_RESOURCE,
    _SPARQL_CHUNK_SIZE,
    TOURIST_ATTRACTION_CLASSES,
    CATEGORY_TO_ACTIVITY,
    DBPEDIA_RESOURCE_TO_ACTIVITY,
    ACTIVITY_OWL_CLASS,
    DEFAULT_ACTIVITIES_BY_CLASS,
    CAPITAL_OF_PROVINCE,
    _run_sparql,
    _make_values_clause,
    _get_all_individual_names,
    _get_ontology_class,
    _collect_entities_by_class,
)

log = logging.getLogger(__name__)

# Step 3: Island -> Province links
def add_island_province(graph: Graph) -> None:
    """Link each Island to its Province using DBpedia's isPartOf and wikiLinks.

    Queries DBpedia for relationships between our Island individuals and
    our Province individuals. Uses locatedInProvince (domain = Island).

    Example result:
        Flores  locatedInProvince  East_Nusa_Tenggara
        Lombok  locatedInProvince  West_Nusa_Tenggara
    """
    log.info("[Island -> Province Links]")
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

# Known false positives produced by wikiPageWikiLink (source, target) pairs to skip.
_LOCATION_LINK_BLACKLIST: set[tuple[str, str]] = {
    ("Kupang",        "Flores"),
    ("Kupang",        "Rote_Island"),
    ("Kupang",        "Savu"),
    ("Mount_Agung",   "Lombok"),
    ("Dompu_Regency", "Satonda_Island"),
}

# Strict DBpedia properties that encode genuine geographic containment.
_STRICT_LOCATION_PROPS = [
    "http://dbpedia.org/ontology/isPartOf",
    "http://dbpedia.org/ontology/location",
    "http://dbpedia.org/property/location",
    "http://dbpedia.org/ontology/region",
]

# Step 4: Auto-discover location links via strict properties + wikiPageWikiLink fallback
def _build_location_targets(
    graph: Graph,
    local_to_dbpedia: dict[str, str],
) -> dict[str, str]:
    """Build a dict of DBpedia URI -> local name for all location entities."""
    location_classes = {"Province", "Island", "City"}
    all_names = _get_all_individual_names(graph)
    targets: dict[str, str] = {}

    for name in all_names:
        entity_class = _get_ontology_class(graph, name)
        if entity_class in location_classes and name in local_to_dbpedia:
            targets[local_to_dbpedia[name]] = name

    # Ensure all provinces are included as targets
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
    """Discover location relationships from DBpedia.

    Strategy:
        1. Query strict geographic properties (dbo:isPartOf, dbo:location, etc.)
           for all entities. Entities that get at least one strict hit use ONLY
           those results — no wikiPageWikiLink fallback needed.
        2. Entities with zero strict hits fall back to wikiPageWikiLink, but
           results are filtered through _LOCATION_LINK_BLACKLIST to remove
           known false positives caused by Wikipedia article cross-references.
    """
    log.info("[Location Links]")
    dbpedia_to_local, local_to_dbpedia = get_dbpedia_mappings()

    all_names = _get_all_individual_names(graph)
    source_entities: dict[str, str] = {}
    for name in all_names:
        if name in local_to_dbpedia:
            source_entities[local_to_dbpedia[name]] = name

    location_targets = _build_location_targets(graph, local_to_dbpedia)

    if not source_entities or not location_targets:
        return

    source_uri_list = list(source_entities.keys())
    target_values_str = _make_values_clause(location_targets.keys())
    prop_values_str = " ".join(f"<{p}>" for p in _STRICT_LOCATION_PROPS)

    # Pass 1: strict geographic properties
    strict_hits: set[str] = set()
    pending_rows: list[tuple[str, str]] = []

    for i in range(0, len(source_uri_list), _SPARQL_CHUNK_SIZE):
        chunk = _make_values_clause(source_uri_list[i:i + _SPARQL_CHUNK_SIZE])
        rows = _run_sparql(f"""
            SELECT ?source ?target WHERE {{
                VALUES ?source {{ {chunk} }}
                VALUES ?target {{ {target_values_str} }}
                VALUES ?prop   {{ {prop_values_str} }}
                ?source ?prop ?target .
            }}
        """)
        for row in rows:
            src = row["source"]["value"]
            strict_hits.add(src)
            pending_rows.append((src, row["target"]["value"]))

    # Pass 2: wikiPageWikiLink fallback for entities with no strict results
    wiki_sources = [u for u in source_uri_list if u not in strict_hits]
    for i in range(0, len(wiki_sources), _SPARQL_CHUNK_SIZE):
        chunk = _make_values_clause(wiki_sources[i:i + _SPARQL_CHUNK_SIZE])
        rows = _run_sparql(f"""
            SELECT ?source ?target WHERE {{
                VALUES ?source {{ {chunk} }}
                VALUES ?target {{ {target_values_str} }}
                ?source <http://dbpedia.org/ontology/wikiPageWikiLink> ?target .
            }}
        """)
        for row in rows:
            pending_rows.append((row["source"]["value"], row["target"]["value"]))

    # Apply results
    link_count = 0
    skipped = 0
    for source_uri, target_uri in pending_rows:
        source_name = source_entities.get(source_uri)
        target_name = location_targets.get(target_uri)

        if not source_name or not target_name or source_name == target_name:
            continue
        if (source_name, target_name) in _LOCATION_LINK_BLACKLIST:
            log.debug("Blacklisted: %s -> %s", source_name, target_name)
            skipped += 1
            continue

        source_class = _get_ontology_class(graph, source_name)
        target_class = _get_ontology_class(graph, target_name)
        prop = _choose_location_property(source_class, target_class)
        if prop:
            add_relation(graph, source_name, prop, target_name)
            link_count += 1

    log.info("  -> %d links (%d via strict props, %d via wikiPageWikiLink, %d blacklisted)",
             link_count, len(strict_hits), len(wiki_sources), skipped)

# Step 5: Create Activity individuals
def add_activity_individuals(graph: Graph) -> None:
    """Create one Activity individual per entry in config.ACTIVITIES.

    Each individual is typed as its specific OWL leaf class (OWL 2 punning),
    so HermiT can infer the WaterSport / MountainSport grouping:

        Surfing   rdf:type Surfing   -> inferred: WaterSport, Activities
        Sailing   rdf:type Sailing   -> inferred: WaterSport, Activities
        Kayaking  rdf:type Kayaking  -> inferred: WaterSport, Activities
        Hiking    rdf:type Hiking    -> inferred: MountainSport, Activities
        Sightseeing / Cultural_Tour  -> typed as Activities (no leaf class)
    """
    log.info("[Activity Individuals]")
    for activity_name in ACTIVITIES:
        owl_class = ACTIVITY_OWL_CLASS.get(activity_name, "Activities")
        add_individual(graph, owl_class, activity_name)
    log.info("  -> %d created: %s", len(ACTIVITIES), ", ".join(ACTIVITIES))

# Step 6: Auto-discover hasActivity from DBpedia categories
def _infer_activities_from_categories(
    category_results: list[dict],
    entity_uri_to_name: dict[str, str],
) -> set[tuple[str, str]]:
    """Match DBpedia category URIs against CATEGORY_TO_ACTIVITY keywords."""
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
    """Match DBpedia wikiPageWikiLinks to known activity resources."""
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

# Step 7: Fallback activities for entities DBpedia didn't cover
def add_activity_fallbacks(graph: Graph) -> None:
    """Assign default activities to entities that got none from DBpedia.

    DBpedia's category coverage is uneven — Balinese ceremonies rarely have
    activity-related categories. This fallback ensures every TouristAttraction
    has at least one hasActivity edge (important for embedding quality).

    Only adds if the entity has ZERO existing hasActivity triples.
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

# Step 8: City -> hasTouristAttraction hub edges
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

    log.info("  -> %d hub edges (City -> hasTouristAttraction)", link_count)

# Step 9: City -> hasAccommodation hub edges
def add_accommodation_hubs(graph: Graph) -> None:
    """Link each provincial capital to all Hotels located in its province.

    This mirrors add_attraction_hubs() but for the Accommodation hierarchy:
        domain = City, range = Accommodation (Hotel ⊑ Accommodation)

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

    log.info("  -> %d hub edges (City -> hasAccommodation)", link_count)
