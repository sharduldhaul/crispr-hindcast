"""Grounding of cited evidence, checked on fixture runs with no model."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from hindcast.llm.client import ReplayCache
from hindcast.llm.forecaster import (
    ModelAnswer,
    ModelClaim,
    ModelRun,
    RetrievalCondition,
    RunStatus,
    _to_forecast,
)
from hindcast.llm.grounding import CitationStatus, Rate, check_grounding
from hindcast.llm.run import run_llm_slice
from hindcast.store import SliceStore, Store
from tests.retrieval_fakes import POST_TITLE_ID, PRE_TITLE_ID, add_post_cutoff_title
from tests.test_llm_forecaster import FakeTransport

CUTOFF = date(2018, 1, 1)


def fixture_run(
    slice_store: SliceStore, cited: dict[str, list[str]], context: list[str]
) -> ModelRun:
    answer = ModelAnswer(
        claims=[
            ModelClaim(gene_symbol=symbol, confidence=0.5, cited_ids=ids, rationale="")
            for symbol, ids in cited.items()
        ],
        refusals=[],
    )
    return ModelRun(
        status=RunStatus.RAN,
        status_reason="",
        condition=RetrievalCondition.TEXT,
        model_id="fixture",
        prompt_hash="fixture",
        candidate_symbols=sorted(cited),
        context_node_ids=context,
        answer=answer,
        forecast=_to_forecast(answer, slice_store, RetrievalCondition.TEXT),
    )


def check(toy_store: Store, cited: dict[str, list[str]], context: list[str]):
    with toy_store.open_slice(CUTOFF) as slice_store:
        return check_grounding(fixture_run(slice_store, cited, context), slice_store, toy_store)


def test_a_claim_citing_a_shown_row_that_names_its_gene_is_grounded(toy_store: Store):
    report = check(toy_store, {"BCL11A": [PRE_TITLE_ID, "meas:pre"]}, [PRE_TITLE_ID, "meas:pre"])

    assert [c.status for c in report.claims[0].citations] == [CitationStatus.IN_CONTEXT] * 2
    assert report.claims[0].grounded
    assert report.citation_validity == Rate(numerator=2, denominator=2)
    assert report.grounded_claim_rate == Rate(numerator=1, denominator=1)


def test_a_row_in_the_slice_that_the_model_was_not_shown_is_out_of_context(toy_store: Store):
    report = check(toy_store, {"BCL11A": ["meas:pre"]}, [PRE_TITLE_ID])

    assert report.claims[0].citations[0].status is CitationStatus.OUT_OF_CONTEXT
    assert not report.claims[0].grounded
    # Valid, because the slice holds it, but not something the model was given.
    assert report.citation_validity == Rate(numerator=1, denominator=1)
    assert report.citations_in_context == Rate(numerator=0, denominator=1)


def test_an_id_that_exists_nowhere_is_fabricated(toy_store: Store):
    report = check(toy_store, {"BCL11A": ["pub:00000000"]}, ["pub:00000000"])

    assert report.fabricated_ids == ["pub:00000000"]
    assert report.citation_validity == Rate(numerator=0, denominator=1)
    assert not report.claims[0].grounded


def test_an_id_dated_after_the_cutoff_is_post_cutoff_not_fabricated(toy_store: Store):
    add_post_cutoff_title(toy_store)
    report = check(toy_store, {"EIF2AK1": [POST_TITLE_ID, "meas:post"]}, [])

    assert report.post_cutoff_ids == sorted([POST_TITLE_ID, "meas:post"])
    assert report.fabricated_ids == []
    assert not report.claims[0].grounded


def test_a_shown_row_about_another_gene_does_not_ground_a_claim(toy_store: Store):
    report = check(toy_store, {"EIF2AK1": [PRE_TITLE_ID, "meas:pre"]}, [PRE_TITLE_ID, "meas:pre"])

    assert [c.names_gene for c in report.claims[0].citations] == [False, False]
    assert not report.claims[0].grounded


def test_the_gene_reference_node_cited_alone_grounds_nothing(toy_store: Store):
    report = check(toy_store, {"BCL11A": ["gene:HGNC:13221"]}, ["gene:HGNC:13221"])

    assert report.claims[0].citations[0].status is CitationStatus.IN_CONTEXT
    assert not report.claims[0].grounded


def test_a_claim_with_no_citation_is_ungrounded_and_rates_keep_their_denominators(
    toy_store: Store,
):
    report = check(toy_store, {"BCL11A": [], "EIF2AK1": []}, [])

    assert report.citation_validity == Rate(numerator=0, denominator=0)
    assert report.grounded_claim_rate == Rate(numerator=0, denominator=2)


def test_grounding_is_refused_for_a_run_with_no_forecast(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as slice_store:
        run = fixture_run(slice_store, {}, [])
        run.forecast = None
        with pytest.raises(ValueError):
            check_grounding(run, slice_store, toy_store)


def test_the_result_file_carries_the_grounding_report(toy_store: Store, tmp_path: Path):
    answer = {
        "claims": [
            {"gene_symbol": "EIF2AK1", "confidence": 0.7, "cited_ids": ["x:1"], "rationale": ""}
        ],
        "refusals": [],
    }
    result = run_llm_slice(
        CUTOFF,
        RetrievalCondition.NONE,
        model_id="gemini-3.8-flash",
        store_path=toy_store.path,
        cache=ReplayCache(tmp_path / "model_cache"),
        transport=FakeTransport(json.dumps(answer)),
        results_dir=tmp_path / "results",
    )
    written = json.loads((tmp_path / "results" / f"{result.run_id}.json").read_text())

    assert written["grounding"]["fabricated_ids"] == ["x:1"]
    assert written["grounding"]["grounded_claim_rate"] == {"numerator": 0, "denominator": 1}
