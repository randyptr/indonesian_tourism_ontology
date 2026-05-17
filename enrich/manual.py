"""Steps 12–18: Manual individual population from curated_data."""

import logging

from rdflib import Graph

from graph_utils import add_individual, add_relation, has_type
from curated_data import (
    TRANSPORTATION, FESTIVALS,
    TRADITIONAL_DANCES, TRADITIONAL_HOUSES,
    BEACHES_MANUAL, RELIGIOUS_CEREMONIES, TEMPLES,
)
from enrich.utils import CAPITAL_OF_PROVINCE, _add_cultural_individuals

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Step 12: Manual Transportation individuals
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Step 13: Manual Festival individuals
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Steps 14–15: Manual TraditionalDance and TraditionalHouse individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_manual_traditional_dances(graph: Graph) -> None:
    """Add TraditionalDance individuals from curated_data.TRADITIONAL_DANCES."""
    log.info("[Traditional Dances]")
    _add_cultural_individuals(graph, TRADITIONAL_DANCES, "TraditionalDance", "traditional dances")


def add_manual_traditional_houses(graph: Graph) -> None:
    """Add TraditionalHouse individuals from curated_data.TRADITIONAL_HOUSES."""
    log.info("[Traditional Houses]")
    _add_cultural_individuals(graph, TRADITIONAL_HOUSES, "TraditionalHouse", "traditional houses")


# ─────────────────────────────────────────────────────────────────────────────
# Step 16: Manual Beach individuals
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Step 17: Manual ReligiousCeremony individuals
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Step 18: Manual Temple individuals
# ─────────────────────────────────────────────────────────────────────────────
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
