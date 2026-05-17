"""OWL 2 DL consistency checking via the HermiT reasoner (owlready2).

This module loads schema.owl + data.owl into owlready2's Java-backed
reasoning infrastructure and runs HermiT to verify:
    1. The ontology is logically consistent (no class is unsatisfiable).
    2. Inferred property values are materialized for downstream use.

It also reports a summary of how many individuals each class contains
after reasoning (useful for verifying that population worked correctly).

Architecture
------------
- A fresh owlready2.World is created on every call to avoid contamination
  from earlier Python-level graph manipulations.
"""

import logging
import tempfile
from pathlib import Path

import owlready2
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from config import SCHEMA_FILE, DATA_FILE, ONTOLOGY_DIR, ONT, ONT_IRI
from curated_data import (
    RESTAURANTS, STREET_VENDORS, TRADITIONAL_MARKETS,
    RESORTS, VILLAS, GUESTHOUSES, HOSTELS,
)

# Supplementary ABox files curated outside the Python pipeline.
# - .ttl is parseable; converted to RDF/XML in-memory for owlready2.
EXTRA_ABOX_TTL_FILES = [
    ONTOLOGY_DIR / "alergy_ingredients_dishes.ttl",
]

# schema.owl uses owl:imports for these two IRIs. owlready2 doesn't read
# Protégé's catalog-v001.xml, so we must pre-load them into the World under
# their declared IRI before loading schema.owl. Then the import resolves
# from cache and no HTTP fetch is attempted.
# Derived from ONT_IRI base: strip the fragment identifier and replace the
# final path segment with the establishments ontology name.
_ONT_BASE = ONT_IRI.rstrip("#").rsplit("/", 1)[0]  # "…/2026/3"
ESTABLISHMENTS_IRI = f"{_ONT_BASE}/populate_Establishments"

# Establishment class → which curated list it sources from, and which superclass
# it subclasses (used to build the same hierarchy as establishments.omn).
ESTABLISHMENT_GROUPS = [
    ("Restaurant",        "Establishments", RESTAURANTS),
    ("StreetVendor",      "Establishments", STREET_VENDORS),
    ("TraditionalMarket", "Establishments", TRADITIONAL_MARKETS),
    ("Resort",            "Accommodation",  RESORTS),
    ("Villa",             "Accommodation",  VILLAS),
    ("Guesthouse",        "Accommodation",  GUESTHOUSES),
    ("Hostel",            "Accommodation",  HOSTELS),
]

log = logging.getLogger(__name__)

# Classes whose instance counts are reported after reasoning
CLASSES_TO_REPORT = [
    "Province", "Island", "City", "Beach", "Park", "Volcano",
    "Museum", "Temple", "Festival", "ReligiousCeremony", "Hotel",
    "TraditionalDance", "TraditionalHouse",
    "Transportation", "TypicalFood",
    "WaterSport", "MountainSport",
    "Restaurant", "StreetVendor", "TraditionalMarket",
    "Resort", "Villa", "Guesthouse", "Hostel",
]


def _create_reasoning_world() -> tuple[owlready2.Ontology, owlready2.Ontology]:
    """Create a fresh owlready2 World and load all ontology files.
    
    Returns
    -------
    tuple[owlready2.Ontology, owlready2.Ontology]
        (schema_ontology, data_ontology) — both fully loaded and ready for
        reasoning.
    """
    # Reset global state
    owlready2.default_world = owlready2.World()
    owlready2.onto_path.clear()
    owlready2.onto_path.append(str(ONTOLOGY_DIR))
    owlready2.JAVA_EXE = "java"

    # Pre-load the two ontologies that schema.owl imports. owlready2 caches
    # ontologies by their declared IRI, so when schema.owl's owl:imports are
    # processed they'll resolve from cache instead of triggering HTTP fetches.
    for ttl_path in EXTRA_ABOX_TTL_FILES:
        if not ttl_path.exists():
            log.warning("Extra ABox not found, skipping: %s", ttl_path.name)
            continue
        _load_graph_into_world(_graph_from_ttl(ttl_path))
        log.info("Pre-loaded: %s", ttl_path.name)

    _load_graph_into_world(_build_establishments_graph())
    log.info("Pre-loaded: establishments (synthesised from curated_data)")

    # Load schema (TBox) and data (ABox). schema.owl's imports now resolve
    # from cache, so no HTTP is attempted.
    schema_ontology = owlready2.get_ontology(f"file://{SCHEMA_FILE}").load(format="rdfxml")
    data_ontology = owlready2.get_ontology(f"file://{DATA_FILE}").load(format="rdfxml")

    return schema_ontology, data_ontology


def _graph_from_ttl(ttl_path: Path) -> Graph:
    """Parse a Turtle file into an rdflib Graph."""
    graph = Graph()
    graph.parse(ttl_path, format="turtle")
    return graph


def _build_establishments_graph() -> Graph:
    """Synthesise the populate_Establishments ontology from curated_data.

    Builds an rdflib Graph that mirrors the content of establishments.omn:
    a class hierarchy stub (Restaurant, StreetVendor, etc. with their
    superclasses) plus one NamedIndividual per curated entry, each typed,
    labelled, and linked via locatedIn to its province. The graph declares
    its IRI as ESTABLISHMENTS_IRI so owlready2 caches it under the same
    IRI that schema.owl imports, allowing the import to resolve from memory
    without triggering an HTTP fetch.
    """
    graph = Graph()
    ns_iri = URIRef(ESTABLISHMENTS_IRI)
    # ontology header
    graph.add((ns_iri, RDF.type, OWL.Ontology))

    # Class stubs with SubClassOf
    superclasses = {"Accommodation", "Establishments"}
    for sup in superclasses:
        graph.add((ONT[sup], RDF.type, OWL.Class))
    for class_name, super_name, _items in ESTABLISHMENT_GROUPS:
        graph.add((ONT[class_name], RDF.type, OWL.Class))
        graph.add((ONT[class_name], RDFS.subClassOf, ONT[super_name]))

    # locatedIn property stub
    graph.add((ONT["locatedIn"], RDF.type, OWL.ObjectProperty))

    # Individuals
    for class_name, _super, items in ESTABLISHMENT_GROUPS:
        for entry in items:
            ind = ONT[entry["name"]]
            graph.add((ind, RDF.type, OWL.NamedIndividual))
            graph.add((ind, RDF.type, ONT[class_name]))
            graph.add((ind, RDFS.label, Literal(entry["name"].replace("_", " "))))
            graph.add((ind, ONT["locatedIn"], ONT[entry["locatedIn"]]))
    return graph


def _load_graph_into_world(graph: Graph) -> None:
    """Serialize an rdflib Graph to a temp RDF/XML file and load via owlready2.

    owlready2 registers the loaded ontology under whatever IRI the file
    declares, making it discoverable to subsequent owl:imports resolutions.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".owl", delete=False, mode="wb"
    ) as tmp:
        graph.serialize(destination=tmp.name, format="xml")
        tmp_path = tmp.name
    try:
        owlready2.get_ontology(f"file://{tmp_path}").load(format="rdfxml")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def check_consistency() -> bool:
    """Run the HermiT reasoner and report whether the ontology is consistent.

    Loads all ontology files from disk, runs HermiT with property-value
    inference enabled, and logs the result. If consistent, also prints
    a per-class instance count summary.

    Returns
    -------
    bool
        True if the ontology is consistent, False if HermiT finds a
        logical contradiction (e.g. an individual belonging to two
        disjoint classes).
    """
    schema_ontology, data_ontology = _create_reasoning_world()
    log.info("Loaded schema=%s data=%s", SCHEMA_FILE.name, DATA_FILE.name)

    try:
        with data_ontology:
            owlready2.sync_reasoner(infer_property_values=True)
    except owlready2.OwlReadyInconsistentOntologyError:
        log.error("Ontology is INCONSISTENT")
        return False

    log.info("Ontology is CONSISTENT")
    _report_class_populations(schema_ontology, data_ontology)
    return True


def _report_class_populations(
    schema_ontology: owlready2.Ontology,
    data_ontology: owlready2.Ontology,
) -> None:
    """Log how many individuals each ontology class contains after reasoning.

    This serves as a quick sanity check: if a class that should be populated
    shows 0 individuals, something went wrong in the population step.

    Parameters
    ----------
    schema_ontology : owlready2.Ontology
        The loaded TBox ontology (class definitions live here).
    data_ontology : owlready2.Ontology
        The loaded ABox ontology (individuals live here).
    """
    log.info("── Individuals per populated class ──")

    for class_label in CLASSES_TO_REPORT:
        # Search both ontologies because some classes may be defined in schema
        # but instantiated in data
        owl_class = (
            schema_ontology.search_one(iri=str(ONT[class_label]))
            or data_ontology.search_one(iri=str(ONT[class_label]))
        )

        if owl_class is None:
            log.info("  %-20s  class not found", class_label)
            continue

        individuals = list(owl_class.instances())
        sample_names = ", ".join(ind.name for ind in individuals[:6])
        overflow_indicator = " …" if len(individuals) > 6 else ""
        log.info(
            "  %-20s  (%2d) %s%s",
            class_label, len(individuals), sample_names, overflow_indicator,
        )
