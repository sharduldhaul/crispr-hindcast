"""A deterministic stand-in for the embedding model, and titles to index.

The fake maps a text to a unit vector seeded by the text's hash, so equal texts
get equal vectors and no model is downloaded.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date

import numpy as np

from hindcast.llm.retrieval import EMBEDDING_DIMENSIONS
from hindcast.models import Node, NodeType, Provenance, TimeScope
from hindcast.store import Store

PRE_TITLE_ID = "pub:23522779"
POST_TITLE_ID = "pub:29735697"
POST_TITLE = "EIF2AK1 kinase HRI controls fetal hemoglobin in erythroid cells"


def fake_embed(texts: Sequence[str]) -> list[np.ndarray]:
    vectors = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vector = np.random.default_rng(seed).standard_normal(EMBEDDING_DIMENSIONS)
        vectors.append(vector / np.linalg.norm(vector))
    return vectors


def publication(node_id: str, title: str, when: date) -> Node:
    pmid = node_id.removeprefix("pub:")
    return Node(
        id=node_id,
        type=NodeType.PUBLICATION,
        label=title,
        attrs={"pmid": pmid},
        prov=Provenance(
            source_id=f"europepmc:{pmid}",
            license="MIT License",
            time_scope=TimeScope.DATED,
            publication_date=when,
            pmid=pmid,
        ),
    )


def add_post_cutoff_title(store: Store) -> None:
    """A publication dated after the 2018 cutoff whose title names the hidden result."""
    store.add_nodes([publication(POST_TITLE_ID, POST_TITLE, date(2018, 6, 1))])
