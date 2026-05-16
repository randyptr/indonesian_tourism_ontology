"""Low-level helpers for building the rdflib knowledge graph."""

import re
import logging
from rdflib import Graph, URIRef, RDF, OWL

from config import ONT


def slugify(dbpedia_uri: str) -> str:
    """Last path segment of a DBpedia URI with non-alphanumeric chars replaced by '_'."""
    last_segment = dbpedia_uri.rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_]", "_", last_segment)


def label_to_local(english_label: str) -> str:
    """Strip and sanitise an English rdfs:label into a safe OWL local name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", english_label.strip())


def add_individual(graph: Graph, class_local_name: str, individual_name: str) -> URIRef:
    """Assert <individual_name> rdf:type owl:NamedIndividual and rdf:type <class>."""
    individual_iri = ONT[individual_name]
    graph.add((individual_iri, RDF.type, OWL.NamedIndividual))
    graph.add((individual_iri, RDF.type, ONT[class_local_name]))
    return individual_iri


def add_relation(graph: Graph, subject_local: str, predicate_local: str, object_local: str) -> None:
    """Add one object-property triple using ontology local names."""
    graph.add((ONT[subject_local], ONT[predicate_local], ONT[object_local]))


def has_type(graph: Graph, individual_local: str, class_local: str) -> bool:
    """True if (individual rdf:type class) exists in the graph."""
    return (ONT[individual_local], RDF.type, ONT[class_local]) in graph


def local_name(iri: URIRef | str) -> str:
    """Fragment after '#', or final path segment after '/' if no '#'."""
    iri_string = str(iri)
    if "#" in iri_string:
        return iri_string.rsplit("#", 1)[-1]
    return iri_string.rsplit("/", 1)[-1]


class NeatFormatter(logging.Formatter):
    """Logging formatter for notebook display.

    Transforms plain log messages into visually structured output:
      [Province]   →  blank line + ▸ Province   (section header)
      + Name       →  · Name                     (item added)
      - Name       →  ✗ Name                     (item skipped)
      -> summary   →  ↳ summary                  (count / result line)
      x -> y       →  x → y                      (inline arrow)
    """

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if re.match(r"^\[.+\]$", msg.strip()):
            return "\n▸ " + msg.strip()[1:-1]
        msg = re.sub(r"^(\s+)\+\s", lambda m: m.group(1) + "· ", msg)
        msg = re.sub(r"^(\s+)-\s", lambda m: m.group(1) + "✗ ", msg)
        msg = re.sub(r"^(\s+)->\s", lambda m: m.group(1) + "↳ ", msg)
        msg = msg.replace(" -> ", " → ")
        return msg
