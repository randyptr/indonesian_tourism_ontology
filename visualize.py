"""Render the tourism ontology as an interactive HTML network graph (PyVis).

Reads both data.owl (individuals) and schema.owl (class definitions), then
creates a force-directed graph where:
    - Nodes represent OWL individuals, coloured by their rdf:type class.
    - Edges represent object-property assertions (locatedIn, hasActivity, etc.).
    - TBox/meta triples (subClassOf, domain, range) are excluded.
    - A colour legend is anchored to the left side of the canvas.

Output: ontology_graph.html — open in any browser to pan, zoom, and explore.

Run:
    python visualize.py
"""

import logging
from pathlib import Path
from rdflib import Graph, URIRef, RDF, RDFS, OWL
from pyvis.network import Network

from config import SCHEMA_FILE, DATA_FILE, ONT_IRI
from graph_utils import local_name

log = logging.getLogger(__name__)

# Output file name for the interactive HTML visualization
OUTPUT_HTML_FILE = "./graph_vis/ontology_graph.html"

# ── Colour Palette ───────────────────────────────────────────────────────────
# Each ontology class gets a distinct colour for visual differentiation.
# "Other" is the fallback for individuals whose class isn't in this map.
CLASS_COLOUR_MAP = {
    "Province":          "#e41a1c",   # red
    "Island":            "#377eb8",   # blue
    "City":              "#4daf4a",   # green
    "Beach":             "#ff7f00",   # orange
    "Park":              "#984ea3",   # purple
    "Volcano":           "#a65628",   # brown
    "Museum":            "#f781bf",   # pink
    "Temple":            "#999999",   # grey
    "Festival":          "#ffff33",   # yellow
    "Hotel":             "#17becf",   # cyan
    "ReligiousCeremony": "#bcbd22",   # olive
    "Activities":        "#bf9a30",   # gold
    "Country":           "#000000",   # black
    "Other":             "#cccccc",   # light grey (fallback)
}

# Predicates that belong to the TBox or meta-level — never shown as edges
TBOX_PREDICATES_TO_SKIP = {
    RDF.type, RDFS.label, RDFS.comment, OWL.sameAs,
    RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range,
    OWL.equivalentClass, OWL.equivalentProperty,
    OWL.inverseOf, OWL.disjointWith,
}


def _load_combined_graph() -> Graph:
    """Load and merge both data.owl and schema.owl into a single rdflib Graph.

    Both files are needed because:
    - data.owl contains the individuals and object-property assertions.
    - schema.owl contains the class definitions needed for type colouring.
    """
    combined_graph = Graph()
    combined_graph.parse(str(DATA_FILE), format="xml")
    combined_graph.parse(str(SCHEMA_FILE), format="xml")
    return combined_graph


def _build_individual_type_map(graph: Graph) -> dict[str, str]:
    """Map each individual's full IRI to its primary ontology class name.

    Scans all rdf:type triples and keeps only those whose object is in our
    ontology namespace (ignoring owl:NamedIndividual and external types).

    Parameters
    ----------
    graph : rdflib.Graph
        The merged knowledge graph.

    Returns
    -------
    dict[str, str]
        Mapping from individual IRI string to class local name
        (e.g. 'http://...#Pandawa_Beach' -> 'Beach').
    """
    type_map: dict[str, str] = {}
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if not isinstance(object_type, URIRef) or object_type == OWL.NamedIndividual:
            continue
        if str(object_type).startswith(ONT_IRI):
            type_map[str(subject)] = local_name(object_type)
    return type_map


def _is_ontology_entity(node: URIRef) -> bool:
    """Check whether a node belongs to our ontology namespace.

    Only ontology entities are shown in the visualization — external IRIs
    (DBpedia, OWL, RDF namespace) are excluded.
    """
    return isinstance(node, URIRef) and str(node).startswith(ONT_IRI)


def _build_network_graph(
    graph: Graph,
    individual_type_map: dict[str, str],
) -> Network:
    """Construct a PyVis Network from the knowledge graph triples.

    Iterates over all triples, skipping TBox predicates and non-ontology
    entities. Each remaining triple becomes a directed edge between two
    coloured nodes.

    Parameters
    ----------
    graph : rdflib.Graph
        The merged knowledge graph (data + schema).
    individual_type_map : dict[str, str]
        Maps individual IRI -> class name (for node colouring).

    Returns
    -------
    pyvis.network.Network
        The fully constructed network ready for HTML export.
    """
    network = Network(
        height="800px", width="100%", bgcolor="#ffffff",
        font_color="#222", directed=True, notebook=False,
    )
    network.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120)

    nodes_already_added: set[str] = set()

    def _ensure_node_exists(entity_iri: str) -> None:
        """Add a node for the entity if it hasn't been added yet."""
        if entity_iri in nodes_already_added:
            return
        nodes_already_added.add(entity_iri)

        entity_class = individual_type_map.get(entity_iri, "Other")
        node_colour = CLASS_COLOUR_MAP.get(entity_class, CLASS_COLOUR_MAP["Other"])
        entity_label = local_name(entity_iri)

        network.add_node(
            entity_iri, label=entity_label, size=18,
            color=node_colour, title=f"{entity_label}\n({entity_class})",
        )

    # Add edges for all ABox object-property triples
    for subject, predicate, obj in graph:
        if predicate in TBOX_PREDICATES_TO_SKIP:
            continue
        if not (_is_ontology_entity(subject) and _is_ontology_entity(obj)):
            continue

        _ensure_node_exists(str(subject))
        _ensure_node_exists(str(obj))
        network.add_edge(str(subject), str(obj), label=local_name(predicate), arrows="to")

    # Ensure all typed individuals appear even if they have no outgoing edges
    for entity_iri in individual_type_map:
        _ensure_node_exists(entity_iri)

    _add_colour_legend(network)
    return network


def _add_colour_legend(network: Network) -> None:
    """Add a fixed legend of coloured boxes to the top-left of the canvas.

    Each ontology class gets a small box node positioned outside the
    physics simulation, providing a visual key for the colour coding.
    """
    for index, (class_name, colour) in enumerate(CLASS_COLOUR_MAP.items()):
        if class_name == "Other":
            continue
        network.add_node(
            f"_legend_{class_name}", label=class_name, color=colour,
            shape="box", physics=False, x=-1200, y=-400 + index * 40,
            fixed=True, size=20,
        )


def main() -> None:
    """Load ontology, build network, and export as interactive HTML."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    combined_graph = _load_combined_graph()
    individual_type_map = _build_individual_type_map(combined_graph)
    network = _build_network_graph(combined_graph, individual_type_map)

    log.info("Nodes: %d  Edges: %d", len(network.nodes), len(network.edges))
    Path(OUTPUT_HTML_FILE).parent.mkdir(parents=True, exist_ok=True)
    network.write_html(OUTPUT_HTML_FILE, notebook=False, open_browser=False)
    log.info("Saved -> %s", OUTPUT_HTML_FILE)


if __name__ == "__main__":
    main()
