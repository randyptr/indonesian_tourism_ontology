"""Populate the knowledge graph with individuals fetched from DBpedia.

Each public function fetches one tourism class (Province, Beach, Park, …) via
SPARQL queries against the DBpedia endpoint and adds:
    - rdf:type triples (class membership)
    - A minimal locatedIn triple linking the individual to its province

Relational enrichment (cross-entity links like island→province, hasActivity)
is handled separately in enrich.py. This module only creates individuals and
their province assignment.

Architecture
------------
1. A shared SPARQL client sends queries with polite throttling.
2. Per-class query dictionaries define the SPARQL for each province.
3. _process_query_results() is the common loop that turns SPARQL bindings
   into OWL individuals with locatedIn edges.
4. A DBpedia URI ↔ local name registry tracks mappings for use by enrich.py.
"""

import time
import logging
from decimal import Decimal
from typing import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD
from SPARQLWrapper import SPARQLWrapper, JSON

from config import (
    DBPEDIA_ENDPOINT, DBPEDIA_TIMEOUT_S, DBPEDIA_THROTTLE_S,
    PROVINCES, ONT,
)
from graph_utils import slugify, label_to_local, add_individual

log = logging.getLogger(__name__)

_sparql_client = SPARQLWrapper(DBPEDIA_ENDPOINT)
_sparql_client.setReturnFormat(JSON)
_sparql_client.setTimeout(DBPEDIA_TIMEOUT_S)


def _execute_sparql_query(sparql_query: str) -> list[dict]:
    """Execute a SPARQL SELECT query against DBpedia and return result bindings.

    Handles errors gracefully (returns empty list on failure) and enforces
    a polite delay between consecutive queries to avoid rate limiting.

    Parameters
    ----------
    sparql_query : str
        A complete SPARQL SELECT query string.

    Returns
    -------
    list[dict]
        Each dict maps variable names to {'type': ..., 'value': ...} dicts.
        Empty list if the query fails (timeout, network error, etc.).
    """
    _sparql_client.setQuery(sparql_query)
    try:
        response = _sparql_client.query().convert()
        return response["results"]["bindings"]
    except Exception as error:
        log.warning("Query failed: %s", error)
        return []
    finally:
        time.sleep(DBPEDIA_THROTTLE_S)


# ── DBpedia URI ↔ Local Name Registry ────────────────────────────────────────
# Populated during queries so that enrich.py can map between DBpedia URIs
# (used in wikiPageWikiLink discovery) and our ontology local names.

_dbpedia_uri_to_local_name: dict[str, str] = {}
_local_name_to_dbpedia_uri: dict[str, str] = {}


def get_dbpedia_mappings() -> tuple[dict[str, str], dict[str, str]]:
    """Return the bidirectional mapping registries built during population.

    Returns
    -------
    tuple[dict, dict]
        (dbpedia_uri_to_local_name, local_name_to_dbpedia_uri)
        Both are populated as a side-effect of running populate_all().
    """
    return _dbpedia_uri_to_local_name, _local_name_to_dbpedia_uri


def _register_uri_mapping(local_name_str: str, dbpedia_uri: str) -> None:
    """Record the bidirectional link between a local name and its DBpedia URI.

    Called internally whenever a new individual is created from a query result,
    so enrich.py can later look up which DBpedia resource corresponds to which
    ontology individual.
    """
    _dbpedia_uri_to_local_name[dbpedia_uri] = local_name_str
    _local_name_to_dbpedia_uri[local_name_str] = dbpedia_uri


def _process_query_results(
    graph: Graph,
    query_results: Iterable[dict],
    owl_class: str,
    *,
    name_variable: str,
    derive_name_from_label: bool,
    uri_variable: str | None = None,
    province_short_name: str | None = None,
) -> int:
    """Convert SPARQL result bindings into OWL individuals with optional locatedIn.

    This is the common processing loop used by all populate_* functions. It:
    1. Extracts the individual's local name from the query result.
    2. Creates the individual with its class assertion.
    3. Registers the DBpedia URI mapping for later use by enrich.py.
    4. Optionally adds a locatedIn triple to the individual's province.

    Parameters
    ----------
    graph : rdflib.Graph
        The target knowledge graph to add individuals to.
    query_results : Iterable[dict]
        SPARQL result bindings (list of dicts from _execute_sparql_query).
    owl_class : str
        The OWL class local name (e.g. 'Beach', 'Island', 'City').
    name_variable : str
        The SPARQL variable name containing the entity identifier.
    derive_name_from_label : bool
        If True, the name_variable contains an rdfs:label string that needs
        sanitisation via label_to_local(). If False, it contains a full
        DBpedia URI that gets slugified.
    uri_variable : str or None
        If provided, the SPARQL variable containing the DBpedia URI
        (used when name_variable is a label, not the URI itself).
    province_short_name : str or None
        If provided, a locatedIn triple is added linking the individual
        to the province indicated by this short name (e.g. 'Bali', 'NTB').

    Returns
    -------
    int
        Number of individuals successfully created.
    """
    individuals_created = 0

    for result_row in query_results:
        # Derive the OWL local name from either a label or a URI
        if derive_name_from_label:
            individual_local = label_to_local(result_row[name_variable]["value"])
        else:
            individual_local = slugify(result_row[name_variable]["value"])

        # Create the individual with class assertion
        add_individual(graph, owl_class, individual_local)

        # Register the DBpedia URI mapping for cross-module use
        if uri_variable and uri_variable in result_row:
            _register_uri_mapping(individual_local, result_row[uri_variable]["value"])
        elif not derive_name_from_label:
            _register_uri_mapping(individual_local, result_row[name_variable]["value"])

        # Add province location if specified
        if province_short_name is not None:
            province_individual = PROVINCES[province_short_name]
            graph.add((ONT[individual_local], ONT.locatedIn, ONT[province_individual]))
            log.info("  + %s  (locatedIn: %s)", individual_local, province_individual)
        else:
            log.info("  + %s", individual_local)

        individuals_created += 1

    return individuals_created


# ═══════════════════════════════════════════════════════════════════════════════
# SPARQL Query Definitions
# Each dict maps province short name -> SPARQL query string.
# ═══════════════════════════════════════════════════════════════════════════════

_PROVINCE_QUERY = """
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?x WHERE {
    VALUES ?x { dbr:Bali dbr:West_Nusa_Tenggara dbr:East_Nusa_Tenggara }
    ?x rdfs:label ?name .
    FILTER(LANG(?name) = "en")
    FILTER(!CONTAINS(?name, "("))
}"""

_ISLAND_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Island .
            ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_Bali> .
        } LIMIT 20""",
    "NTB": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Island .
            ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_West_Nusa_Tenggara> .
        } LIMIT 20""",
    "NTT": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Island .
            ?x dct:subject <http://dbpedia.org/resource/Category:Lesser_Sunda_Islands> .
            FILTER NOT EXISTS {
                ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_Bali> .
            }
            FILTER NOT EXISTS {
                ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_West_Nusa_Tenggara> .
            }
            FILTER(?x NOT IN (
                <http://dbpedia.org/resource/Lombok>,
                <http://dbpedia.org/resource/Sumbawa>,
                <http://dbpedia.org/resource/Moyo_Island>,
                <http://dbpedia.org/resource/Satonda_Island>,
                <http://dbpedia.org/resource/Bungin_Island>,
                <http://dbpedia.org/resource/Lesser_Sunda_Islands>,
                <http://dbpedia.org/resource/Sunda_Arc>,
                <http://dbpedia.org/resource/Bawean>,
                <http://dbpedia.org/resource/Gili_Islands>,
                <http://dbpedia.org/resource/Timor>
            ))
        } LIMIT 20""",
}

# Regencies (kabupaten) — Bali uses dbo:subdivision; NTB/NTT use precise category
_REGENCY_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo:  <http://dbpedia.org/ontology/>
        PREFIX dbr:  <http://dbpedia.org/resource/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            dbr:Bali dbo:subdivision ?city .
            ?city rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            FILTER(CONTAINS(?name, "Regency"))
        } LIMIT 25""",
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Regencies_of_West_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 25""",
    "NTT": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Regencies_of_East_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 30""",
}

# Capital cities (kota) — category intersection with Cities_in_Indonesia
_CITY_QUERIES_BY_PROVINCE = {
    province_short: f"""
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {{
            ?city dct:subject <http://dbpedia.org/resource/Category:Cities_in_Indonesia> ;
                  dct:subject <http://dbpedia.org/resource/Category:Populated_places_in_{province_full}> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        }} LIMIT 10"""
    for province_short, province_full in PROVINCES.items()
}

# Beaches — Bali has its own category; NTB/NTT intersect Beaches_of_Indonesia
_BEACH_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?beach ?name WHERE {
            ?beach dct:subject <http://dbpedia.org/resource/Category:Beaches_of_Bali> ;
                   rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 30""",
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?beach ?name WHERE {
            ?beach dct:subject <http://dbpedia.org/resource/Category:Beaches_of_Indonesia> ;
                   rdfs:label  ?name .
            { ?beach dct:subject <http://dbpedia.org/resource/Category:Landforms_of_Lombok> }
            UNION { ?beach dct:subject <http://dbpedia.org/resource/Category:Landforms_of_Sumbawa> }
            UNION { ?beach dct:subject <http://dbpedia.org/resource/Category:Landforms_of_West_Nusa_Tenggara> }
            FILTER(LANG(?name) = "en")
        } LIMIT 30""",
    "NTT": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?beach ?name WHERE {
            ?beach dct:subject <http://dbpedia.org/resource/Category:Beaches_of_Indonesia> ;
                   dct:subject <http://dbpedia.org/resource/Category:Landforms_of_East_Nusa_Tenggara> ;
                   rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 30""",
}

# National parks — intersect National_parks_of_Indonesia with regional categories
_PARK_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?park ?name WHERE {
            ?park dct:subject <http://dbpedia.org/resource/Category:National_parks_of_Indonesia> ;
                  dct:subject ?regionCat ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
            FILTER(?regionCat IN (
                <http://dbpedia.org/resource/Category:National_parks_of_Bali>,
                <http://dbpedia.org/resource/Category:Tourist_attractions_in_Bali>,
                <http://dbpedia.org/resource/Category:Geography_of_Bali>))
        } LIMIT 20""",
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?park ?name WHERE {
            ?park dct:subject <http://dbpedia.org/resource/Category:National_parks_of_Indonesia> ;
                  dct:subject ?regionCat ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
            FILTER(?regionCat IN (
                <http://dbpedia.org/resource/Category:Geography_of_West_Nusa_Tenggara>,
                <http://dbpedia.org/resource/Category:Tourist_attractions_in_West_Nusa_Tenggara>))
        } LIMIT 20""",
    "NTT": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?park ?name WHERE {
            ?park dct:subject <http://dbpedia.org/resource/Category:National_parks_of_Indonesia> ;
                  dct:subject ?regionCat ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
            FILTER(?regionCat IN (
                <http://dbpedia.org/resource/Category:Geography_of_East_Nusa_Tenggara>,
                <http://dbpedia.org/resource/Category:Tourist_attractions_in_East_Nusa_Tenggara>))
        } LIMIT 20""",
}

# Volcanoes — use dbo:Volcano type with province-specific category
_VOLCANO_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Volcano .
            ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Bali> .
        } LIMIT 15""",
    "NTB": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Volcano .
            { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Lombok> }
            UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Sumbawa> }
        } LIMIT 15""",
    "NTT": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Volcano .
            ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Flores> .
        } LIMIT 15""",
}

# Museums — use dbo:Museum type with province-specific category or location
_MUSEUM_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Museum .
            { ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_Bali> }
            UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
        } LIMIT 15""",
    "NTB": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Museum .
            ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_West_Nusa_Tenggara> .
        } LIMIT 15""",
    "NTT": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Museum .
            ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_East_Nusa_Tenggara> .
        } LIMIT 15""",
}

_TEMPLE_KNOWN_BALI_QUERY = """
    PREFIX dbr: <http://dbpedia.org/resource/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?x ?name WHERE {
        VALUES ?x {
            dbr:Pura_Besakih          dbr:Pura_Tanah_Lot
            dbr:Pura_Uluwatu          dbr:Pura_Tirta_Empul
            dbr:Pura_Luhur_Batukaru   dbr:Pura_Taman_Ayun
            dbr:Pura_Goa_Lawah        dbr:Pura_Ulun_Danu_Batur
            dbr:Pura_Ulun_Danu_Beratan dbr:Pura_Penataran_Agung_Lempuyang
            dbr:Pura_Jagannatha
        }
        ?x rdfs:label ?name .
        FILTER(LANG(?name) = "en")
    }"""

_TEMPLE_DISCOVER_BALI_QUERY = """
    PREFIX dct:  <http://purl.org/dc/terms/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?x ?name WHERE {
        ?x rdfs:label ?name .
        FILTER(LANG(?name) = "en")
        FILTER(STRSTARTS(?name, "Pura "))
        ?x dct:subject <http://dbpedia.org/resource/Category:Tourist_attractions_in_Bali> .
    } LIMIT 20"""

_TEMPLE_QUERIES_BY_PROVINCE = {
    "NTB": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x ?name WHERE {
            ?x a dbo:Temple .
            ?x dct:subject <http://dbpedia.org/resource/Category:Temples_in_West_Nusa_Tenggara> .
            ?x rdfs:label ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 15""",
    "NTT": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x ?name WHERE {
            ?x a dbo:Temple .
            ?x dct:subject <http://dbpedia.org/resource/Category:Temples_in_East_Nusa_Tenggara> .
            ?x rdfs:label ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 15""",
}

# Festivals — societal events tagged as tourist attractions
_FESTIVAL_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo:  <http://dbpedia.org/ontology/>
        PREFIX dct:  <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            { ?x a dbo:SocietalEvent } UNION { ?x a dbo:Convention } UNION { ?x a dbo:MusicFestival }
            ?x dct:subject <http://dbpedia.org/resource/Category:Tourist_attractions_in_Bali> .
        } LIMIT 15""",
    "NTB": """
        PREFIX dbo:  <http://dbpedia.org/ontology/>
        PREFIX dct:  <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            { ?x a dbo:SocietalEvent } UNION { ?x a dbo:Convention } UNION { ?x a dbo:MusicFestival }
            ?x dct:subject <http://dbpedia.org/resource/Category:Tourist_attractions_in_West_Nusa_Tenggara> .
        } LIMIT 15""",
    "NTT": """
        PREFIX dbo:  <http://dbpedia.org/ontology/>
        PREFIX dct:  <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            { ?x a dbo:SocietalEvent } UNION { ?x a dbo:Convention } UNION { ?x a dbo:MusicFestival }
            ?x dct:subject <http://dbpedia.org/resource/Category:Tourist_attractions_in_East_Nusa_Tenggara> .
            FILTER NOT EXISTS {
                ?x dct:subject ?cat .
                FILTER(REGEX(STR(?cat), "election|Election|gubernatorial|parliament", "i"))
            }
            FILTER(!REGEX(STR(?x), "election|Election|gubernatorial", "i"))
        } LIMIT 15""",
}

# Hotels — dbo:Hotel type with province-specific category
_HOTEL_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Hotel .
            { ?x dct:subject <http://dbpedia.org/resource/Category:Hotels_in_Bali> }
            UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
        } LIMIT 15""",
    "NTB": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Hotel .
            ?x dct:subject <http://dbpedia.org/resource/Category:Hotels_in_West_Nusa_Tenggara> .
        } LIMIT 15""",
    "NTT": """
        PREFIX dbo: <http://dbpedia.org/ontology/>
        PREFIX dct: <http://purl.org/dc/terms/>
        SELECT DISTINCT ?x WHERE {
            ?x a dbo:Hotel .
            ?x dct:subject <http://dbpedia.org/resource/Category:Hotels_in_East_Nusa_Tenggara> .
        } LIMIT 15""",
}

# Religious ceremonies — Balinese Hindu ceremonies, NTB/NTT cultural rituals
_CEREMONY_QUERIES_BY_PROVINCE = {
    "Bali": """
        PREFIX dbr:  <http://dbpedia.org/resource/>
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?x ?name WHERE {
            ?x rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            {
                { ?x dct:subject <http://dbpedia.org/resource/Category:Hinduism_in_Bali> }
                UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Ceremonies_in_Indonesia> }
                UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Observances_set_by_the_Balinese_saka_calendar> }
                UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Observances_set_by_the_Pawukon_calendar> }
                UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Hindu_rituals_related_to_death> ;
                            dct:subject <http://dbpedia.org/resource/Category:Culture_of_Bali> }
                UNION { ?x rdfs:label "Ogoh-ogoh"@en }
            }
            FILTER NOT EXISTS {
                ?x dct:subject ?bad .
                FILTER(REGEX(STR(?bad), "Asian_Games|Asian_Para_Games|multi-sport|Populated_places|Villages|People_of"))
            }
            FILTER(?x NOT IN (
                <http://dbpedia.org/resource/Daluang_paper>,
                <http://dbpedia.org/resource/Lamak>,
                <http://dbpedia.org/resource/Balinese_Kshatriya>,
                <http://dbpedia.org/resource/Dang_Hyang_Nirartha>,
                <http://dbpedia.org/resource/Acintya>,
                <http://dbpedia.org/resource/Balinese_Hinduism>,
                <http://dbpedia.org/resource/Vasant_Panchami>
            ))
        } LIMIT 30""",
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?x ?name WHERE {
            ?x rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            ?x dct:subject <http://dbpedia.org/resource/Category:Lombok> .
            ?x dct:subject ?cat .
            FILTER(REGEX(STR(?cat), "Festival|Ceremony|Ritual|Holiday", "i"))
        } LIMIT 20""",
    "NTT": """
        PREFIX dbr:  <http://dbpedia.org/resource/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?x ?name WHERE {
            VALUES ?x { dbr:Pasola dbr:Caci }
            ?x rdfs:label ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 10""",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Public API — One function per ontology class
# Each function queries DBpedia for its class and adds individuals to the graph.
# ═══════════════════════════════════════════════════════════════════════════════

def populate_provinces(graph: Graph) -> None:
    """Add the three target provinces (Bali, NTB, NTT) as Province individuals.

    These are the top-level geographic containers. All other entities are
    eventually linked to one of these via locatedIn chains.
    """
    log.info("[Province]")
    _process_query_results(
        graph, _execute_sparql_query(_PROVINCE_QUERY), "Province",
        name_variable="x", derive_name_from_label=False,
    )


def populate_islands(graph: Graph) -> None:
    """Add islands for each province, with locatedIn linking to the province.

    NTT uses the broader 'Lesser_Sunda_Islands' category with exclusion
    filters because DBpedia lacks a direct 'Islands_of_East_Nusa_Tenggara'
    category.
    """
    log.info("[Island]")
    for province_short, query in _ISLAND_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Island",
            name_variable="x", derive_name_from_label=False,
            province_short_name=province_short,
        )
        log.info("  -> %s: %d islands", province_short, count)


def populate_cities(graph: Graph) -> None:
    """Add regencies (kabupaten) and capital cities (kota) per province.

    Combines results from two separate queries (regencies + cities) per
    province, deduplicating by English label to avoid double-counting
    entities that appear in both query patterns.

    Province-level entities are filtered out: DBpedia's category nesting
    causes 'Bali', 'West Nusa Tenggara', and 'East Nusa Tenggara' to appear
    in city-related result sets. Without this filter, the same individuals
    would be typed as both Province AND City.
    """
    log.info("[City]")

    # Local names of all provinces — must never be (re)typed as City
    province_local_names = set(PROVINCES.values())

    for province_short in PROVINCES:
        seen_names: set[str] = set()
        combined_results: list[dict] = []

        # Merge regency and city results, deduplicating by name
        for query in (_REGENCY_QUERIES_BY_PROVINCE[province_short],
                      _CITY_QUERIES_BY_PROVINCE[province_short]):
            for result_row in _execute_sparql_query(query):
                entity_name = result_row["name"]["value"]
                if entity_name in seen_names:
                    continue
                # Skip results that resolve to one of our Province individuals
                # (DBpedia categories sometimes include the province itself).
                if label_to_local(entity_name) in province_local_names:
                    log.info("  - skipped %s (already a Province)", entity_name)
                    continue
                seen_names.add(entity_name)
                combined_results.append(result_row)

        count = _process_query_results(
            graph, combined_results, "City",
            name_variable="name", derive_name_from_label=True,
            uri_variable="city", province_short_name=province_short,
        )
        log.info("  -> %s: %d cities/regencies", province_short, count)


def populate_beaches(graph: Graph) -> None:
    """Add beaches per province with locatedIn assignment.

    Bali has a dedicated 'Beaches_of_Bali' category. NTB and NTT require
    intersection with 'Beaches_of_Indonesia' + province-specific landform
    categories.
    """
    log.info("[Beach]")
    for province_short, query in _BEACH_QUERIES_BY_PROVINCE.items():
        _process_query_results(
            graph, _execute_sparql_query(query), "Beach",
            name_variable="name", derive_name_from_label=True,
            uri_variable="beach", province_short_name=province_short,
        )


def populate_parks(graph: Graph) -> None:
    """Add national parks per province with locatedIn assignment."""
    log.info("[Park]")
    for province_short, query in _PARK_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Park",
            name_variable="name", derive_name_from_label=True,
            uri_variable="park", province_short_name=province_short,
        )
        log.info("  -> %s: %d parks", province_short, count)


def populate_volcanoes(graph: Graph) -> None:
    """Add volcanoes per province with locatedIn assignment."""
    log.info("[Volcano]")
    for province_short, query in _VOLCANO_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Volcano",
            name_variable="x", derive_name_from_label=False,
            province_short_name=province_short,
        )
        log.info("  -> %s: %d volcanoes", province_short, count)


def populate_museums(graph: Graph) -> None:
    """Add museums per province with locatedIn assignment."""
    log.info("[Museum]")
    for province_short, query in _MUSEUM_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Museum",
            name_variable="x", derive_name_from_label=False,
            province_short_name=province_short,
        )
        log.info("  -> %s: %d museums", province_short, count)


def populate_temples(graph: Graph) -> None:
    """Add Hindu/Buddhist temples per province with locatedIn assignment.

    Bali uses two separate queries merged in Python (see _TEMPLE_KNOWN_BALI_QUERY
    and _TEMPLE_DISCOVER_BALI_QUERY) because DBpedia doesn't consistently type
    Balinese temples as dbo:Temple and SPARQL UNION patterns time out.
    NTB and NTT use a single category + dbo:Temple type query.
    """
    log.info("[Temple]")

    # Bali: merge known temples (VALUES) + discovery (label search), deduplicate by URI
    seen_uris: set[str] = set()
    bali_results: list[dict] = []
    for query in (_TEMPLE_KNOWN_BALI_QUERY, _TEMPLE_DISCOVER_BALI_QUERY):
        for result_row in _execute_sparql_query(query):
            uri = result_row["x"]["value"]
            if uri not in seen_uris:
                seen_uris.add(uri)
                bali_results.append(result_row)

    count = _process_query_results(
        graph, bali_results, "Temple",
        name_variable="name", derive_name_from_label=True,
        uri_variable="x", province_short_name="Bali",
    )
    log.info("  -> Bali: %d temples", count)

    # NTB and NTT: single query each
    for province_short, query in _TEMPLE_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Temple",
            name_variable="name", derive_name_from_label=True,
            uri_variable="x", province_short_name=province_short,
        )
        log.info("  -> %s: %d temples", province_short, count)


def populate_festivals(graph: Graph) -> None:
    """Add cultural festivals per province with locatedIn assignment."""
    log.info("[Festival]")
    for province_short, query in _FESTIVAL_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Festival",
            name_variable="x", derive_name_from_label=False,
            province_short_name=province_short,
        )
        log.info("  -> %s: %d festivals", province_short, count)


def populate_hotels(graph: Graph) -> None:
    """Add hotels per province with locatedIn assignment.

    Note: Hotels are typed as Accommodation (⊑ owl:Thing), which is
    disjoint from TouristAttraction. They participate in locatedIn
    but NOT hasActivity or hasTouristAttraction.
    """
    log.info("[Hotel]")
    for province_short, query in _HOTEL_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "Hotel",
            name_variable="x", derive_name_from_label=False,
            province_short_name=province_short,
        )
        log.info("  -> %s: %d hotels", province_short, count)


def populate_religious_ceremonies(graph: Graph) -> None:
    """Add religious ceremonies and cultural rituals per province.

    Bali: Balinese Hindu ceremonies (Nyepi, Galungan, Ngaben, etc.)
    NTB: Sasak cultural rituals (Gandrung, etc.)
    NTT: Manggarai/Sumbanese ceremonies (Pasola, Caci)
    """
    log.info("[ReligiousCeremony]")
    for province_short, query in _CEREMONY_QUERIES_BY_PROVINCE.items():
        count = _process_query_results(
            graph, _execute_sparql_query(query), "ReligiousCeremony",
            name_variable="name", derive_name_from_label=True,
            uri_variable="x", province_short_name=province_short,
        )
        log.info("  -> %s: %d ceremonies", province_short, count)


# ─────────────────────────────────────────────────────────────────────────────
# Area enrichment (Province + City) — fetched from DBpedia and stored in km²
# ─────────────────────────────────────────────────────────────────────────────

_AREA_QUERY_TEMPLATE = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbp: <http://dbpedia.org/property/>

SELECT ?place ?areaSqM ?areaKm2 WHERE {{
  VALUES ?place {{ {value_list} }}
  OPTIONAL {{ ?place dbo:areaTotal    ?areaSqM . }}
  OPTIONAL {{ ?place dbp:areaTotalKm2 ?areaKm2 . }}
}}
"""


def _pick_area_km2(binding: dict) -> Decimal | None:
    """Choose the best available area value and convert to km².

    Prefers ``dbp:areaTotalKm2`` (raw infobox value, already km²); falls back
    to ``dbo:areaTotal`` (m², converted by /1_000_000). Returns ``None`` if
    neither is present or both are unparseable.
    """
    raw_km2 = binding.get("areaKm2", {}).get("value")
    if raw_km2:
        try:
            return Decimal(raw_km2)
        except Exception:  # noqa: BLE001 — some infobox values are non-numeric
            pass

    raw_m2 = binding.get("areaSqM", {}).get("value")
    if raw_m2:
        try:
            return Decimal(raw_m2) / Decimal(1_000_000)
        except Exception:  # noqa: BLE001
            pass

    return None


def populate_areas(graph: Graph) -> None:
    """Fetch areaTotal/areaTotalKm2 from DBpedia for every Province and City.

    Uses the URI mapping registry built during earlier populators, so this
    must run AFTER populate_provinces and populate_cities. Issues a single
    batched SPARQL query with VALUES, then writes
        <individual> ex:hasAreaSqKm "<decimal>"^^xsd:decimal
    for every individual where DBpedia returns a usable area.
    """
    log.info("[hasAreaSqKm]")

    # Collect Province + City individuals that have a DBpedia URI
    targets: list[tuple[str, str]] = []  # (local_name, dbpedia_uri)
    for subj, _, obj in graph.triples((None, RDF.type, None)):
        if obj not in (ONT.Province, ONT.City):
            continue
        local_name = str(subj).rsplit("#", 1)[-1]
        dbpedia_uri = _local_name_to_dbpedia_uri.get(local_name)
        if dbpedia_uri:
            targets.append((local_name, dbpedia_uri))

    if not targets:
        log.info("  no Province/City individuals with DBpedia URIs found")
        return

    # Single batched query
    value_list = " ".join(f"<{uri}>" for _, uri in targets)
    query_results = _execute_sparql_query(
        _AREA_QUERY_TEMPLATE.format(value_list=value_list)
    )

    # Build URI → area mapping (last write wins; DBpedia returns one row per place)
    area_by_uri: dict[str, Decimal] = {}
    for row in query_results:
        place_uri = row.get("place", {}).get("value")
        km2 = _pick_area_km2(row)
        if place_uri and km2 is not None:
            area_by_uri[place_uri] = km2

    # Write triples
    written = 0
    for local_name, dbpedia_uri in targets:
        km2 = area_by_uri.get(dbpedia_uri)
        if km2 is None:
            log.info("  - %-30s  no area data", local_name)
            continue
        graph.add((
            ONT[local_name],
            ONT.hasAreaSqKm,
            Literal(km2, datatype=XSD.decimal),
        ))
        log.info("  + %-30s  %s km²", local_name, km2)
        written += 1

    log.info("  -> wrote %d hasAreaSqKm triples", written)


# ── Orchestrator ─────────────────────────────────────────────────────────────

ALL_POPULATORS = [
    populate_provinces,
    populate_islands,
    populate_cities,
    populate_beaches,
    populate_parks,
    populate_volcanoes,
    populate_museums,
    populate_temples,
    populate_festivals,
    populate_religious_ceremonies,
    populate_hotels,
    populate_areas,  # must run after provinces + cities (depends on URI registry)
]


def populate_all(graph: Graph) -> None:
    """Run every populator in canonical order.

    Each populator is independent — if one fails (e.g. DBpedia timeout),
    the others still succeed. The canonical order ensures provinces exist
    before other entities reference them via locatedIn.
    """
    for populator_function in ALL_POPULATORS:
        populator_function(graph)
