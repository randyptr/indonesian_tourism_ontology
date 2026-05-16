"""Knowledge graph embeddings and link prediction for the tourism ontology.

Uses PyKEEN to train a DistMult embedding model on the ontology's object-property
triples, then demonstrates link prediction by:
    1. Defining 3 new "test" individuals with partial knowledge.
    2. Training embeddings that include these individuals.
    3. Predicting the missing tail for a chosen relation (e.g. locatedIn).
    4. Visualising all entity embeddings as a 2D t-SNE scatter plot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from rdflib import Graph, URIRef, RDF, OWL, Literal
from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline
from pykeen.predict import predict_target

from config import DATA_FILE, SCHEMA_FILE, ONT, ONT_IRI, ONTOLOGY_DIR
from graph_utils import local_name, add_individual, add_relation
from reasoning import _graph_from_ttl, _build_establishments_graph

log = logging.getLogger(__name__)

# ── Training Configuration ───────────────────────────────────────────────────
PLOT_OUTPUT_FILE = "embedding_clusters.png"   # t-SNE scatter plot output

# Only these classes are included in the t-SNE plot
PLOT_CLASSES = {
    "Beach", "Park", "Volcano", "MainDish", "SideDish",
    "ReligiousCeremony", "Festival", "City", "Island", "Province",
    "Ingredient", "Allergens", "Guesthouse", "Hostel", "Hotel",
    "Resort", "Villa", "Restaurant", "StreetVendor", "TraditionalMarket",
}
MODEL_NAME       = "DistMult"                 # embedding model architecture
EMBEDDING_DIM    = 64                         # dimensionality of entity/relation vectors
NUM_EPOCHS       = 400                        # training iterations over the full graph
RANDOM_SEED      = 42                         # reproducibility seed for training + t-SNE
TOP_K_PREDICTIONS = 5                         # how many top candidates to display

# ── Test Individuals for Link Prediction ─────────────────────────────────────
# Each gets one or two "anchoring" facts (pre-training), then a query whose
# tail we ask the trained model to predict.


@dataclass(frozen=True)
class TestIndividual:
    """A synthetic individual used to evaluate link prediction quality.

    Attributes
    ----------
    name : str
        OWL local name for the individual.
    known_facts : list[tuple[str, str]]
        Facts asserted before training. Each is (predicate, tail_local_name).
        Use "rdf:type" as predicate for class membership.
    query_relation : str
        The predicate for which we want the model to predict the tail.
    expected_class : str
        Only candidates of this class are considered valid predictions.
    note : str
        Human-readable explanation of what we expect the model to predict.
    """
    name: str
    known_facts: list[tuple[str, str]]
    query_relation: str
    expected_class: str
    note: str


TEST_INDIVIDUALS: list[TestIndividual] = [
    TestIndividual(
        name="Tanah_Lot_Beach",
        known_facts=[("rdf:type", "Beach")],
        query_relation="locatedIn",
        expected_class="Province",
        note="A Beach with no province assigned — expect Bali (5/8 beaches in Bali).",
    ),
    TestIndividual(
        name="Mount_Inerie",
        known_facts=[("rdf:type", "Volcano"), ("locatedIn", "East_Nusa_Tenggara")],
        query_relation="locatedIn",
        expected_class="Island",
        note="A Volcano in NTT — expect an Island in NTT (Flores).",
    ),
    TestIndividual(
        name="Sasak_Heritage_Festival",
        known_facts=[("rdf:type", "Festival"), ("locatedIn", "West_Nusa_Tenggara")],
        query_relation="hasActivity",
        expected_class="Activities",
        note="A Festival in NTB — expect a Cultural / Sightseeing activity.",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Step 1: Load Triples
# ═══════════════════════════════════════════════════════════════════════════════

def load_object_property_triples() -> tuple[Graph, np.ndarray]:
    """Extract all object-property triples from data.owl and schema.owl.

    Reads both ontology files and filters to keep only triples where:
    - Both subject and object are URIRefs (no literals).
    - The object is not owl:NamedIndividual (meta-level noise).

    Returns
    -------
    tuple[rdflib.Graph, np.ndarray]
        - The merged rdflib graph (used later for type lookup and writing back).
        - An (N, 3) array of string triples suitable for PyKEEN.
    """
    merged_graph = Graph()
    merged_graph.parse(str(DATA_FILE), format="xml")
    merged_graph.parse(str(SCHEMA_FILE), format="xml")
    # Parse imported ontology files (rdflib does not follow owl:imports)
    merged_graph += _graph_from_ttl(ONTOLOGY_DIR / "alergy_ingredients_dishes.ttl")
    merged_graph += _build_establishments_graph()

    triple_strings = [
        (str(subject), str(predicate), str(obj))
        for subject, predicate, obj in merged_graph
        if isinstance(subject, URIRef) and isinstance(obj, URIRef)
        and not isinstance(obj, Literal)
        and obj != OWL.NamedIndividual
    ]
    return merged_graph, np.array(triple_strings)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 2: Add Test Individuals
# ═══════════════════════════════════════════════════════════════════════════════

def add_test_individuals_to_graph(graph: Graph) -> np.ndarray:
    """Insert TEST_INDIVIDUALS into the graph and return their triples.

    Each test individual gets its known_facts asserted in the graph so that
    PyKEEN can learn an embedding for it during training. The returned
    triples are appended to the training set.

    Parameters
    ----------
    graph : rdflib.Graph
        The knowledge graph to modify in-place.

    Returns
    -------
    np.ndarray
        An (M, 3) array of the extra triples added (for concatenation
        with the base training triples).
    """
    extra_triples = []

    for test_individual in TEST_INDIVIDUALS:
        for predicate, tail_name in test_individual.known_facts:
            if predicate == "rdf:type":
                add_individual(graph, tail_name, test_individual.name)
                extra_triples.append((
                    str(ONT[test_individual.name]),
                    str(RDF.type),
                    str(ONT[tail_name]),
                ))
            else:
                add_relation(graph, test_individual.name, predicate, tail_name)
                extra_triples.append((
                    str(ONT[test_individual.name]),
                    str(ONT[predicate]),
                    str(ONT[tail_name]),
                ))

    return np.array(extra_triples)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: Train Embeddings
# ═══════════════════════════════════════════════════════════════════════════════

def train_embedding_model(all_triples: np.ndarray):
    """Train a DistMult model on the full set of triples.

    Uses the entire graph for training (no held-out test set) because our
    goal is to learn high-quality embeddings for ALL entities including
    the 3 test individuals — not to evaluate ranking metrics.

    Parameters
    ----------
    all_triples : np.ndarray
        An (N, 3) array of (subject, predicate, object) string triples.

    Returns
    -------
    tuple[PipelineResult, TriplesFactory]
        The trained pipeline result (contains model) and the triples factory
        (contains entity/relation ID mappings).
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


# ═══════════════════════════════════════════════════════════════════════════════
# Step 4: Visualize with t-SNE
# ═══════════════════════════════════════════════════════════════════════════════

def build_entity_type_map(graph: Graph) -> dict[str, str]:
    """Map each individual's full IRI to its ontology class local name.

    Used by the visualization to colour entities by their class membership.
    Only entities in our ontology namespace are included.
    """
    type_map: dict[str, str] = {}
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if not isinstance(object_type, URIRef) or object_type == OWL.NamedIndividual:
            continue
        if str(object_type).startswith(ONT_IRI):
            class_name = local_name(object_type)
            if class_name in PLOT_CLASSES:
                type_map[str(subject)] = class_name
    return type_map


def visualize_embeddings(trained_model, triples_factory: TriplesFactory, graph: Graph) -> None:
    """Project entity embeddings to 2D with t-SNE and save a scatter plot.

    Only ABox individuals (those with a known ontology rdf:type) are plotted.
    TBox entities (class definitions, property definitions, OWL restrictions)
    are filtered out to avoid an overwhelming "Other" cloud that obscures
    the meaningful clusters.

    Parameters
    ----------
    trained_model : pykeen.models.Model
        The trained embedding model (provides entity vectors).
    triples_factory : TriplesFactory
        Maps entity IDs to their IRI labels.
    graph : rdflib.Graph
        Used to determine each entity's class for colouring.
    """
    # Extract raw embedding vectors for all entities
    all_embeddings = trained_model.entity_representations[0](
        indices=None
    ).detach().cpu().numpy()

    entity_labels = [
        triples_factory.entity_id_to_label[entity_id]
        for entity_id in range(all_embeddings.shape[0])
    ]
    entity_type_map = build_entity_type_map(graph)

    # Filter to only ABox individuals (those with a known class)
    abox_indices = [
        index for index, label in enumerate(entity_labels)
        if label in entity_type_map
    ]
    if not abox_indices:
        log.warning("No typed entities found — skipping plot")
        return

    filtered_embeddings = all_embeddings[abox_indices]
    filtered_labels = [entity_labels[i] for i in abox_indices]
    entity_classes = [entity_type_map[label] for label in filtered_labels]

    # Run t-SNE dimensionality reduction
    perplexity_value = min(30, max(2, len(abox_indices) - 1))
    projected_2d = TSNE(
        n_components=2, random_state=RANDOM_SEED,
        perplexity=perplexity_value, init="pca",
    ).fit_transform(filtered_embeddings)

    # Create scatter plot coloured by class
    plt.figure(figsize=(14, 8))
    colour_palette = plt.get_cmap("tab20")

    unique_classes = sorted(set(entity_classes))
    for class_index, class_name in enumerate(unique_classes):
        point_indices = [j for j, c in enumerate(entity_classes) if c == class_name]
        plt.scatter(
            projected_2d[point_indices, 0],
            projected_2d[point_indices, 1],
            s=28, color=colour_palette(class_index % colour_palette.N),
            label=class_name, alpha=0.8,
        )

    # Annotate the test individuals for easy identification
    for test_individual in TEST_INDIVIDUALS:
        individual_iri = str(ONT[test_individual.name])
        if individual_iri in filtered_labels:
            point_index = filtered_labels.index(individual_iri)
            plt.annotate(
                test_individual.name,
                (projected_2d[point_index, 0], projected_2d[point_index, 1]),
                fontsize=8, fontweight="bold",
                xytext=(5, 5), textcoords="offset points",
            )

    plt.legend(fontsize=8, loc="upper left", markerscale=1.2, bbox_to_anchor=(1.01, 1))
    plt.title(f"{MODEL_NAME} entity embeddings (t-SNE projection)")
    plt.tight_layout()
    plt.savefig(PLOT_OUTPUT_FILE, dpi=140, bbox_inches="tight")
    plt.close()
    log.info("Saved cluster plot -> %s", PLOT_OUTPUT_FILE)


# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: Link Prediction
# ═══════════════════════════════════════════════════════════════════════════════

def filter_predictions_by_class(
    predictions_dataframe,
    expected_class: str,
    entity_type_map: dict[str, str],
):
    """Keep only candidate tails whose rdf:type matches the expected class.

    This ensures predictions are semantically valid (e.g. locatedIn should
    only predict Province or Island, not Beach or Activity).
    """
    return predictions_dataframe[
        predictions_dataframe["tail_label"].apply(
            lambda iri: entity_type_map.get(iri) == expected_class
        )
    ]


def predict_missing_links(
    trained_model,
    triples_factory: TriplesFactory,
    graph: Graph,
) -> list[tuple[str, str, str]]:
    """Run link prediction for each test individual and return new triples.

    For each TestIndividual, predicts the most likely tail entity for its
    query_relation, filtering candidates to only those matching expected_class.

    Parameters
    ----------
    trained_model : pykeen.models.Model
        The trained embedding model.
    triples_factory : TriplesFactory
        Entity/relation ID mappings from training.
    graph : rdflib.Graph
        Used to look up entity types for filtering predictions.

    Returns
    -------
    list[tuple[str, str, str]]
        New (subject_iri, predicate_iri, object_iri) triples to add to the graph.
    """
    entity_type_map = build_entity_type_map(graph)
    predicted_triples: list[tuple[str, str, str]] = []

    for test_individual in TEST_INDIVIDUALS:
        head_iri = str(ONT[test_individual.name])
        relation_iri = str(ONT[test_individual.query_relation])

        # Skip if the entity or relation wasn't seen during training
        if head_iri not in triples_factory.entity_to_id:
            log.warning("Skipping %s — entity not in training data", test_individual.name)
            continue
        if relation_iri not in triples_factory.relation_to_id:
            log.warning("Skipping %s — relation not in training data", test_individual.name)
            continue

        # Get raw predictions from the model
        raw_predictions = predict_target(
            model=trained_model, head=head_iri,
            relation=relation_iri, triples_factory=triples_factory,
        ).df

        # Filter to type-consistent candidates only
        valid_predictions = filter_predictions_by_class(
            raw_predictions, test_individual.expected_class, entity_type_map,
        )

        log.info(
            "\n%s -- %s -- ?  (%s)",
            test_individual.name, test_individual.query_relation, test_individual.note,
        )
        log.info("  Top-%d type-consistent (%s):", TOP_K_PREDICTIONS, test_individual.expected_class)

        for _, row in valid_predictions.head(TOP_K_PREDICTIONS).iterrows():
            log.info("    %.4f  %s", row["score"], local_name(row["tail_label"]))

        # Take the highest-scoring valid prediction
        if not valid_predictions.empty:
            best_tail_iri = valid_predictions.iloc[0]["tail_label"]
            predicted_triples.append((head_iri, relation_iri, best_tail_iri))
            log.info(
                "  -> autocompleting: %s %s %s",
                test_individual.name, test_individual.query_relation,
                local_name(best_tail_iri),
            )

    return predicted_triples


# ═══════════════════════════════════════════════════════════════════════════════
# Step 6: Write Predictions Back to Ontology
# ═══════════════════════════════════════════════════════════════════════════════

def write_predictions_to_data_owl(
    graph: Graph,
    predicted_triples: list[tuple[str, str, str]],
) -> None:
    """Append predicted triples to the graph and save to data.owl.

    Parameters
    ----------
    graph : rdflib.Graph
        The knowledge graph to modify.
    predicted_triples : list[tuple[str, str, str]]
        New triples from link prediction (subject_iri, predicate_iri, object_iri).
    """
    if not predicted_triples:
        log.info("No predictions to write back.")
        return

    for subject_iri, predicate_iri, object_iri in predicted_triples:
        graph.add((URIRef(subject_iri), URIRef(predicate_iri), URIRef(object_iri)))

    graph.serialize(destination=str(DATA_FILE), format="xml")
    log.info("\nAppended %d predicted triples to %s", len(predicted_triples), DATA_FILE.name)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Execute the full embedding + link prediction pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    log.info("=" * 60)
    log.info("Step 1: Load object-property triples from data.owl + schema.owl")
    graph, base_triples = load_object_property_triples()
    log.info("  %d triples extracted", len(base_triples))

    log.info("\nStep 2: Add %d new individuals with anchoring facts", len(TEST_INDIVIDUALS))
    extra_triples = add_test_individuals_to_graph(graph)
    all_triples = np.vstack([base_triples, extra_triples])
    log.info("  +%d anchoring triples (total %d)", len(extra_triples), len(all_triples))

    log.info("\nStep 3: Train %s (dim=%d, epochs=%d) …", MODEL_NAME, EMBEDDING_DIM, NUM_EPOCHS)
    training_result, triples_factory = train_embedding_model(all_triples)

    log.info("\nStep 4: Project embeddings with t-SNE")
    visualize_embeddings(training_result.model, triples_factory, graph)

    log.info("\nStep 5: Link prediction for the %d new individuals", len(TEST_INDIVIDUALS))
    predicted_triples = predict_missing_links(training_result.model, triples_factory, graph)

    log.info("\nStep 6: Autocomplete data.owl with the predictions")
    write_predictions_to_data_owl(graph, predicted_triples)

    log.info(
        "\nDone. Run `python -c 'from reasoning import check_consistency; check_consistency()'`"
        " to verify the autocompleted ontology is still consistent."
    )


if __name__ == "__main__":
    main()
