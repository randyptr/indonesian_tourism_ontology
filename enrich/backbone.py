"""Step 1-2: Country backbone and Bali_Island fix."""

import logging

from rdflib import Graph

from config import ONT, PROVINCES
from graph_utils import add_individual, add_relation
from enrich.utils import CAPITAL_OF_PROVINCE

log = logging.getLogger(__name__)


def add_country_backbone(graph: Graph) -> None:
    """Create Indonesia as Country and link the 3 provinces to it.

    Also explicitly re-asserts rdf:type ONT.Province for each province.
    populate_provinces() may type them with dbo:Province (DBpedia namespace)
    rather than ONT.Province — without this re-assertion, build_entity_type_map
    in graph_embedding.py won't find them (it filters by ONT_IRI prefix), so
    Province entities are invisible in the t-SNE plot and link predictions.

    Triples added (per province):
        Indonesia            rdf:type         Country
        <Province>           rdf:type         Province   ← guaranteed ONT namespace
        <Province>           locatedInCountry Indonesia
    """
    log.info("[Country Backbone]")
    add_individual(graph, "Country", "Indonesia")
    for province_name in PROVINCES.values():
        add_individual(graph, "Province", province_name)   # ensures ONT.Province type
        add_relation(graph, province_name, "locatedInCountry", "Indonesia")
    log.info("  -> 3 provinces typed as ONT.Province and linked to Indonesia")


def add_bali_island(graph: Graph) -> None:
    """Create Bali_Island as an Island individual.

    Why manual: DBpedia's "Bali" is typed as dbo:Province, not dbo:Island.
    But our ontology needs an Island entity for Bali so that City individuals
    in Bali can use locatedInIsland -> Bali_Island (domain = City).
    """
    log.info("[Bali Island Fix]")
    add_individual(graph, "Island", "Bali_Island")
    add_relation(graph, "Bali_Island", "locatedInProvince", "Bali")
    log.info("  + Bali_Island (DBpedia types Bali as Province, not Island)")
