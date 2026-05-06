"""Graph embeddings + link prediction for the tourism ontology (PyKEEN).

Workflow:
    1. Extract object-property triples from data.owl + schema.owl.
    2. Define 3 new individuals (with one or two known facts each) so PyKEEN
       learns embeddings for them.
    3. Train a TransE model on all triples.
    4. Project entity embeddings to 2D with t-SNE and save a coloured plot.
    5. For each new individual, predict the missing tail of a chosen relation
       and append the top prediction back into data.owl as a new triple.

Run:
    python graph_embedding.py
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

from config import DATA_FILE, SCHEMA_FILE, ONT, ONT_IRI
from graph_utils import local_name, add_individual, add_rel

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PLOT_FILE       = "embedding_clusters.png"
MODEL_NAME      = "DistMult"          # DistMult often outperforms TransE on small KGs
EMBEDDING_DIM   = 64
NUM_EPOCHS      = 400
RANDOM_SEED     = 42
TOP_K           = 5

# ── Hand-defined new individuals ──────────────────────────────────────────────
# Each gets one or two anchoring facts (pre-training), then a query whose tail
# we ask the model to predict.
@dataclass(frozen=True)
class TestIndividual:
    name: str
    known_facts: list[tuple[str, str]]      # list of (predicate, tail)
    query_relation: str                      # predicate for which we predict tail
    expected_class: str                      # used to filter predictions
    note: str

NEW_INDIVIDUALS: list[TestIndividual] = [
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. Load triples
# ─────────────────────────────────────────────────────────────────────────────
def load_object_triples() -> tuple[Graph, np.ndarray]:
    """Read data.owl (+ schema.owl for class hierarchy) and return:
       - the merged rdflib graph (used later for type lookup / writing back)
       - an (N, 3) ndarray of (s, p, o) string triples for PyKEEN
    Literals and non-ontology IRIs are dropped.
    """
    g = Graph()
    g.parse(str(DATA_FILE), format="xml")
    g.parse(str(SCHEMA_FILE), format="xml")

    triples = [
        (str(s), str(p), str(o))
        for s, p, o in g
        if isinstance(s, URIRef) and isinstance(o, URIRef)
        and not isinstance(o, Literal)
        and o != OWL.NamedIndividual
    ]
    return g, np.array(triples)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Extend graph with new individuals
# ─────────────────────────────────────────────────────────────────────────────
def add_test_individuals(g: Graph) -> np.ndarray:
    """Add NEW_INDIVIDUALS to the graph in-place AND return the extra triples
    so they can be appended to the PyKEEN triples factory."""
    extra = []
    for ind in NEW_INDIVIDUALS:
        for pred, tail in ind.known_facts:
            if pred == "rdf:type":
                add_individual(g, tail, ind.name)
                extra.append((str(ONT[ind.name]), str(RDF.type), str(ONT[tail])))
            else:
                add_rel(g, ind.name, pred, tail)
                extra.append((str(ONT[ind.name]), str(ONT[pred]), str(ONT[tail])))
    return np.array(extra)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Train embeddings
# ─────────────────────────────────────────────────────────────────────────────
def train_embeddings(triples: np.ndarray):
    """Train TransE on all triples (no held-out test set — we want embeddings
    for every entity, including the 3 new ones)."""
    tf = TriplesFactory.from_labeled_triples(triples)
    result = pipeline(
        training=tf, testing=tf, validation=tf,
        model=MODEL_NAME,
        model_kwargs=dict(embedding_dim=EMBEDDING_DIM),
        training_kwargs=dict(num_epochs=NUM_EPOCHS, use_tqdm_batch=False),
        random_seed=RANDOM_SEED,
    )
    return result, tf


# ─────────────────────────────────────────────────────────────────────────────
# 4. Visualize clusters with t-SNE
# ─────────────────────────────────────────────────────────────────────────────
def _build_type_map(g: Graph) -> dict[str, str]:
    """Map each individual IRI → its primary ontology class local name."""
    out: dict[str, str] = {}
    for s, _, o in g.triples((None, RDF.type, None)):
        if not isinstance(o, URIRef) or o == OWL.NamedIndividual:
            continue
        if str(o).startswith(ONT_IRI):
            out[str(s)] = local_name(o)
    return out


def visualize_embeddings(model, tf: TriplesFactory, g: Graph) -> None:
    """Project entity embeddings to 2D with t-SNE and scatter-plot by class.

    Only ABox individuals (those with an ontology rdf:type) are shown;
    TBox entities (class/property definitions, OWL restrictions) are
    filtered out so the plot isn't dominated by an "Other" cloud.
    """
    emb = model.entity_representations[0](indices=None).detach().cpu().numpy()
    labels = [tf.entity_id_to_label[i] for i in range(emb.shape[0])]
    type_of = _build_type_map(g)

    # Keep only entities that have a known ontology class (ABox individuals)
    keep = [i for i, lbl in enumerate(labels) if lbl in type_of]
    if not keep:
        log.warning("No typed entities found — skipping plot")
        return
    emb_filtered = emb[keep]
    labels_filtered = [labels[i] for i in keep]
    classes = [type_of[lbl] for lbl in labels_filtered]

    perplexity = min(30, max(2, len(keep) - 1))
    proj = TSNE(n_components=2, random_state=RANDOM_SEED,
                perplexity=perplexity, init="pca").fit_transform(emb_filtered)

    plt.figure(figsize=(11, 8))
    cmap = plt.get_cmap("tab20")
    for i, cls in enumerate(sorted(set(classes))):
        idx = [j for j, c in enumerate(classes) if c == cls]
        plt.scatter(proj[idx, 0], proj[idx, 1], s=28,
                    color=cmap(i % cmap.N), label=cls, alpha=0.8)

    # Highlight the new individuals
    for ind in NEW_INDIVIDUALS:
        iri = str(ONT[ind.name])
        if iri in labels_filtered:
            j = labels_filtered.index(iri)
            plt.annotate(ind.name, (proj[j, 0], proj[j, 1]),
                         fontsize=8, fontweight="bold",
                         xytext=(5, 5), textcoords="offset points")

    plt.legend(fontsize=8, loc="best", markerscale=1.2)
    plt.title(f"{MODEL_NAME} entity embeddings (t-SNE projection)")
    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=140)
    plt.close()
    log.info("Saved cluster plot → %s", PLOT_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Link prediction
# ─────────────────────────────────────────────────────────────────────────────
def _filter_by_class(df, expected_class: str, type_of: dict[str, str]):
    """Keep only candidate tails whose rdf:type matches expected_class."""
    return df[df["tail_label"].apply(lambda iri: type_of.get(iri) == expected_class)]


def predict_for_new_individuals(model, tf: TriplesFactory, g: Graph) -> list[tuple[str, str, str]]:
    """For each TestIndividual, run link prediction and pick the top
    type-consistent tail. Returns the new triples to add back to the graph."""
    type_of = _build_type_map(g)
    new_triples: list[tuple[str, str, str]] = []

    for ind in NEW_INDIVIDUALS:
        head_iri = str(ONT[ind.name])
        rel_iri  = str(ONT[ind.query_relation])
        if head_iri not in tf.entity_to_id or rel_iri not in tf.relation_to_id:
            log.warning("Skipping %s — head or relation not in training data", ind.name)
            continue

        pred = predict_target(
            model=model, head=head_iri, relation=rel_iri, triples_factory=tf,
        ).df

        filtered = _filter_by_class(pred, ind.expected_class, type_of)
        log.info("\n%s -- %s -- ?  (%s)", ind.name, ind.query_relation, ind.note)
        log.info("  Top-%d type-consistent (%s):", TOP_K, ind.expected_class)
        for _, row in filtered.head(TOP_K).iterrows():
            log.info("    %.4f  %s", row["score"], local_name(row["tail_label"]))

        if not filtered.empty:
            top_tail = filtered.iloc[0]["tail_label"]
            new_triples.append((head_iri, rel_iri, top_tail))
            log.info("  → autocompleting: %s %s %s",
                     ind.name, ind.query_relation, local_name(top_tail))

    return new_triples


# ─────────────────────────────────────────────────────────────────────────────
# 6. Write predictions back to data.owl
# ─────────────────────────────────────────────────────────────────────────────
def append_predictions_to_data_owl(g: Graph, new_triples: list[tuple[str, str, str]]) -> None:
    """Add the predicted triples to the graph and overwrite data.owl."""
    if not new_triples:
        log.info("No predictions to write back.")
        return
    for s, p, o in new_triples:
        g.add((URIRef(s), URIRef(p), URIRef(o)))
    g.serialize(destination=str(DATA_FILE), format="xml")
    log.info("\nAppended %d predicted triples to %s", len(new_triples), DATA_FILE.name)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    log.info("=" * 60)
    log.info("Step 1: Load object-property triples from data.owl + schema.owl")
    g, base_triples = load_object_triples()
    log.info("  %d triples extracted", len(base_triples))

    log.info("\nStep 2: Add 3 new individuals with anchoring facts")
    extra = add_test_individuals(g)
    all_triples = np.vstack([base_triples, extra])
    log.info("  +%d anchoring triples (total %d)", len(extra), len(all_triples))

    log.info("\nStep 3: Train %s (dim=%d, epochs=%d) …", MODEL_NAME, EMBEDDING_DIM, NUM_EPOCHS)
    result, tf = train_embeddings(all_triples)

    log.info("\nStep 4: Project embeddings with t-SNE")
    visualize_embeddings(result.model, tf, g)

    log.info("\nStep 5: Link prediction for the 3 new individuals")
    new_triples = predict_for_new_individuals(result.model, tf, g)

    log.info("\nStep 6: Autocomplete data.owl with the predictions")
    append_predictions_to_data_owl(g, new_triples)

    log.info("\nDone. Run `python -c 'from reasoning import check_consistency; check_consistency()'`"
             " to verify the autocompleted ontology is still consistent.")


if __name__ == "__main__":
    main()
