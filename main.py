"""End-to-end ontology population pipeline.

Orchestrates the full workflow from an empty data.owl to a populated,
enriched, and consistency-checked knowledge graph:

    Step 1: Reset data.owl to a blank skeleton (imports schema.owl only).
    Step 2: Query DBpedia to populate individuals (provinces, islands, etc.).
    Step 3: Enrich with relational triples (locatedIn, hasActivity, etc.).
    Step 4: Serialize the final graph to data.owl.
    Step 5: Run HermiT reasoner to verify OWL 2 DL consistency.

Run with:
    python main.py
"""

import logging

from rdflib import Graph

from config import DATA_FILE, BLANK_DATA_OWL
from populate import populate_all
from enrich import enrich_all
from reasoning import check_consistency


def setup_logging() -> None:
    """Configure root logger to print messages without timestamps.

    Uses a minimal format (message only) since this is a batch script,
    not a long-running service.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def reset_data_file() -> Graph:
    """Wipe data.owl back to the blank skeleton and return a fresh graph.

    Overwrites the existing data.owl with BLANK_DATA_OWL (which contains
    only the ontology declaration and the owl:imports link to schema.owl),
    then parses it into a new rdflib Graph ready for population.

    Returns
    -------
    rdflib.Graph
        A graph containing only the 2 skeleton triples (ontology + import).
    """
    DATA_FILE.write_text(BLANK_DATA_OWL, encoding="utf-8")
    graph = Graph()
    graph.parse(str(DATA_FILE), format="xml")
    return graph


def save_graph(graph: Graph) -> None:
    """Serialize the populated graph to data.owl in RDF/XML format.

    This overwrites the file that was reset in Step 1, now containing
    all individuals and relationships added during Steps 2-3.
    """
    graph.serialize(destination=str(DATA_FILE), format="xml")


def main() -> None:
    """Execute the full pipeline: reset → populate → enrich → save → reason."""
    setup_logging()
    log = logging.getLogger("main")

    log.info("=" * 60)
    log.info("Step 1: Reset data.owl and load with rdflib")
    graph = reset_data_file()
    log.info("  Triples (skeleton): %d", len(graph))

    log.info("\nStep 2: Query DBpedia and add individuals")
    populate_all(graph)
    log.info("  Triples (after populate): %d", len(graph))

    log.info("\nStep 3: Enrich with relational triples (auto from DBpedia)")
    enrich_all(graph)
    log.info("  Triples (after enrich):   %d", len(graph))

    log.info("\nStep 4: Save data.owl")
    save_graph(graph)
    log.info("  Saved -> %s", DATA_FILE)

    log.info("\nStep 5: Run HermiT reasoner")
    check_consistency()


if __name__ == "__main__":
    main()
