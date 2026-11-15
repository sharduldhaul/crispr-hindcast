"""Text retrieval: the two rankers, their fusion, the cache and the record.

Tested with fake vectors, so no embedding model is downloaded. The routes by
which retrieval could leak a post-cutoff row are in `test_slice_leak.py`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from hindcast.llm import retrieval
from hindcast.llm.client import ReplayCache
from hindcast.llm.forecaster import RetrievalCondition, RunStatus
from hindcast.llm.run import candidate_symbols, run_llm_slice
from hindcast.pipeline import load_rulebook
from hindcast.store import Store
from tests.retrieval_fakes import PRE_TITLE_ID, fake_embed, publication
from tests.test_llm_forecaster import GOOD_ANSWER, MODEL, FakeTransport

CUTOFF = date(2018, 1, 1)


def _index(store: Store, tmp_path: Path) -> Path:
    path = tmp_path / "title_embeddings.db"
    retrieval.build_title_embeddings(store, path, embed=fake_embed)
    return path


def test_the_lexical_ranker_finds_a_title_that_names_the_symbol(toy_store: Store):
    toy_store.add_nodes([publication("pub:1", "Globin switching in mice", date(2010, 1, 1))])
    with toy_store.open_slice(CUTOFF) as sl:
        assert retrieval.lexical_ranking(sl, "BCL11A") == [PRE_TITLE_ID]
        assert retrieval.lexical_ranking(sl, "ZNF410") == []


def test_a_symbol_with_query_syntax_in_it_is_searched_as_text(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as sl:
        assert retrieval.lexical_ranking(sl, 'BCL11A" OR "dissection') == []
        assert retrieval.lexical_ranking(sl, "HBG1/2") == []


def test_the_dense_ranker_puts_the_nearest_vector_first_and_breaks_ties_by_id():
    matrix = np.zeros((3, retrieval.EMBEDDING_DIMENSIONS), dtype="<f4")
    matrix[0, 0] = matrix[1, 1] = matrix[2, 1] = 1.0
    query = np.zeros(retrieval.EMBEDDING_DIMENSIONS)
    query[1] = 2.0

    assert retrieval.dense_ranking(["pub:a", "pub:c", "pub:b"], matrix, query) == [
        "pub:b",
        "pub:c",
        "pub:a",
    ]


def test_fusion_rewards_a_row_both_rankers_return():
    fused = retrieval.fuse([["pub:a", "pub:b"], ["pub:c", "pub:b"]])

    assert fused[0] == "pub:b"
    # The two rows ranked first by one ranker each have equal scores.
    assert fused[1:] == ["pub:a", "pub:c"]


def test_the_cache_embeds_each_title_once(toy_store: Store, tmp_path: Path):
    calls: list[int] = []

    def counting(texts):
        calls.append(len(texts))
        return fake_embed(texts)

    path = tmp_path / "title_embeddings.db"
    first = retrieval.build_title_embeddings(toy_store, path, embed=counting)
    second = retrieval.build_title_embeddings(toy_store, path, embed=counting)

    assert (first.titles_total, first.titles_embedded) == (1, 1)
    assert second.titles_embedded == 0
    assert calls == [1]


def test_a_vector_of_the_wrong_length_is_rejected(toy_store: Store, tmp_path: Path):
    with pytest.raises(ValueError, match="length"):
        retrieval.build_title_embeddings(
            toy_store, tmp_path / "e.db", embed=lambda texts: [np.ones(8) for _ in texts]
        )


def test_a_vector_cached_for_an_older_title_is_not_copied_into_the_slice(
    toy_store: Store, tmp_path: Path
):
    path = _index(toy_store, tmp_path)
    toy_store.conn.execute("UPDATE node SET label = 'A corrected title' WHERE type = 'Publication'")
    toy_store.conn.commit()

    with toy_store.open_slice(CUTOFF, title_embeddings=path) as sl:
        assert sl.sql("SELECT count(*) FROM title_embedding")[0][0] == 0


def test_retrieval_without_vectors_fails_instead_of_using_one_ranker(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as sl, pytest.raises(ValueError, match="no title vectors"):
        retrieval.retrieve(sl, ["BCL11A"], embed_query=fake_embed)


def test_a_record_written_with_other_parameters_is_an_error(
    toy_store: Store, tmp_path: Path, monkeypatch
):
    path = _index(toy_store, tmp_path)
    with toy_store.open_slice(CUTOFF, title_embeddings=path) as sl:
        record = retrieval.retrieve(sl, ["BCL11A"], embed_query=fake_embed)
    retrieval.write_record(record, tmp_path)

    assert retrieval.load_record(CUTOFF.isoformat(), ["BCL11A"], tmp_path) == record
    with pytest.raises(ValueError, match="other parameters or candidates"):
        retrieval.load_record(CUTOFF.isoformat(), ["BCL11A", "ZNF410"], tmp_path)
    monkeypatch.setattr(retrieval, "ROWS_PER_GENE", retrieval.ROWS_PER_GENE + 1)
    with pytest.raises(ValueError, match="other parameters or candidates"):
        retrieval.load_record(CUTOFF.isoformat(), ["BCL11A"], tmp_path)


def _run_text(toy_store: Store, tmp_path: Path, transport: FakeTransport | None):
    return run_llm_slice(
        CUTOFF,
        RetrievalCondition.TEXT,
        model_id=MODEL,
        store_path=toy_store.path,
        cache=ReplayCache(tmp_path / "model_cache"),
        transport=transport,
        results_dir=tmp_path / "results",
    )


def test_the_text_condition_is_not_run_without_a_retrieval_record(toy_store: Store, tmp_path: Path):
    transport = FakeTransport(json.dumps(GOOD_ANSWER))
    result = _run_text(toy_store, tmp_path, transport)

    assert result.run.status is RunStatus.NOT_RUN
    assert "retrieval record" in result.run.status_reason
    assert transport.requests == []


def test_the_text_condition_gives_the_model_ids_titles_and_dates(toy_store: Store, tmp_path: Path):
    path = _index(toy_store, tmp_path)
    candidates = candidate_symbols(load_rulebook(), CUTOFF)
    with toy_store.open_slice(CUTOFF, title_embeddings=path) as sl:
        retrieval.write_record(retrieval.retrieve(sl, candidates, embed_query=fake_embed))

    transport = FakeTransport(json.dumps(GOOD_ANSWER))
    result = _run_text(toy_store, tmp_path, transport)
    replayed = _run_text(toy_store, tmp_path, None)

    prompt = transport.requests[0].input[0]["content"][0]["text"]
    assert f"[{PRE_TITLE_ID}] 2013-03-22 | BCL11A enhancer dissection" in prompt
    assert result.run.status is RunStatus.RAN
    assert result.run.context_node_ids == [PRE_TITLE_ID]
    # The record alone rebuilds the same request, with no embedding model.
    assert replayed.run.cache_keys == result.run.cache_keys
    assert (replayed.run.calls_live, replayed.run.calls_replayed) == (0, 1)
