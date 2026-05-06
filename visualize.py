"""Render data.owl + schema.owl as an interactive HTML graph (PyVis).

Output: ontology_graph.html. Open it in a browser to explore.

Nodes are coloured by the rdf:type of the individual (Beach, Park, City, ...).
Edges are labeled by the predicate's local name. TBox/meta triples are skipped.
"""

import logging
from rdflib import Graph, URIRef, RDF, RDFS, OWL
from pyvis.network import Network

from config import SCHEMA_FILE, DATA_FILE, ONT_IRI
from graph_utils import local_name

log = logging.getLogger(__name__)

OUTPUT_HTML = "ontology_graph.html"

CLASS_COLORS = {
    "Province":          "#e41a1c",
    "Island":            "#377eb8",
    "City":              "#4daf4a",
    "Beach":             "#ff7f00",
    "Park":              "#984ea3",
    "Volcano":           "#a65628",
    "Museum":            "#f781bf",
    "Temple":            "#999999",
    "Festival":          "#ffff33",
    "Hotel":             "#17becf",
    "ReligiousCeremony": "#bcbd22",
    "Activities":        "#bf9a30",
    "Country":           "#000000",
    "Other":             "#cccccc",
}

# TBox / meta predicates that should not become graph edges
SKIP_PREDICATES = {
    RDF.type, RDFS.label, RDFS.comment, OWL.sameAs,
    RDFS.subClassOf, RDFS.subPropertyOf, RDFS.domain, RDFS.range,
    OWL.equivalentClass, OWL.equivalentProperty,
    OWL.inverseOf, OWL.disjointWith,
}


def _load_combined() -> Graph:
    g = Graph()
    g.parse(str(DATA_FILE), format="xml")
    g.parse(str(SCHEMA_FILE), format="xml")
    return g


def _type_map(g: Graph) -> dict[str, str]:
    """Map each individual's IRI to its primary class local name."""
    out: dict[str, str] = {}
    for s, _, o in g.triples((None, RDF.type, None)):
        if not isinstance(o, URIRef) or o == OWL.NamedIndividual:
            continue
        if str(o).startswith(ONT_IRI):
            out[str(s)] = local_name(o)
    return out


def _is_ontology_iri(node: URIRef) -> bool:
    return isinstance(node, URIRef) and str(node).startswith(ONT_IRI)


def _build_network(g: Graph, type_of: dict[str, str]) -> Network:
    net = Network(height="800px", width="100%", bgcolor="#ffffff",
                  font_color="#222", directed=True, notebook=False)
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120)

    added: set[str] = set()

    def _add_node(uri: str) -> None:
        if uri in added:
            return
        added.add(uri)
        cls = type_of.get(uri, "Other")
        net.add_node(uri, label=local_name(uri), size=18,
                     color=CLASS_COLORS.get(cls, CLASS_COLORS["Other"]),
                     title=f"{local_name(uri)}\n({cls})")

    for s, p, o in g:
        if p in SKIP_PREDICATES:
            continue
        if not (_is_ontology_iri(s) and _is_ontology_iri(o)):
            continue
        _add_node(str(s))
        _add_node(str(o))
        net.add_edge(str(s), str(o), label=local_name(p), arrows="to")

    # Ensure typed individuals appear even if isolated
    for uri in type_of:
        _add_node(uri)

    _add_legend(net)
    return net


def _add_legend(net: Network) -> None:
    for i, (cls, color) in enumerate(CLASS_COLORS.items()):
        if cls == "Other":
            continue
        net.add_node(f"_legend_{cls}", label=cls, color=color, shape="box",
                     physics=False, x=-1200, y=-400 + i * 40, fixed=True, size=20)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    g = _load_combined()
    type_of = _type_map(g)
    net = _build_network(g, type_of)
    log.info("Nodes: %d  Edges: %d", len(net.nodes), len(net.edges))
    net.write_html(OUTPUT_HTML, notebook=False, open_browser=False)
    log.info("Saved → %s", OUTPUT_HTML)


if __name__ == "__main__":
    main()
