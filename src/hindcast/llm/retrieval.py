"""Text retrieval over publication titles, inside the slice.

Contract. In: a slice connection and the candidate gene symbols. Out: for each
gene, the IDs of the publications whose titles rank highest under two rankers
fused by reciprocal rank, written as a `RetrievalRecord`.

The two rankers read only the slice:

*   Lexical: BM25 over `title_fts`, the FTS5 index the slice builds from its
    own publication rows. The query is the gene symbol.
*   Dense: exact cosine search over `title_embedding`, the vectors the slice
    copied for publications it contains. The query is a fixed sentence naming
    the gene and the phenotype.

Retrieval is computed by `hindcast retrieve` and the record is committed.
A run replays the record: it reads each listed ID back through the slice
connection, so the embedding model is needed to write a record and never to
replay one, and a clone builds the same prompt without it.

What this module must never do:

*   Read a title, a date or a vector from anywhere but the slice connection.
    The embedding cache in `data/work/` covers every publication, so only
    `Store.open_slice` touches it, and it copies pre-cutoff rows only.
*   Trust a record. An ID the slice does not hold raises `SliceLeakError`.
*   Fall back to one ranker. With no vectors in the slice, retrieval fails.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from hindcast.llm.client import CACHE_DIR
from hindcast.pipeline import DEFAULT_DB
from hindcast.store import SliceLeakError, SliceStore, Store

# numpy is imported inside the functions that search. Replaying a record needs
# none of them, so the offline path runs without the `llm` extra.
if TYPE_CHECKING:
    import numpy as np

#: Committed retrieval records, one per cutoff.
RETRIEVAL_DIR = CACHE_DIR / "retrieval"

#: The embedding cache: one vector per publication title, computed once.
EMBEDDINGS_DB = DEFAULT_DB.parent / "title_embeddings.db"

#: Embedding model, run locally through fastembed. See METHODOLOGY.md.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

#: Vector length of `EMBEDDING_MODEL`. A cached vector of another length is an error.
EMBEDDING_DIMENSIONS = 384

#: Reciprocal rank fusion constant: a row scores 1 / (RRF_K + rank) per ranker.
RRF_K = 60

#: How many rows each ranker contributes per gene before fusion.
RANKER_DEPTH = 50

#: How many fused rows per gene reach the prompt.
ROWS_PER_GENE = 5

#: The dense query. The lexical query is the symbol alone.
DENSE_QUERY = "{symbol} regulation of fetal hemoglobin in erythroid cells"

#: Titles embedded per batch when the cache is built.
EMBED_BATCH_SIZE = 256

#: Embeds a list of texts, one vector each, in order.
Embedder = Callable[[Sequence[str]], Iterable["np.ndarray"]]


class GeneRetrieval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str
    node_ids: list[str]


class RetrievalRecord(BaseModel):
    """Ranked publication IDs per candidate gene, with the parameters that produced them."""

    model_config = ConfigDict(extra="forbid")

    cutoff: str
    embedding_model: str
    rrf_k: int
    ranker_depth: int
    rows_per_gene: int
    dense_query: str
    genes: list[GeneRetrieval]


class EvidenceRow(BaseModel):
    """One retrieved publication as the model sees it."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    publication_date: str
    title: str


class EmbeddingBuildReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    titles_total: int
    titles_embedded: int
    seconds: float
    size_bytes: int


def fastembed_embedder(*, query: bool) -> Embedder:
    """The local embedding model. Needs the `llm` extra; the first use downloads the model."""
    # Imported here so replaying a record does not need fastembed installed.
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    if query:
        return lambda texts: (v for text in texts for v in model.query_embed(text))
    return lambda texts: model.embed(list(texts), batch_size=EMBED_BATCH_SIZE)


def _as_blob(vector: np.ndarray) -> bytes:
    import numpy as np

    if vector.shape != (EMBEDDING_DIMENSIONS,):
        raise ValueError(
            f"expected a vector of length {EMBEDDING_DIMENSIONS}, got shape {vector.shape}"
        )
    unit = vector / np.linalg.norm(vector)
    return unit.astype("<f4").tobytes()


def build_title_embeddings(
    store: Store, path: Path | None = None, *, embed: Embedder | None = None
) -> EmbeddingBuildReport:
    """Embed every publication title not yet in the cache.

    The cache is keyed on node ID and title, so a rebuilt graph re-embeds only
    titles that are new or changed. It covers post-cutoff publications too,
    which is why nothing but `Store.open_slice` reads it.
    """
    import numpy as np

    path = path or EMBEDDINGS_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    con = sqlite3.connect(path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS title_embedding ("
            "node_id TEXT PRIMARY KEY, title TEXT NOT NULL, vector BLOB NOT NULL)"
        )
        cached = dict(con.execute("SELECT node_id, title FROM title_embedding"))
        titles = [
            (str(r[0]), str(r[1]))
            for r in store.sql("SELECT id, label FROM node WHERE type = 'Publication' ORDER BY id")
        ]
        missing = [(i, t) for i, t in titles if cached.get(i) != t]
        if missing:
            embed = embed or fastembed_embedder(query=False)
            for start in range(0, len(missing), EMBED_BATCH_SIZE):
                batch = missing[start : start + EMBED_BATCH_SIZE]
                vectors = list(embed([t for _, t in batch]))
                if len(vectors) != len(batch):
                    raise ValueError("the embedder returned a different number of vectors")
                with con:
                    con.executemany(
                        "INSERT OR REPLACE INTO title_embedding (node_id, title, vector) "
                        "VALUES (?, ?, ?)",
                        [
                            (i, t, _as_blob(np.asarray(v)))
                            for (i, t), v in zip(batch, vectors, strict=True)
                        ],
                    )
    finally:
        con.close()
    return EmbeddingBuildReport(
        embedding_model=EMBEDDING_MODEL,
        titles_total=len(titles),
        titles_embedded=len(missing),
        seconds=round(time.monotonic() - started, 1),
        size_bytes=path.stat().st_size,
    )


def lexical_ranking(slice_store: SliceStore, symbol: str) -> list[str]:
    """Publication IDs whose title contains the symbol, best BM25 first."""
    # Quoted so the symbol is a phrase and FTS5 query syntax in it is inert.
    phrase = '"' + symbol.replace('"', '""') + '"'
    rows = slice_store.sql(
        "SELECT node_id FROM title_fts WHERE title_fts MATCH ? "
        "ORDER BY bm25(title_fts), node_id LIMIT ?",
        (phrase, RANKER_DEPTH),
    )
    return [str(r[0]) for r in rows]


def load_slice_vectors(slice_store: SliceStore) -> tuple[list[str], np.ndarray]:
    """Every title vector the slice holds, as IDs and a matrix with one row each."""
    import numpy as np

    rows = slice_store.sql("SELECT node_id, vector FROM title_embedding ORDER BY node_id")
    ids = [str(r[0]) for r in rows]
    matrix = np.frombuffer(b"".join(bytes(r[1]) for r in rows), dtype="<f4")
    return ids, matrix.reshape(len(ids), EMBEDDING_DIMENSIONS)


def dense_ranking(ids: list[str], matrix: np.ndarray, query_vector: np.ndarray) -> list[str]:
    """The IDs nearest the query by cosine similarity, computed against every row."""
    import numpy as np

    query = np.asarray(query_vector, dtype="<f4")
    scores = matrix @ (query / np.linalg.norm(query))
    # Sorted on (-score, id) so equal scores always come out in the same order.
    order = sorted(range(len(ids)), key=lambda i: (-float(scores[i]), ids[i]))
    return [ids[i] for i in order[:RANKER_DEPTH]]


def fuse(rankings: Sequence[Sequence[str]]) -> list[str]:
    """Reciprocal rank fusion. Ties are broken by ID."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(scores, key=lambda node_id: (-scores[node_id], node_id))


def retrieve(
    slice_store: SliceStore, candidates: Sequence[str], *, embed_query: Embedder | None = None
) -> RetrievalRecord:
    """Rank the slice's publication titles for each candidate gene."""
    ids, matrix = load_slice_vectors(slice_store)
    if not ids:
        raise ValueError(
            "the slice holds no title vectors; run `hindcast embed-titles` and open "
            "the slice with the embedding cache"
        )
    embed_query = embed_query or fastembed_embedder(query=True)
    symbols = sorted(candidates)
    query_vectors = list(embed_query([DENSE_QUERY.format(symbol=s) for s in symbols]))
    genes = [
        GeneRetrieval(
            gene_symbol=symbol,
            node_ids=fuse(
                [lexical_ranking(slice_store, symbol), dense_ranking(ids, matrix, vector)]
            )[:ROWS_PER_GENE],
        )
        for symbol, vector in zip(symbols, query_vectors, strict=True)
    ]
    return RetrievalRecord(
        cutoff=slice_store.cutoff,
        embedding_model=EMBEDDING_MODEL,
        rrf_k=RRF_K,
        ranker_depth=RANKER_DEPTH,
        rows_per_gene=ROWS_PER_GENE,
        dense_query=DENSE_QUERY,
        genes=genes,
    )


def _record_path(cutoff: str, directory: Path | None) -> Path:
    return (directory or RETRIEVAL_DIR) / f"{cutoff}.json"


def write_record(record: RetrievalRecord, directory: Path | None = None) -> Path:
    path = _record_path(record.cutoff, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.model_dump(), indent=2, sort_keys=True) + "\n")
    return path


def load_record(
    cutoff: str, candidates: Sequence[str], directory: Path | None = None
) -> RetrievalRecord | None:
    """The committed record for a cutoff, or `None` if there is none.

    A record written with other parameters or for other candidates is an
    error, not a miss: replaying it would describe a retrieval that was not run.
    """
    path = _record_path(cutoff, directory)
    if not path.exists():
        return None
    record = RetrievalRecord.model_validate_json(path.read_text())
    expected = {
        "cutoff": cutoff,
        "embedding_model": EMBEDDING_MODEL,
        "rrf_k": RRF_K,
        "ranker_depth": RANKER_DEPTH,
        "rows_per_gene": ROWS_PER_GENE,
        "dense_query": DENSE_QUERY,
    }
    actual = record.model_dump(exclude={"genes"})
    if actual != expected or [g.gene_symbol for g in record.genes] != sorted(candidates):
        raise ValueError(
            f"retrieval record {path.name} was written with other parameters or "
            f"candidates; rerun `hindcast retrieve`"
        )
    return record


def evidence_rows(
    record: RetrievalRecord, slice_store: SliceStore
) -> list[tuple[str, list[EvidenceRow]]]:
    """Read each recorded ID back through the slice. Raises if the slice lacks one."""
    out: list[tuple[str, list[EvidenceRow]]] = []
    for gene in record.genes:
        rows: list[EvidenceRow] = []
        for node_id in gene.node_ids:
            node = slice_store.node(node_id)
            if node is None:
                raise SliceLeakError(
                    f"retrieval record names {node_id}, which the slice at "
                    f"{slice_store.cutoff} does not contain"
                )
            rows.append(
                EvidenceRow(
                    node_id=node.id,
                    publication_date=str(node.prov.effective_date),
                    title=node.label,
                )
            )
        out.append((gene.gene_symbol, rows))
    return out
