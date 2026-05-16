"""Shared constants, namespaces, file paths, and domain configuration.

This module holds *no* logic — only declarative data. Every other module
imports from here so that paths, namespaces, and domain mappings live in
exactly one place. Changing a file path or namespace here propagates
everywhere automatically.

Sections
--------
File Paths          Where schema.owl, data.owl, and travel.owl live on disk.
Namespaces          The ontology IRI and rdflib Namespace object.
DBpedia Config      Endpoint URL and polite throttling parameters.
Domain Mappings     Province short-name registry and activity vocabulary.
Blank Skeleton      The XML template written to data.owl on every fresh run.
"""

from pathlib import Path
from rdflib import Namespace

# ── File Paths ───────────────────────────────────────────────────────────────
# All ontology files live under the 'ontology/' subdirectory of this project.
PROJECT_DIR  = Path(__file__).resolve().parent
ONTOLOGY_DIR = PROJECT_DIR / "ontology"
SCHEMA_FILE  = ONTOLOGY_DIR / "schema.owl"       # TBox — class and property definitions
DATA_FILE    = ONTOLOGY_DIR / "data.owl"          # ABox — individuals and assertions
CATALOG_FILE = ONTOLOGY_DIR / "catalog-v001.xml"  # Protégé catalog for local resolution

# ── Namespaces ───────────────────────────────────────────────────────────────
# The ontology IRI is used as the namespace for all classes, properties,
# and individuals defined in this project.
ONT_IRI  = "http://www.semanticweb.org/emmaa/ontologies/2026/3/untitled-ontology-9#"
DATA_IRI = "http://www.semanticweb.org/emmaa/ontologies/2026/3/tourism-data"

# rdflib Namespace object — used as ONT["ClassName"] or ONT.propertyName
ONT = Namespace(ONT_IRI)

# ── DBpedia Configuration ────────────────────────────────────────────────────
# All SPARQL queries in populate.py and enrich.py hit this endpoint.
DBPEDIA_ENDPOINT = "https://dbpedia.org/sparql"
DBPEDIA_TIMEOUT_S = 30          # seconds before a single query is abandoned
DBPEDIA_THROTTLE_S = 1.0       # polite delay (seconds) between consecutive queries

# ── Domain Mappings ──────────────────────────────────────────────────────────

# Province registry: short name -> OWL individual local name.
# Used to iterate over the three target provinces and to resolve locatedIn targets.
PROVINCES = {
    "Bali": "Bali",
    "NTB":  "West_Nusa_Tenggara",
    "NTT":  "East_Nusa_Tenggara",
}

# Activity vocabulary: individuals of class :Activities (plural class name in schema).
# These are the only valid objects for the hasActivity property.
ACTIVITIES = [
    # WaterSport subclasses (schema: Surfing/Snorkeling/Diving/Sailing/Kayaking ⊑ WaterSport)
    "Surfing",
    "Snorkeling",
    "Diving",
    "Sailing",
    "Kayaking",
    # MountainSport subclasses (schema: Hiking ⊑ MountainSport)
    "Hiking",
    # Direct Activities individuals (no dedicated leaf class in schema)
    "Sightseeing",
    "Cultural_Tour",
]

# ── Blank Data OWL Skeleton ──────────────────────────────────────────────────
# Written to data.owl at the start of every pipeline run (main.py Step 1).
# Contains only the ontology declaration and the owl:imports link to schema.owl.
BLANK_DATA_OWL = f"""\
<?xml version="1.0"?>
<rdf:RDF xmlns="{DATA_IRI}/"
     xml:base="{DATA_IRI}/"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:xml="http://www.w3.org/XML/1998/namespace"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">
    <owl:Ontology rdf:about="{DATA_IRI}">
        <owl:imports rdf:resource="{ONT_IRI[:-1]}"/>
    </owl:Ontology>
</rdf:RDF>
"""
