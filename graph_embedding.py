"""Knowledge graph embeddings for the tourism ontology.

Trains a DistMult model on object-property triples from data.owl + schema.owl,
then supports manual link prediction queries and t-SNE visualisation.
"""

from __future__ import annotations

import logging

import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from rdflib import Graph, URIRef, RDF, OWL
from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline

from config import DATA_FILE, SCHEMA_FILE, ONT_IRI, ONTOLOGY_DIR
from reasoning import _graph_from_ttl, _build_establishments_graph

log = logging.getLogger(__name__)

PLOT_OUTPUT_FILE  = "./graph_vis/embedding_clusters.png"
PLOT_CLASSES = {
    "Beach", "Park", "Volcano", "MainDish", "SideDish",
    "ReligiousCeremony", "Festival", "City", "Island", "Province",
    "Ingredient", "Allergens", "Guesthouse", "Hostel", "Hotel",
    "Resort", "Villa", "Restaurant", "StreetVendor", "TraditionalMarket",
}
MODEL_NAME        = "DistMult"
EMBEDDING_DIM     = 64
NUM_EPOCHS        = 400
RANDOM_SEED       = 42
TOP_K_PREDICTIONS = 5


def load_object_property_triples() -> tuple[Graph, np.ndarray]:
    """Load data.owl + schema.owl and return (merged_graph, (N,3) triple array).

    Filters to URIRef-only triples, excluding owl:NamedIndividual meta-triples.
    """
    merged_graph = Graph()
    merged_graph.parse(str(DATA_FILE), format="xml")
    merged_graph.parse(str(SCHEMA_FILE), format="xml")
    merged_graph += _graph_from_ttl(ONTOLOGY_DIR / "alergy_ingredients_dishes.ttl")
    merged_graph += _build_establishments_graph()

    triple_strings = [
        (str(s), str(p), str(o))
        for s, p, o in merged_graph
        if isinstance(s, URIRef) and isinstance(o, URIRef)
        and o != OWL.NamedIndividual
    ]
    return merged_graph, np.array(triple_strings)


def train_embedding_model(all_triples: np.ndarray):
    """Train DistMult on the given triples and return (PipelineResult, TriplesFactory).

    Uses the full triple set for training, validation, and testing — the goal
    is embeddings for all entities, not held-out ranking metrics.
    """
    triples_factory = TriplesFactory.from_labeled_triples(all_triples)
    training_result = pipeline(
        training=triples_factory,
        testing=triples_factory,
        validation=triples_factory,
        model=MODEL_NAME,
        model_kwargs=dict(embedding_dim=EMBEDDING_DIM),
        training_kwargs=dict(num_epochs=NUM_EPOCHS, use_tqdm_batch=False),
        random_seed=RANDOM_SEED,
    )
    return training_result, triples_factory


def build_entity_type_map(graph: Graph) -> dict[str, str]:
    """Map each individual's IRI to its ontology class local name.

    Only includes entities in our namespace whose class is in PLOT_CLASSES.
    Used for filtering predictions and colouring the t-SNE plot.
    """
    type_map: dict[str, str] = {}
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if not isinstance(object_type, URIRef) or object_type == OWL.NamedIndividual:
            continue
        if str(object_type).startswith(ONT_IRI):
            class_name = str(object_type)[len(ONT_IRI):]
            if class_name in PLOT_CLASSES:
                type_map[str(subject)] = class_name
    return type_map


def visualize_embeddings(trained_model, triples_factory: TriplesFactory, graph: Graph) -> None:
    """Project entity embeddings to 2D with t-SNE and save a scatter plot.

    Only ABox individuals with a known ontology rdf:type are plotted —
    TBox entities (class nodes, property nodes, OWL restrictions) are excluded.
    """
    all_embeddings = trained_model.entity_representations[0](
        indices=None
    ).detach().cpu().numpy()

    entity_labels = [
        triples_factory.entity_id_to_label[i]
        for i in range(all_embeddings.shape[0])
    ]
    entity_type_map = build_entity_type_map(graph)

    abox_indices = [i for i, label in enumerate(entity_labels) if label in entity_type_map]
    if not abox_indices:
        log.warning("No typed entities found — skipping plot")
        return

    filtered_embeddings = all_embeddings[abox_indices]
    filtered_labels     = [entity_labels[i] for i in abox_indices]
    entity_classes      = [entity_type_map[label] for label in filtered_labels]

    perplexity_value = min(30, max(2, len(abox_indices) - 1))
    projected_2d = TSNE(
        n_components=2, random_state=RANDOM_SEED,
        perplexity=perplexity_value, init="pca",
    ).fit_transform(filtered_embeddings)

    plt.figure(figsize=(14, 8))
    colour_palette = plt.get_cmap("tab20")
    for idx, class_name in enumerate(sorted(set(entity_classes))):
        pts = [j for j, c in enumerate(entity_classes) if c == class_name]
        plt.scatter(
            projected_2d[pts, 0], projected_2d[pts, 1],
            s=28, color=colour_palette(idx % colour_palette.N),
            label=class_name, alpha=0.8,
        )

    plt.legend(fontsize=8, loc="upper left", markerscale=1.2, bbox_to_anchor=(1.01, 1))
    plt.title(f"{MODEL_NAME} entity embeddings (t-SNE projection)")
    plt.tight_layout()
    plt.savefig(PLOT_OUTPUT_FILE, dpi=140, bbox_inches="tight")
    plt.close()
    log.info("Saved cluster plot -> %s", PLOT_OUTPUT_FILE)


def filter_predictions_by_class(
    predictions_dataframe,
    expected_class: str,
    entity_type_map: dict[str, str],
):
    """Keep only candidate tails whose rdf:type matches expected_class."""
    return predictions_dataframe[
        predictions_dataframe["tail_label"].apply(
            lambda iri: entity_type_map.get(iri) == expected_class
        )
    ]
