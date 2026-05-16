"""Utility functions for manipulating the rdflib knowledge graph.

This module provides the low-level building blocks used by both populate.py
and enrich.py. Keeping them here avoids duplication and ensures every module
creates triples the same way (same namespace, same sanitisation rules).

Functions
---------
slugify             Convert a DBpedia URI into a safe OWL local name.
label_to_local      Convert an English rdfs:label into a safe OWL local name.
add_individual      Assert an individual with its class membership.
add_relation        Add an object-property triple using local names.
has_type            Check whether an individual belongs to a given class.
local_name          Extract the fragment (after '#') or final path segment of an IRI.
"""

import re
from rdflib import Graph, URIRef, RDF, OWL

from config import ONT


def slugify(dbpedia_uri: str) -> str:
    """Convert a DBpedia resource URI into a safe OWL local name.

    Takes the last path segment of the URI (e.g. 'Mount_Agung' from
    'http://dbpedia.org/resource/Mount_Agung') and replaces any character
    that is not alphanumeric or underscore with '_'.

    Example
    -------
    >>> slugify("http://dbpedia.org/resource/Nusa_Penida")
    'Nusa_Penida'
    >>> slugify("http://dbpedia.org/resource/Komodo_(island)")
    'Komodo__island_'
    """
    last_segment = dbpedia_uri.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "_", last_segment)


def label_to_local(english_label: str) -> str:
    """Convert an English rdfs:label string into a safe OWL local name.

    Strips leading/trailing whitespace, then replaces any non-alphanumeric
    character (except underscore) with '_'.

    Example
    -------
    >>> label_to_local("Badung Regency")
    'Badung_Regency'
    >>> label_to_local("  Pandawa Beach  ")
    'Pandawa_Beach'
    """
    return re.sub(r"[^A-Za-z0-9_]", "_", english_label.strip())


def add_individual(graph: Graph, class_local_name: str, individual_name: str) -> URIRef:
    """Assert that an individual exists and belongs to the given class.

    Adds two triples:
        <individual_name> rdf:type owl:NamedIndividual .
        <individual_name> rdf:type <class_local_name> .

    Parameters
    ----------
    graph : rdflib.Graph
        The target knowledge graph to add triples to.
    class_local_name : str
        The OWL class local name (e.g. 'Beach', 'Province').
    individual_name : str
        The local name for the new individual (e.g. 'Pandawa_Beach').

    Returns
    -------
    URIRef
        The full IRI of the newly created individual.

    Example
    -------
    >>> individual_iri = add_individual(graph, "Beach", "Pandawa_Beach")
    # Adds: ont:Pandawa_Beach rdf:type owl:NamedIndividual, ont:Beach .
    """
    individual_iri = ONT[individual_name]
    graph.add((individual_iri, RDF.type, OWL.NamedIndividual))
    graph.add((individual_iri, RDF.type, ONT[class_local_name]))
    return individual_iri


def add_relation(graph: Graph, subject_local: str, predicate_local: str, object_local: str) -> None:
    """Add an object-property triple using ontology local names.

    All three arguments are local names (fragments) that get expanded
    with the ontology namespace prefix.

    Parameters
    ----------
    graph : rdflib.Graph
        The target knowledge graph.
    subject_local : str
        Local name of the subject individual (e.g. 'Pandawa_Beach').
    predicate_local : str
        Local name of the object property (e.g. 'locatedIn').
    object_local : str
        Local name of the object individual (e.g. 'Bali').

    Example
    -------
    >>> add_relation(graph, "Pandawa_Beach", "locatedIn", "Bali")
    # Adds: ont:Pandawa_Beach ont:locatedIn ont:Bali .
    """
    graph.add((ONT[subject_local], ONT[predicate_local], ONT[object_local]))


def has_type(graph: Graph, individual_local: str, class_local: str) -> bool:
    """Check whether an individual is asserted as a member of a given class.

    Parameters
    ----------
    graph : rdflib.Graph
        The knowledge graph to query.
    individual_local : str
        Local name of the individual to check.
    class_local : str
        Local name of the OWL class to test membership against.

    Returns
    -------
    bool
        True if the triple (individual rdf:type class) exists in the graph.

    Example
    -------
    >>> has_type(graph, "Pandawa_Beach", "Beach")
    True
    """
    return (ONT[individual_local], RDF.type, ONT[class_local]) in graph


def local_name(iri: URIRef | str) -> str:
    """Extract the local part (fragment or final path segment) of an IRI.

    If the IRI contains '#', returns everything after the last '#'.
    Otherwise, returns everything after the last '/'.

    Parameters
    ----------
    iri : URIRef or str
        The full IRI to extract from.

    Returns
    -------
    str
        The local name portion.

    Example
    -------
    >>> local_name("http://www.semanticweb.org/.../ontology-9#Beach")
    'Beach'
    >>> local_name("http://dbpedia.org/resource/Bali")
    'Bali'
    """
    iri_string = str(iri)
    if "#" in iri_string:
        return iri_string.rsplit("#", 1)[-1]
    return iri_string.rsplit("/", 1)[-1]


# Backward-compatible alias (used by enrich.py and graph_embedding.py)
add_rel = add_relation
