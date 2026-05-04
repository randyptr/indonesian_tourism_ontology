"""
Populate data.owl with individuals from DBpedia (Bali, NTT, NTB – Indonesia).

Steps:
  1. Load data.owl as an RDFLib Graph (format="xml").
  2. Query DBpedia SPARQL endpoint for individuals per class.
  3. Add rdf:type triples for each new individual into the graph.
  4. Save the graph back to data.owl (RDF/XML).
  5. Load schema.owl then data.owl with owlready2 (format="rdfxml").
  6. Run HermiT reasoner, verify consistency, and show populated individuals.
"""

import os
import re
import time

from rdflib import Graph, Namespace, RDF
from SPARQLWrapper import SPARQLWrapper, JSON

# ── Namespaces ────────────────────────────────────────────────────────────────
ONT  = Namespace("http://www.semanticweb.org/emmaa/ontologies/2026/3/untitled-ontology-9#")
OWL  = Namespace("http://www.w3.org/2002/07/owl#")

SCHEMA_FILE = "schema.owl"
DATA_FILE   = "data.owl"

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 – Load data.owl with RDFLib
# ─────────────────────────────────────────────────────────────────────────────
BLANK_DATA_OWL = """\
<?xml version="1.0"?>
<rdf:RDF xmlns="http://www.semanticweb.org/emmaa/ontologies/2026/3/tourism-data/"
     xml:base="http://www.semanticweb.org/emmaa/ontologies/2026/3/tourism-data/"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:xml="http://www.w3.org/XML/1998/namespace"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
    <owl:Ontology rdf:about="http://www.semanticweb.org/emmaa/ontologies/2026/3/tourism-data">
        <owl:imports rdf:resource="http://www.semanticweb.org/emmaa/ontologies/2026/3/untitled-ontology-9"/>
    </owl:Ontology>
</rdf:RDF>
"""

print("=" * 60)
print("Step 1: Loading data.owl with RDFLib (format='xml') …")
# Reset data.owl to a clean skeleton before each run to avoid duplicates
with open(DATA_FILE, "w", encoding="utf-8") as f:
    f.write(BLANK_DATA_OWL)
g = Graph()
g.parse(DATA_FILE, format="xml")
print(f"  Triples before population: {len(g)}")

# ─────────────────────────────────────────────────────────────────────────────
# DBpedia helpers
# ─────────────────────────────────────────────────────────────────────────────
dbpedia = SPARQLWrapper("https://dbpedia.org/sparql")
dbpedia.setReturnFormat(JSON)
dbpedia.setTimeout(30)

def slugify(uri: str) -> str:
    """Convert a DBpedia resource URI to a safe OWL local name."""
    local = uri.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "_", local)

def run_query(sparql_query: str) -> list:
    dbpedia.setQuery(sparql_query)
    try:
        return dbpedia.query().convert()["results"]["bindings"]
    except Exception as exc:
        print(f"    [WARN] Query failed: {exc}")
        return []

def label_to_local(label: str) -> str:
    """Convert an English rdfs:label to a safe OWL local name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", label.strip())

def add_individual(class_local: str, ind_name: str):
    """Assert ind_name rdf:type class_local (and OWL NamedIndividual) in g."""
    ind = ONT[ind_name]
    g.add((ind, RDF.type, OWL.NamedIndividual))
    g.add((ind, RDF.type, ONT[class_local]))

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – Query DBpedia and populate the graph
# ─────────────────────────────────────────────────────────────────────────────
print("\nStep 2: Querying DBpedia and adding individuals to the graph …\n")

# ── Province ──────────────────────────────────────────────────────────────────
print("  [Province]")
q = """
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX dbo: <http://dbpedia.org/ontology/>
SELECT DISTINCT ?x WHERE {
  VALUES ?x { dbr:Bali dbr:West_Nusa_Tenggara dbr:East_Nusa_Tenggara }
  ?x a dbo:Province .
}"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Province", name)
    print(f"    + {name}")
time.sleep(1)

# ── Island ────────────────────────────────────────────────────────────────────
print("  [Island]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dbr: <http://dbpedia.org/resource/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Island .
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Islands_of_Bali> }
    UNION
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Islands_of_West_Nusa_Tenggara> }
    UNION
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Islands_of_East_Nusa_Tenggara> }
  }
} LIMIT 20"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Island", name)
    print(f"    + {name}")
time.sleep(1)

# ── City ──────────────────────────────────────────────────────────────────────
print("  [City]")

# Province IRI → individual local name (added in the Province block above)
PROVINCE_INDIVIDUALS = {
    "Bali":            "Bali",
    "NTB":             "West_Nusa_Tenggara",
    "NTT":             "East_Nusa_Tenggara",
}

# Strategy per province (DBpedia is inconsistent across provinces):
#   Bali   → dbo:subdivision from dbr:Bali gives all 8 kabupaten reliably
#   NTB/NTT → use precise Regencies_of_* categories
# For all: two simple queries per province — one for regencies (label filter),
#          one for cities (category intersection). No expensive EXISTS subqueries.
CITY_PROVINCE_MAP = {
    "Bali": "Bali",
    "NTB":  "West_Nusa_Tenggara",
    "NTT":  "East_Nusa_Tenggara",
}

# Query 1: regencies (kabupaten) per province
REGENCY_QUERIES = {
    # Bali: dbo:subdivision is reliable
    "Bali": """
        PREFIX dbo:  <http://dbpedia.org/ontology/>
        PREFIX dbr:  <http://dbpedia.org/resource/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            dbr:Bali dbo:subdivision ?city .
            ?city rdfs:label ?name .
            FILTER(LANG(?name) = "en")
            FILTER(CONTAINS(?name, "Regency"))
        } LIMIT 25
    """,
    # NTB/NTT: use precise Regencies_of_* categories
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Regencies_of_West_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 25
    """,
    "NTT": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Regencies_of_East_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 30
    """,
}

# Query 2: proper cities (kota) per province — simple category intersection, no EXISTS
CITY_QUERIES = {
    "Bali": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Cities_in_Indonesia> ;
                  dct:subject <http://dbpedia.org/resource/Category:Populated_places_in_Bali> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 10
    """,
    "NTB": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Cities_in_Indonesia> ;
                  dct:subject <http://dbpedia.org/resource/Category:Populated_places_in_West_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 10
    """,
    "NTT": """
        PREFIX dct:  <http://purl.org/dc/terms/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?city ?name WHERE {
            ?city dct:subject <http://dbpedia.org/resource/Category:Cities_in_Indonesia> ;
                  dct:subject <http://dbpedia.org/resource/Category:Populated_places_in_East_Nusa_Tenggara> ;
                  rdfs:label  ?name .
            FILTER(LANG(?name) = "en")
        } LIMIT 10
    """,
}

for prov_name in ["Bali", "NTB", "NTT"]:
    # Run regency query
    regency_results = run_query(REGENCY_QUERIES[prov_name])
    time.sleep(1)
    # Run city (kota) query
    kota_results = run_query(CITY_QUERIES[prov_name])
    time.sleep(1)

    # Merge results, deduplicate by name
    seen = set()
    combined = []
    for r in regency_results + kota_results:
        n = r["name"]["value"]
        if n not in seen:
            seen.add(n)
            combined.append(r)

    count = 0
    for r in combined:
        ind_name = label_to_local(r["name"]["value"])
        prov_ind = CITY_PROVINCE_MAP[prov_name]
        add_individual("City", ind_name)
        g.add((ONT[ind_name], ONT.locatedIn, ONT[prov_ind]))
        print(f"    + {ind_name}  (locatedIn: {prov_ind})")
        count += 1
    print(f"    → {prov_name}: {count} cities/regencies")


# ── Beach ─────────────────────────────────────────────────────────────────────
# DBpedia beaches are often not typed dbo:Beach; use dct:subject category directly
print("  [Beach]")
BEACH_CATEGORIES = [
    "Beaches_of_Bali",
    "Beaches_of_Lombok",
    "Beaches_of_Flores",
    "Beaches_of_Sumbawa",
]
cat_filters = " || ".join(
    f'?cat = <http://dbpedia.org/resource/Category:{c}>'
    for c in BEACH_CATEGORIES
)
q = f"""
    PREFIX dct:  <http://purl.org/dc/terms/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?beach ?name WHERE {{
        ?beach dct:subject ?cat ;
               rdfs:label  ?name .
        FILTER(LANG(?name) = "en")
        FILTER({cat_filters})
    }}
    LIMIT 30
"""
for r in run_query(q):
    name = label_to_local(r["name"]["value"])
    add_individual("Beach", name)
    print(f"    + {name}")
time.sleep(1)

# ── Park / National Park ──────────────────────────────────────────────────────
# Parks in DBpedia are typed dbo:ProtectedArea, not dbo:NationalPark.
# Filter by region using dct:subject geography categories — no hardcoded names.
print("  [Park]")
PARK_REGION_CATEGORIES = [
    "National_parks_of_Bali",
    "Geography_of_Bali",
    "Geography_of_West_Nusa_Tenggara",
    "Geography_of_East_Nusa_Tenggara",
    "Tourist_attractions_in_Bali",
    "Tourist_attractions_in_West_Nusa_Tenggara",
    "Tourist_attractions_in_East_Nusa_Tenggara",
]
cat_filters = " || ".join(
    f'?regionCat = <http://dbpedia.org/resource/Category:{c}>'
    for c in PARK_REGION_CATEGORIES
)
q = f"""
    PREFIX dct:  <http://purl.org/dc/terms/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT DISTINCT ?park ?name WHERE {{
        ?park dct:subject <http://dbpedia.org/resource/Category:National_parks_of_Indonesia> ;
              dct:subject ?regionCat ;
              rdfs:label  ?name .
        FILTER(LANG(?name) = "en")
        FILTER({cat_filters})
    }} LIMIT 20
"""
for r in run_query(q):
    name = label_to_local(r["name"]["value"])
    add_individual("Park", name)
    print(f"    + {name}")
time.sleep(1)

# ── Volcano ───────────────────────────────────────────────────────────────────
print("  [Volcano]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Volcano .
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Lombok> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Flores> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Volcanoes_of_Sumbawa> }
  }
} LIMIT 15"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Volcano", name)
    print(f"    + {name}")
time.sleep(1)

# ── Museum ────────────────────────────────────────────────────────────────────
print("  [Museum]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Museum .
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Museums_in_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Museums_in_West_Nusa_Tenggara> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Museums_in_East_Nusa_Tenggara> }
    UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
  }
} LIMIT 15"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Museum", name)
    print(f"    + {name}")
time.sleep(1)

# ── Temple ────────────────────────────────────────────────────────────────────
print("  [Temple]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Temple .
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Hindu_temples_in_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Temples_in_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Temples_in_Indonesia> }
    UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
  }
} LIMIT 15"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Temple", name)
    print(f"    + {name}")
time.sleep(1)

# ── Festival ──────────────────────────────────────────────────────────────────
print("  [Festival]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  { ?x a dbo:MusicFestival } UNION { ?x a dbo:Event }
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Festivals_in_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Annual_events_in_Bali> }
    UNION { ?x dcterms:subject <http://dbpedia.org/resource/Category:Festivals_in_Indonesia> }
    UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
  }
} LIMIT 15"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Festival", name)
    print(f"    + {name}")
time.sleep(1)

# ── Hotel ─────────────────────────────────────────────────────────────────────
print("  [Hotel]")
q = """
PREFIX dbo: <http://dbpedia.org/ontology/>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT DISTINCT ?x WHERE {
  ?x a dbo:Hotel .
  {
    { ?x dcterms:subject <http://dbpedia.org/resource/Category:Hotels_in_Bali> }
    UNION { ?x dbo:location <http://dbpedia.org/resource/Bali> }
  }
} LIMIT 15"""
for r in run_query(q):
    name = slugify(r["x"]["value"])
    add_individual("Hotel", name)
    print(f"    + {name}")
time.sleep(1)

print(f"\n  Triples after population: {len(g)}")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – Save graph back to data.owl (RDF/XML)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\nStep 3: Saving graph to '{DATA_FILE}' (format='xml') …")
g.serialize(destination=DATA_FILE, format="xml")
print("  Saved.")

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 – Load ontologies with owlready2 (schema first, then data)
# ─────────────────────────────────────────────────────────────────────────────
print("\nStep 4: Loading ontologies with owlready2 (format='rdfxml') …")
import owlready2 as owl2

# Map remote travel.owl IRI → local file so owlready2 doesn't fetch from internet
owl2.onto_path.append(os.path.abspath("."))
owl2.JAVA_EXE = "java"

travel_local = f"file://{os.path.abspath('travel.owl')}"
owl2.onto_path.append(os.path.abspath("."))

# Redirect the remote IRI to the local copy
travel_onto = owl2.get_ontology(travel_local).load(format="rdfxml")
# Alias the expected IRI so imports resolve correctly
owl2.get_ontology("http://www.owl-ontologies.com/travel.owl")._loaded = True
owl2.get_ontology("http://www.owl-ontologies.com/travel.owl").graph = travel_onto.graph

schema_onto = owl2.get_ontology(f"file://{os.path.abspath(SCHEMA_FILE)}").load(format="rdfxml")
print(f"  Loaded schema: {SCHEMA_FILE}")

data_onto = owl2.get_ontology(f"file://{os.path.abspath(DATA_FILE)}").load(format="rdfxml")
print(f"  Loaded data:   {DATA_FILE}")

# ─────────────────────────────────────────────────────────────────────────────
# Step 5 – Run HermiT reasoner and inspect individuals
# ─────────────────────────────────────────────────────────────────────────────
print("\nStep 5: Running HermiT reasoner …")
try:
    with data_onto:
        owl2.sync_reasoner(infer_property_values=True)
    print("  Ontology is CONSISTENT ✓")
except owl2.base.OwlReadyInconsistentOntologyError:
    print("  [ERROR] Ontology is INCONSISTENT ✗")

print("\n── Individuals per populated class ──────────────────────────────")
classes_to_show = [
    "Province", "Island", "City", "Beach",
    "Park", "Volcano", "Museum", "Temple", "Festival", "Hotel",
]
for label in classes_to_show:
    cls = schema_onto.search_one(iri=str(ONT[label]))
    if cls is None:
        cls = data_onto.search_one(iri=str(ONT[label]))
    if cls is None:
        print(f"  {label:10s}: class not found")
        continue
    inds = list(cls.instances())
    sample = [i.name for i in inds[:6]]
    tail   = " …" if len(inds) > 6 else ""
    print(f"  {label:10s} ({len(inds):2d} individuals): {sample}{tail}")

print("\nDone.")
