"""Steps 10–11: Property enrichment (visitor counts, ratings, entry fees, years)."""

import logging

from rdflib import Graph, Literal, XSD

from config import ONT
from graph_utils import has_type
from curated_data import RATINGS, ENTRY_FEE, PARK_ESTABLISHED_YEAR, PARKS_MANUAL
from populate import get_dbpedia_mappings
from enrich.utils import (
    TOURIST_ATTRACTION_CLASSES,
    _run_sparql,
    _make_values_clause,
    _collect_entities_by_class,
    _add_cultural_individuals,
)

log = logging.getLogger(__name__)

# Step 16 (pre-property): Manual Park individuals
def add_manual_parks(graph: Graph) -> None:
    """Add Park individuals from curated_data.PARKS_MANUAL.

    These Bali parks are referenced in RATINGS, ENTRY_FEE, and PARK_ESTABLISHED_YEAR
    but are not returned by DBpedia's populate step. Adding them here ensures the
    property enrichers (add_curated_ratings, add_curated_entry_fees,
    add_park_established_years) find them in the graph instead of logging skips.

    Each entry gets:
        rdf:type Park
        locatedIn -> Province
        hasActivity -> Sightseeing, Hiking
        City -> hasTouristAttraction -> Park  (hub link)
    """
    log.info("[Parks (Manual)]")
    _add_cultural_individuals(
        graph, PARKS_MANUAL, "Park", "parks",
        activities=["Sightseeing", "Hiking"],
    )

# Step 10: numberOfVisitors data property
def add_visitor_counts(graph: Graph) -> None:
    """Fetch annual visitor counts from DBpedia and add as data property triples.

    Queries DBpedia's dbo:numberOfVisitors for all TouristAttraction entities
    that have a DBpedia URI mapping. Adds triples of the form:
        ont:Komodo_National_Park  ont:numberOfVisitors  "45000"^^xsd:integer

    Only national parks tend to have this data on DBpedia — coverage is sparse
    (~4 entities in our region).
    """
    log.info("[Visitor Counts (DBpedia)]")
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

# Step 11: Curated hasRating data properties
def add_curated_ratings(graph: Graph) -> None:
    """Add manually curated hasRating (xsd:decimal, scale 1–5) triples.

    Reads from curated_data.RATINGS — a dict of class -> {individual: score}.
    domain = TouristAttraction ⊔ Accommodation, so both attraction and hotel/resort
    individuals are valid subjects. Skips only individuals missing from the graph.

    Example triple added:
        ont:Pandawa_Beach  ont:hasRating  "4.1"^^xsd:decimal
        ont:Amankila       ont:hasRating  "4.7"^^xsd:decimal
    """
    log.info("[Ratings]")
    added_count = 0
    skipped_missing: list[str] = []

    for class_name, ratings_dict in RATINGS.items():
        for individual_name, rating_value in ratings_dict.items():

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
    if skipped_missing:
        log.info("  - not in graph: %s", ", ".join(skipped_missing))

# Step 11b: Curated hasEntryFee (TouristAttraction -> xsd:boolean)
def add_curated_entry_fees(graph: Graph) -> None:
    """Add manually curated hasEntryFee triples.

    Reads from curated_data.ENTRY_FEE — {individual: bool}.
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

# Step 11c: Curated establishedYear for Parks (Park -> xsd:integer, Functional)
def add_park_established_years(graph: Graph) -> None:
    """Add manually curated establishedYear triples for Parks.

    Reads from curated_data.PARK_ESTABLISHED_YEAR — {park_name: year}.
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
