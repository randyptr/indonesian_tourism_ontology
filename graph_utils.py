"""Tiny helpers for working with the rdflib graph.

Kept in one module so populate/enrich don't reinvent these.
"""

import re
from rdflib import Graph, URIRef, RDF, OWL

from config import ONT


def slugify(uri: str) -> str:
    """Convert a DBpedia resource URI into a safe OWL local name."""
    local = uri.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "_", local)


def label_to_local(label: str) -> str:
    """Convert an English rdfs:label into a safe OWL local name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", label.strip())


def add_individual(g: Graph, class_local: str, ind_name: str) -> URIRef:
    """Assert ind_name rdf:type class_local (and owl:NamedIndividual). Returns the IRI."""
    ind = ONT[ind_name]
    g.add((ind, RDF.type, OWL.NamedIndividual))
    g.add((ind, RDF.type, ONT[class_local]))
    return ind


def add_rel(g: Graph, s_local: str, p_local: str, o_local: str) -> None:
    """Add an object-property triple using local names."""
    g.add((ONT[s_local], ONT[p_local], ONT[o_local]))


def has_type(g: Graph, ind_local: str, class_local: str) -> bool:
    """True iff ind_local has been asserted as class_local."""
    return (ONT[ind_local], RDF.type, ONT[class_local]) in g


def local_name(uri: URIRef | str) -> str:
    """Return the local part of an IRI (text after '#')."""
    s = str(uri)
    return s.rsplit("#", 1)[-1] if "#" in s else s.rsplit("/", 1)[-1]
