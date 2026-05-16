"""End-to-end ontology population pipeline.

Run with:
    python main.py
"""

import logging

from rdflib import Graph

from config import DATA_FILE, BLANK_DATA_OWL
from populate import populate_all
from enrich import enrich_all
from reasoning import check_consistency


def reset_data_file() -> Graph:
    """Wipe data.owl to the blank skeleton and return a fresh graph."""
    DATA_FILE.write_text(BLANK_DATA_OWL, encoding="utf-8")
    graph = Graph()
    graph.parse(str(DATA_FILE), format="xml")
    return graph


def save_graph(graph: Graph) -> None:
    """Serialize the graph to data.owl in RDF/XML format."""
    graph.serialize(destination=str(DATA_FILE), format="xml")


def main() -> None:
    """Execute the full pipeline: reset → populate → enrich → save → reason."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("main")

    log.info("=" * 60)
    log.info("Step 1: Reset data.owl")
    graph = reset_data_file()
    log.info("  Triples (skeleton): %d", len(graph))

    log.info("\nStep 2: Query DBpedia and add individuals")
    populate_all(graph)
    log.info("  Triples (after populate): %d", len(graph))

    log.info("\nStep 3: Enrich with relational triples")
    enrich_all(graph)
    log.info("  Triples (after enrich):   %d", len(graph))

    log.info("\nStep 4: Save data.owl")
    save_graph(graph)
    log.info("  Saved -> %s", DATA_FILE)

    log.info("\nStep 5: Run HermiT reasoner")
    check_consistency()


if __name__ == "__main__":
    main()
