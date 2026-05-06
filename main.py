"""End-to-end pipeline: populate → enrich → save → reason.

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
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def reset_data_file() -> Graph:
    """Wipe data.owl back to the blank skeleton and return a fresh rdflib Graph."""
    DATA_FILE.write_text(BLANK_DATA_OWL, encoding="utf-8")
    g = Graph()
    g.parse(str(DATA_FILE), format="xml")
    return g


def save_graph(g: Graph) -> None:
    g.serialize(destination=str(DATA_FILE), format="xml")


def main() -> None:
    setup_logging()
    log = logging.getLogger("main")

    log.info("=" * 60)
    log.info("Step 1: Reset data.owl and load with rdflib")
    g = reset_data_file()
    log.info("  Triples (skeleton): %d", len(g))

    log.info("\nStep 2: Query DBpedia and add individuals")
    populate_all(g)
    log.info("  Triples (after populate): %d", len(g))

    log.info("\nStep 3: Enrich with relational triples")
    # enrich_all(g)
    # log.info("  Triples (after enrich):   %d", len(g))

    log.info("\nStep 4: Save data.owl")
    save_graph(g)
    log.info("  Saved → %s", DATA_FILE)

    log.info("\nStep 5: Run HermiT reasoner")
    check_consistency()


if __name__ == "__main__":
    main()
