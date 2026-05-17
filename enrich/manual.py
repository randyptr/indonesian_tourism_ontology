"""Manual individual population from curated_data."""

import logging

from rdflib import Graph

from graph_utils import add_individual, add_relation, has_type, local_name
from curated_data import (
    TRANSPORTATION, FESTIVALS,
    TRADITIONAL_DANCES, TRADITIONAL_HOUSES,
    BEACHES_MANUAL, RELIGIOUS_CEREMONIES, TEMPLES,
    EXTRA_CITIES, EXTRA_LINKS,
)
from enrich.utils import CAPITAL_OF_PROVINCE, _add_cultural_individuals

log = logging.getLogger(__name__)

# Manual Transportation individuals
def add_manual_transportation(graph: Graph) -> None:
    """Add Transportation individuals from curated_data.TRANSPORTATION.

    For each entry:
        1. Creates the individual with its specific subclass (AirTransport,
           LandTransport, or WaterTransport).
        2. Adds locatedIn -> Province.
        3. Links the provincial capital to it via City -> hasTransportation.

    Example triples added:
        ont:Ngurah_Rai_International_Airport  rdf:type  ont:AirTransport
        ont:Ngurah_Rai_International_Airport  ont:locatedIn  ont:Bali
        ont:Denpasar  ont:hasTransportation  ont:Ngurah_Rai_International_Airport
    """
    log.info("[Transportation]")
    added_count = 0

    for entry in TRANSPORTATION:
        individual_name  = entry["name"]
        owl_class        = entry["type"]
        province_name    = entry["locatedIn"]

        # Create the individual and link to province
        add_individual(graph, owl_class, individual_name)
        add_relation(graph, individual_name, "locatedIn", province_name)

        # Link the provincial capital to this transportation node
        capital_name = CAPITAL_OF_PROVINCE.get(province_name)
        if capital_name and has_type(graph, capital_name, "City"):
            add_relation(graph, capital_name, "hasTransportation", individual_name)

        added_count += 1

    log.info("  -> %d individuals added", added_count)

# Manual Festival individuals
def add_manual_festivals(graph: Graph) -> None:
    """Add Festival individuals for NTB and NTT from curated_data.FESTIVALS."""
    log.info("[Festivals]")
    added_count = 0

    for entry in FESTIVALS:
        individual_name = entry["name"]
        province_name   = entry["locatedIn"]

        add_individual(graph, "Festival", individual_name)
        add_relation(graph, individual_name, "locatedIn", province_name)

        # Assign default activity directly — these won't be picked up by
        # add_activity_links() since they have no DBpedia URI
        add_relation(graph, individual_name, "hasActivity", "Cultural_Tour")

        added_count += 1

    log.info("  -> %d individuals added", added_count)

# Manual TraditionalDance and TraditionalHouse individuals
def add_manual_traditional_dances(graph: Graph) -> None:
    """Add TraditionalDance individuals from curated_data.TRADITIONAL_DANCES."""
    log.info("[Traditional Dances]")
    _add_cultural_individuals(graph, TRADITIONAL_DANCES, "TraditionalDance", "traditional dances")

def add_manual_traditional_houses(graph: Graph) -> None:
    """Add TraditionalHouse individuals from curated_data.TRADITIONAL_HOUSES."""
    log.info("[Traditional Houses]")
    _add_cultural_individuals(graph, TRADITIONAL_HOUSES, "TraditionalHouse", "traditional houses")

# Manual Beach individuals
def add_manual_beaches(graph: Graph) -> None:
    """Add Beach individuals from curated_data.BEACHES_MANUAL.

    Supplements DBpedia output: NTB and NTT beaches are rarely returned by the
    DBpedia populate step; Bali entries fill specific gaps. Each beach receives
    the full set of water-sport activity links.

    Each entry gets:
        rdf:type Beach
        locatedIn -> Province
        hasActivity -> Surfing, Snorkeling, Sailing, Kayaking
        City -> hasTouristAttraction -> Beach  (hub link)
    """
    log.info("[Beaches]")
    _add_cultural_individuals(
        graph, BEACHES_MANUAL, "Beach", "beaches",
        activities=["Surfing", "Snorkeling", "Sailing", "Kayaking"],
    )

# Manual ReligiousCeremony individuals
def add_manual_religious_ceremonies(graph: Graph) -> None:
    """Add ReligiousCeremony individuals from curated_data.RELIGIOUS_CEREMONIES.

    DBpedia returns near-zero structured results for ReligiousCeremony across
    all three provinces. All entries are therefore manual.

    Each entry gets:
        rdf:type ReligiousCeremony
        locatedIn -> Province
        hasActivity -> Cultural_Tour
        City -> hasTouristAttraction -> ReligiousCeremony  (hub link)
    """
    log.info("[Religious Ceremonies]")
    _add_cultural_individuals(
        graph, RELIGIOUS_CEREMONIES, "ReligiousCeremony", "religious ceremonies",
    )

# Manual Temple individuals
def add_manual_temples(graph: Graph) -> None:
    """Add Temple individuals from curated_data.TEMPLES.

    DBpedia covers some famous Bali temples; NTB and NTT have no structured
    Temple results. Bali entries here supplement DBpedia output — rdflib triples
    are idempotent so adding an existing individual's type/locatedIn is safe.

    Each entry gets:
        rdf:type Temple
        locatedIn -> Province
        hasActivity -> Cultural_Tour
        City -> hasTouristAttraction -> Temple  (hub link)
    """
    log.info("[Temples]")
    _add_cultural_individuals(
        graph, TEMPLES, "Temple", "temples",
    )


def add_extra_cities(graph: Graph) -> None:
    """Add City individuals not returned by DBpedia's populate step.

    Each EXTRA_CITIES entry provides locatedIn / locatedInIsland /
    locatedInProvince in one place, so the data lives in curated_data.py
    rather than being hardcoded here.
    """
    log.info("[Extra Cities]")
    count = 0
    for entry in EXTRA_CITIES:
        name = entry["name"]
        if has_type(graph, name, "City"):
            continue
        add_individual(graph, "City", name)
        add_relation(graph, name, "locatedIn",         entry["locatedIn"])
        add_relation(graph, name, "locatedInIsland",   entry["locatedInIsland"])
        add_relation(graph, name, "locatedInProvince", entry["locatedInProvince"])
        count += 1
    log.info("  -> %d cities added", count)


def add_extra_links(graph: Graph) -> None:
    """Apply curated (subject, predicate, object) triples from EXTRA_LINKS.

    Used for sparse entities where DBpedia provides no useful connections and
    for known semantic facts (e.g. Komodo NP supports more activities than
    just diving) that the automated enrichers can't infer.
    """
    log.info("[Extra Links]")
    for s, p, o in EXTRA_LINKS:
        add_relation(graph, s, p, o)
    log.info("  -> %d triples added", len(EXTRA_LINKS))
