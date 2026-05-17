"""Knowledge graph embeddings for the tourism ontology.

Trains a DistMult model on object-property triples from data.owl + schema.owl,
then supports manual link prediction queries and t-SNE visualisation.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
from rdflib import Graph, URIRef, RDF, RDFS, OWL
from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline
from pykeen.models import DistMult

from config import DATA_FILE, SCHEMA_FILE, ONT_IRI, ONTOLOGY_DIR, ONT
from graph_utils import local_name
from enrich import CAPITAL_OF_PROVINCE
from reasoning import _graph_from_ttl, _build_establishments_graph

log = logging.getLogger(__name__)

PLOT_OUTPUT_FILE   = "./graph_vis/embedding_clusters.png"
MODEL_DIR          = Path("embedding_model")
PLOT_CLASSES = {
    "Beach", "Park", "Volcano", "MainDish", "SideDish",
    "ReligiousCeremony", "Festival", "City", "Island", "Province",
    "Ingredient", "Allergens", "Guesthouse", "Hostel", "Hotel",
    "Resort", "Villa", "Restaurant", "StreetVendor", "TraditionalMarket",
}
MODEL_NAME        = "DistMult"
EMBEDDING_DIM     = 128
NUM_EPOCHS        = 400
LEARNING_RATE     = 0.01
RANDOM_SEED       = 42
TOP_K_PREDICTIONS = 5


def _wire_supplementary_hubs(graph: Graph) -> None:
    """Add City → hasFood and City → hasAccommodation hub edges for supplementary ABox files.

    Food individuals (alergy_ingredients_dishes.ttl) carry originatesFrom → Province.
    Establishment individuals (Resort, Villa, Guesthouse, Hostel) carry locatedIn → Province.
    Neither file goes through enrich_all, so their hub edges are wired here, after merging,
    so the embedding model sees the full City–Food and City–Accommodation relations.
    """
    # Food hubs: City → hasFood → Food
    for food_subj, _, province_obj in graph.triples((None, ONT.originatesFrom, None)):
        if not isinstance(province_obj, URIRef):
            continue
        capital = CAPITAL_OF_PROVINCE.get(local_name(province_obj))
        if capital:
            graph.add((ONT[capital], ONT.hasFood, food_subj))

    # Accommodation hubs: City → hasAccommodation → Resort / Villa / Guesthouse / Hostel
    # (Hotel is already handled by add_accommodation_hubs in enrich_all)
    for accom_class in ("Resort", "Villa", "Guesthouse", "Hostel"):
        for subj, _, _ in graph.triples((None, RDF.type, ONT[accom_class])):
            for province, capital in CAPITAL_OF_PROVINCE.items():
                if (subj, ONT.locatedIn, ONT[province]) in graph:
                    graph.add((ONT[capital], ONT.hasAccommodation, subj))


def _add_inverse_triples(triples: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Generate inverse triples for every object-property assertion.

    For each (s, p, o) triple, adds (o, inv_<localName>, s). This doubles
    the relational signal so the embedding model learns bidirectional patterns
    (e.g. City->locatedIn->Province AND Province->inv_locatedIn->City).

    TBox predicates (rdf:type, rdfs:subClassOf, etc.) are excluded — only
    ontology-namespace predicates get an inverse.
    """
    SKIP_INVERSE_PREFIXES = (
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2002/07/owl#",
    )
    inverse_triples = []
    for s, p, o in triples:
        if any(p.startswith(prefix) for prefix in SKIP_INVERSE_PREFIXES):
            continue
        # Build inverse predicate IRI: ont#inv_hasActivity
        if "#" in p:
            namespace, local = p.rsplit("#", 1)
            inv_p = f"{namespace}#inv_{local}"
        else:
            inv_p = f"{p}_inv"
        inverse_triples.append((o, inv_p, s))
    return inverse_triples


def load_object_property_triples() -> tuple[Graph, np.ndarray]:
    """Load data.owl + schema.owl and return (merged_graph, (N,3) triple array).

    Filters to URIRef-only triples, excluding owl:NamedIndividual meta-triples.
    Adds inverse triples to double the relational signal for embedding training.
    """
    merged_graph = Graph()
    merged_graph.parse(str(DATA_FILE), format="xml")
    merged_graph.parse(str(SCHEMA_FILE), format="xml")
    merged_graph += _graph_from_ttl(ONTOLOGY_DIR / "alergy_ingredients_dishes.ttl")
    merged_graph += _build_establishments_graph()
    _wire_supplementary_hubs(merged_graph)

    triple_strings = [
        (str(s), str(p), str(o))
        for s, p, o in merged_graph
        if isinstance(s, URIRef) and isinstance(o, URIRef)
        and o != OWL.NamedIndividual
    ]
    # Add inverse triples for richer bidirectional signal
    # inverse = _add_inverse_triples(triple_strings)
    # triple_strings.extend(inverse)
    # log.info("Triples: %d original + %d inverse = %d total",
    #          len(triple_strings) - len(inverse), len(inverse), len(triple_strings))
    return merged_graph, np.array(triple_strings)


def train_embedding_model(all_triples: np.ndarray, num_epochs: NUM_EPOCHS):
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
        optimizer_kwargs=dict(lr=LEARNING_RATE),
        training_kwargs=dict(num_epochs=num_epochs, use_tqdm_batch=False),
        random_seed=RANDOM_SEED,
    )
    return training_result, triples_factory


def save_embedding_model(training_result, triples_factory: TriplesFactory) -> None:
    """Save model weights and triples factory to MODEL_DIR for later reuse."""
    MODEL_DIR.mkdir(exist_ok=True)
    torch.save(training_result.model.state_dict(), MODEL_DIR / "weights.pt")
    triples_factory.to_path_binary(MODEL_DIR / "triples")
    log.info("Saved embedding model → %s/", MODEL_DIR)


def load_embedding_model() -> tuple:
    """Load a previously saved model from MODEL_DIR.

    Returns (model, triples_factory) ready for predict_target calls.
    Raises FileNotFoundError if MODEL_DIR doesn't exist yet.
    """
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"No saved model at '{MODEL_DIR}/' — run the training cell first."
        )
    triples_factory = TriplesFactory.from_path_binary(MODEL_DIR / "triples")
    model = DistMult(triples_factory=triples_factory, embedding_dim=EMBEDDING_DIM)
    model.load_state_dict(torch.load(MODEL_DIR / "weights.pt", weights_only=True))
    model.eval()
    log.info("Loaded embedding model ← %s/", MODEL_DIR)
    return model, triples_factory


def build_subclass_ancestors(graph: Graph) -> dict[str, set[str]]:
    """Return {class_name: {all ancestor class names}} by walking rdfs:subClassOf chains.

    Reads the TBox from the already-loaded graph, so no extra file I/O needed.
    Example: "Surfing" -> {"WaterSport", "Activities"}, "Hiking" -> {"MountainSport", "Activities"}
    """
    direct_parents: dict[str, set[str]] = {}
    for sub, _, sup in graph.triples((None, RDFS.subClassOf, None)):
        if isinstance(sub, URIRef) and isinstance(sup, URIRef):
            if str(sub).startswith(ONT_IRI) and str(sup).startswith(ONT_IRI):
                sub_name = str(sub)[len(ONT_IRI):]
                sup_name = str(sup)[len(ONT_IRI):]
                direct_parents.setdefault(sub_name, set()).add(sup_name)

    def _ancestors(cls: str, seen: set[str]) -> set[str]:
        if cls in seen:
            return seen
        seen.add(cls)
        for parent in direct_parents.get(cls, set()):
            _ancestors(parent, seen)
        return seen

    return {cls: _ancestors(cls, set()) - {cls} for cls in direct_parents}


def build_entity_type_map(
    graph: Graph,
    classes: set[str] | None = None,
) -> dict[str, str]:
    """Map each individual's IRI to its ontology class local name.

    If classes is given, only includes entities whose direct type is in that set
    (used to filter the t-SNE plot to PLOT_CLASSES). Pass None to include all
    ontology individuals (used for link-prediction filtering).

    An individual may carry multiple rdf:type triples (e.g. ONT.Province from
    our enricher AND dbo:Province from DBpedia populate). Only ONT-namespaced
    types are considered; among those, the last one encountered wins. Province
    entities are guaranteed to have ONT.Province via add_country_backbone, so
    they are found correctly without any special handling here.
    """
    type_map: dict[str, str] = {}
    for subject, _, object_type in graph.triples((None, RDF.type, None)):
        if not isinstance(object_type, URIRef) or object_type == OWL.NamedIndividual:
            continue
        if str(object_type).startswith(ONT_IRI):
            class_name = str(object_type)[len(ONT_IRI):]
            if classes is None or class_name in classes:
                type_map[str(subject)] = class_name
    return type_map


def visualize_embeddings(trained_model, triples_factory: TriplesFactory, graph: Graph) -> None:
    """Project entity embeddings to 2D with t-SNE and save a scatter plot.

    Only ABox individuals with a known ontology rdf:type are plotted —
    TBox entities (class nodes, property nodes, OWL restrictions) are excluded.
    """
    all_embeddings = (
        trained_model.entity_representations[0](indices=None)
        .detach().cpu().numpy()
    )

    entity_labels = [
        triples_factory.entity_id_to_label[i]
        for i in range(all_embeddings.shape[0])
    ]
    entity_type_map = build_entity_type_map(graph, classes=PLOT_CLASSES)

    abox_indices = [i for i, label in enumerate(entity_labels) if label in entity_type_map]
    if not abox_indices:
        log.warning("No typed entities found — skipping plot")
        return

    filtered_embeddings = all_embeddings[abox_indices]
    filtered_labels     = [entity_labels[i] for i in abox_indices]
    entity_classes      = [entity_type_map[label] for label in filtered_labels]

    projected_2d = TSNE(
        n_components=2, random_state=RANDOM_SEED,
        perplexity=min(30, len(abox_indices) - 1),
    ).fit_transform(filtered_embeddings)

    # Classes with very few individuals get a larger marker so they're visible.
    # _LARGE_MARKER_CLASSES = {"Province", "Island", "Country"}

    plt.figure(figsize=(14, 8))
    colour_palette = plt.get_cmap("tab20")
    for idx, class_name in enumerate(sorted(set(entity_classes))):
        pts = [j for j, c in enumerate(entity_classes) if c == class_name]
        marker_size = 90 # bullet size
        plt.scatter(
            projected_2d[pts, 0], projected_2d[pts, 1],
            s=marker_size, color=colour_palette(idx % colour_palette.N),
            label=class_name, alpha=0.9,
            edgecolors="black",
            linewidths=0.6,
        )

    plt.legend(fontsize=8, loc="upper left", markerscale=1.2, bbox_to_anchor=(1.01, 1))
    plt.title(f"{MODEL_NAME} entity embeddings (t-SNE projection)")
    plt.tight_layout()
    Path(PLOT_OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(PLOT_OUTPUT_FILE, dpi=140, bbox_inches="tight")
    plt.close()
    log.info("Saved cluster plot -> %s", PLOT_OUTPUT_FILE)


def filter_predictions_by_class(
    predictions_dataframe,
    expected_class: str,
    entity_type_map: dict[str, str],
    ancestors_map: dict[str, set[str]] | None = None,
):
    """Keep only candidate tails whose type matches or is a subclass of expected_class.

    With ancestors_map, a query for "Activities" will also match candidates typed
    as "Surfing", "Diving", "Hiking", etc., since those are subclasses of Activities.
    """
    def _matches(iri: str) -> bool:
        cls = entity_type_map.get(iri)
        if cls is None:
            return False
        if cls == expected_class:
            return True
        return ancestors_map is not None and expected_class in ancestors_map.get(cls, set())

    return predictions_dataframe[predictions_dataframe["tail_label"].apply(_matches)]
