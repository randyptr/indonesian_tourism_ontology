"""Populate the graph with individuals fetched from DBpedia.

Each public function fetches one tourism class (Province, Beach, Park, …) and
adds rdf:type triples (and a minimal locatedIn for Province-aware classes) to
the supplied rdflib graph. Relational enrichment lives in `enrich.py`.
"""

import time
import logging
from typing import Iterable

from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

from config import (
    DBPEDIA_ENDPOINT, DBPEDIA_TIMEOUT_S, DBPEDIA_THROTTLE_S,
    PROVINCES, ONT,
)
from graph_utils import slugify, label_to_local, add_individual

log = logging.getLogger(__name__)

# ── SPARQL client (single shared instance) ────────────────────────────────────
_sparql = SPARQLWrapper(DBPEDIA_ENDPOINT)
_sparql.setReturnFormat(JSON)
_sparql.setTimeout(DBPEDIA_TIMEOUT_S)


def _run_query(query: str) -> list[dict]:
    """Execute a SPARQL query and return result bindings (or [] on failure)."""
    _sparql.setQuery(query)
    try:
        return _sparql.query().convert()["results"]["bindings"]
    except Exception as exc:
        log.warning("Query failed: %s", exc)
        return []
    finally:
        time.sleep(DBPEDIA_THROTTLE_S)


def _add_results(g: Graph, results: Iterable[dict], cls: str,
                 *, name_var: str, name_from_label: bool,
                 prov_short: str | None = None) -> int:
    """Common loop: turn SPARQL bindings into individuals + locatedIn edges."""
    count = 0
    for r in results:
        if name_from_label:
            local = label_to_local(r[name_var]["value"])
        else:
            local = slugify(r[name_var]["value"])
        add_individual(g, cls, local)
        if prov_short is not None:
            prov_ind = PROVINCES[prov_short]
            g.add((ONT[local], ONT.locatedIn, ONT[prov_ind]))
            log.info("  + %s  (locatedIn: %s)", local, prov_ind)
        else:
            log.info("  + %s", local)
        count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Per-class SPARQL queries (kept inline for readability — they're short)
# ─────────────────────────────────────────────────────────────────────────────

_PROVINCE_Q = """
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX dbo: <http://dbpedia.org/ontology/>
SELECT DISTINCT ?x WHERE {
  VALUES ?x { dbr:Bali dbr:West_Nusa_Tenggara dbr:East_Nusa_Tenggara }
  ?x a dbo:Province .
}"""

_ISLAND_Q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Island .
  { ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_Bali> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_West_Nusa_Tenggara> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Islands_of_East_Nusa_Tenggara> }
} LIMIT 20"""

# Regencies (kabupaten) — Bali uses dbo:subdivision; NTB/NTT use precise category
_REGENCY_QUERIES = {
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

# Kota (capital cities) — category intersection
_CITY_QUERIES = {
    prov: f"""
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {{
            ?city dct:subject <http://dbpedia.org/resource/Category:Cities_in_Indonesia> ;
                  dct:subject <http://dbpedia.org/resource/Category:Populated_places_in_{full}> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        }} LIMIT 10"""
    for prov, full in PROVINCES.items()
}

# Beaches — Bali has its own category; NTB/NTT intersect Beaches_of_Indonesia
_BEACH_QUERIES = {
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

# Parks: typed dbo:ProtectedArea; intersect National_parks_of_Indonesia with region category
_PARK_REGION_CATS = [
    "National_parks_of_Bali",
    "Geography_of_Bali",
    "Geography_of_West_Nusa_Tenggara",
    "Geography_of_East_Nusa_Tenggara",
    "Tourist_attractions_in_Bali",
    "Tourist_attractions_in_West_Nusa_Tenggara",
    "Tourist_attractions_in_East_Nusa_Tenggara",
]
_PARK_Q = f"""
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?park ?name WHERE {{
    ?park dct:subject <http://dbpedia.org/resource/Category:National_parks_of_Indonesia> ;
          dct:subject ?regionCat ;
          rdfs:label  ?name .
    FILTER(LANG(?name) = "en")
    FILTER({" || ".join(f"?regionCat = <http://dbpedia.org/resource/Category:{c}>" for c in _PARK_REGION_CATS)})
}} LIMIT 20"""

_VOLCANO_Q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Volcano .
  { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Bali> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Lombok> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Flores> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Sumbawa> }
} LIMIT 15"""

_MUSEUM_Q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Museum .
  { ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_Bali> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_West_Nusa_Tenggara> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Museums_in_East_Nusa_Tenggara> }
  UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
} LIMIT 15"""

_TEMPLE_Q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Temple .
  { ?x dct:subject <http://dbpedia.org/resource/Category:Hindu_temples_in_Bali> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Temples_in_Bali> }
  UNION { ?x dct:subject <http://dbpedia.org/resource/Category:Temples_in_Indonesia> }
  UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
} LIMIT 15"""

_FESTIVAL_Q = """
PREFIX dbo:  <http://dbpedia.org/ontology/>
PREFIX dct:  <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  { ?x a dbo:SocietalEvent } UNION { ?x a dbo:Convention } UNION { ?x a dbo:MusicFestival }
  ?x dct:subject <http://dbpedia.org/resource/Category:Tourist_attractions_in_Bali> .
} LIMIT 15"""

_HOTEL_Q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Hotel .
  { ?x dct:subject <http://dbpedia.org/resource/Category:Hotels_in_Bali> }
  UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
} LIMIT 15"""

# Religious ceremonies
_CEREMONY_QUERIES = {
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


# ─────────────────────────────────────────────────────────────────────────────
# Public API — one function per ontology class
# ─────────────────────────────────────────────────────────────────────────────

def populate_provinces(g: Graph) -> None:
    log.info("[Province]")
    _add_results(g, _run_query(_PROVINCE_Q), "Province", name_var="x", name_from_label=False)

def populate_islands(g: Graph) -> None:
    log.info("[Island]")
    _add_results(g, _run_query(_ISLAND_Q), "Island", name_var="x", name_from_label=False)

def populate_cities(g: Graph) -> None:
    """Regencies (kabupaten) + capital cities (kota) per province."""
    log.info("[City]")
    for prov in PROVINCES:
        seen, combined = set(), []
        for q in (_REGENCY_QUERIES[prov], _CITY_QUERIES[prov]):
            for r in _run_query(q):
                if (n := r["name"]["value"]) not in seen:
                    seen.add(n)
                    combined.append(r)
        n = _add_results(g, combined, "City", name_var="name",
                         name_from_label=True, prov_short=prov)
        log.info("  → %s: %d cities/regencies", prov, n)

def populate_beaches(g: Graph) -> None:
    log.info("[Beach]")
    for prov, q in _BEACH_QUERIES.items():
        _add_results(g, _run_query(q), "Beach", name_var="name",
                     name_from_label=True, prov_short=prov)

def populate_parks(g: Graph) -> None:
    log.info("[Park]")
    _add_results(g, _run_query(_PARK_Q), "Park", name_var="name", name_from_label=True)

def populate_volcanoes(g: Graph) -> None:
    log.info("[Volcano]")
    _add_results(g, _run_query(_VOLCANO_Q), "Volcano", name_var="x", name_from_label=False)

def populate_museums(g: Graph) -> None:
    log.info("[Museum]")
    _add_results(g, _run_query(_MUSEUM_Q), "Museum", name_var="x", name_from_label=False)

def populate_temples(g: Graph) -> None:
    log.info("[Temple]")
    _add_results(g, _run_query(_TEMPLE_Q), "Temple", name_var="x", name_from_label=False)

def populate_festivals(g: Graph) -> None:
    log.info("[Festival]")
    _add_results(g, _run_query(_FESTIVAL_Q), "Festival", name_var="x", name_from_label=False)

def populate_hotels(g: Graph) -> None:
    log.info("[Hotel]")
    _add_results(g, _run_query(_HOTEL_Q), "Hotel", name_var="x", name_from_label=False)

def populate_religious_ceremonies(g: Graph) -> None:
    log.info("[ReligiousCeremony]")
    for prov, q in _CEREMONY_QUERIES.items():
        n = _add_results(g, _run_query(q), "ReligiousCeremony",
                         name_var="name", name_from_label=True, prov_short=prov)
        log.info("  → %s: %d ceremonies", prov, n)


# Single entry point that runs them all in the canonical order
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
]


def populate_all(g: Graph) -> None:
    """Run every populator in order. Each one is independent and can be skipped."""
    for fn in ALL_POPULATORS:
        fn(g)
