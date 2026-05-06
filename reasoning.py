"""HermiT-based consistency check via owlready2.

Loads schema.owl + data.owl (with travel.owl wired in to satisfy the import
chain) into a fresh owlready2 World, runs HermiT, and reports class extensions.
"""

import logging
import owlready2 as owl2

from config import SCHEMA_FILE, DATA_FILE, TRAVEL_FILE, TRAVEL_REMOTE_IRI,\
    ONTOLOGY_DIR, ONT

log = logging.getLogger(__name__)

CLASSES_TO_REPORT = [
    "Province", "Island", "City", "Beach", "Park", "Volcano",
    "Museum", "Temple", "Festival", "ReligiousCeremony", "Hotel",
]


def _load_world() -> tuple[owl2.Ontology, owl2.Ontology]:
    """Spin up a fresh World and load travel + schema + data ontologies.

    A fresh World is required: leftover owlready2 state from earlier in the
    process can cause spurious INCONSISTENT results.
    """
    owl2.default_world = owl2.World()
    owl2.onto_path.clear()
    owl2.onto_path.append(str(ONTOLOGY_DIR))
    owl2.JAVA_EXE = "java"

    # Wire the local travel.owl to satisfy the remote import IRI
    travel_uri = f"file://{TRAVEL_FILE}"
    travel = owl2.get_ontology(travel_uri).load(format="rdfxml")
    aliased = owl2.get_ontology(TRAVEL_REMOTE_IRI)
    aliased._loaded = True
    aliased.graph = travel.graph

    schema = owl2.get_ontology(f"file://{SCHEMA_FILE}").load(format="rdfxml")
    data   = owl2.get_ontology(f"file://{DATA_FILE}").load(format="rdfxml")
    return schema, data


def check_consistency() -> bool:
    """Run HermiT and report. Returns True iff consistent."""
    schema, data = _load_world()
    log.info("Loaded schema=%s data=%s", SCHEMA_FILE.name, DATA_FILE.name)

    try:
        with data:
            owl2.sync_reasoner(infer_property_values=True)
    except owl2.OwlReadyInconsistentOntologyError:
        log.error("Ontology is INCONSISTENT")
        return False

    log.info("Ontology is CONSISTENT")
    _report_classes(schema, data)
    return True


def _report_classes(schema: owl2.Ontology, data: owl2.Ontology) -> None:
    log.info("── Individuals per populated class ──")
    for label in CLASSES_TO_REPORT:
        cls = schema.search_one(iri=str(ONT[label])) or data.search_one(iri=str(ONT[label]))
        if cls is None:
            log.info("  %-20s  class not found", label)
            continue
        inds = list(cls.instances())
        sample = ", ".join(i.name for i in inds[:6])
        tail = " …" if len(inds) > 6 else ""
        log.info("  %-20s  (%2d) %s%s", label, len(inds), sample, tail)
