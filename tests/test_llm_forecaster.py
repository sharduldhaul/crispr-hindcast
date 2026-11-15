"""The language-model forecaster, tested offline with a fake transport.

No test here touches the network or needs a key. The fake stands in for the
API and counts how often it is called, which is how replay is proven.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hindcast.llm import forecaster as forecaster_module
from hindcast.llm.client import ModelRequest, ModelResponse, ReplayCache, cost_usd
from hindcast.llm.forecaster import RetrievalCondition, RunStatus
from hindcast.llm.run import run_llm_slice
from hindcast.pipeline import load_rulebook
from hindcast.store import Store

CUTOFF = date(2018, 1, 1)
MODEL = "gemini-3.8-flash"

GOOD_ANSWER = {
    "claims": [
        {"gene_symbol": "ZNF410", "confidence": 0.4, "cited_ids": [], "rationale": "a guess"},
        {"gene_symbol": "EIF2AK1", "confidence": 0.7, "cited_ids": [], "rationale": "a guess"},
    ],
    "refusals": [{"gene_symbol": "NFIX", "reason": "nothing known"}],
}


class FakeTransport:
    """Returns one fixed response and records every request it is given."""

    def __init__(self, text: str, *, status: str = "completed") -> None:
        self.text = text
        self.status = status
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            served_model_id=request.model_id,
            steps=[{"type": "model_output", "content": [{"type": "text", "text": self.text}]}],
            status=self.status,
            input_tokens=1000,
            output_tokens=500,
        )


def _run(toy_store: Store, tmp_path: Path, transport: FakeTransport | None):
    return run_llm_slice(
        CUTOFF,
        RetrievalCondition.NONE,
        model_id=MODEL,
        store_path=toy_store.path,
        cache=ReplayCache(tmp_path / "model_cache"),
        transport=transport,
        results_dir=tmp_path / "results",
    )


def test_a_model_answer_is_scored_by_the_existing_grader(toy_store: Store, tmp_path: Path):
    result = _run(toy_store, tmp_path, FakeTransport(json.dumps(GOOD_ANSWER)))

    assert result.run.status is RunStatus.RAN
    assert result.run.forecast.symbols_by_confidence() == ["EIF2AK1", "ZNF410"]
    assert result.run.forecast.refused_symbols() == {"NFIX"}
    card = result.scorecard
    assert card is not None
    assert card.forecast_size == 2 and card.refusal_count == 1
    assert card.ranking_by_confidence.first_hit_rank == 1
    written = json.loads((tmp_path / "results" / f"{result.run_id}.json").read_text())
    assert written["run"]["model_id"] == MODEL
    assert written["run"]["condition"] == "none"
    assert written["run"]["prompt_hash"]


def test_a_second_run_replays_from_the_cache_without_calling_the_model(
    toy_store: Store, tmp_path: Path
):
    transport = FakeTransport(json.dumps(GOOD_ANSWER))
    first = _run(toy_store, tmp_path, transport)
    second = _run(toy_store, tmp_path, transport)
    offline = _run(toy_store, tmp_path, None)

    assert len(transport.requests) == 1
    assert (first.run.calls_live, first.run.calls_replayed) == (1, 0)
    assert (second.run.calls_live, second.run.calls_replayed) == (0, 1)
    assert offline.run.status is RunStatus.RAN
    assert offline.scorecard == first.scorecard
    assert offline.run.forecast == first.run.forecast


def test_with_no_cached_response_and_no_transport_the_row_is_not_run(
    toy_store: Store, tmp_path: Path
):
    result = _run(toy_store, tmp_path, None)

    assert result.run.status is RunStatus.NOT_RUN
    assert result.run.status_reason
    assert result.scorecard is None and result.run.forecast is None
    assert not (tmp_path / "model_cache").exists()


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        json.dumps({"claims": []}),
        json.dumps(
            {
                "claims": [
                    {"gene_symbol": "NFIX", "confidence": 1.7, "cited_ids": [], "rationale": ""}
                ],
                "refusals": [],
            }
        ),
        json.dumps(
            {
                "claims": [
                    {"gene_symbol": "NFIX", "confidence": 0.5, "cited_ids": [], "rationale": ""}
                ],
                "refusals": [{"gene_symbol": "NFIX", "reason": "also refused"}],
            }
        ),
    ],
)
def test_a_malformed_response_is_recorded_as_a_failure_and_never_repaired(
    toy_store: Store, tmp_path: Path, text: str
):
    transport = FakeTransport(text)
    result = _run(toy_store, tmp_path, transport)
    replayed = _run(toy_store, tmp_path, transport)

    assert result.run.status is RunStatus.FAILED
    assert result.run.forecast is None and result.scorecard is None
    assert result.run.input_tokens == 1000
    # The failure is cached like any response: it replays, and is not retried.
    assert replayed.run.status is RunStatus.FAILED
    assert len(transport.requests) == 1


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_a_refused_or_truncated_response_is_a_failure(
    toy_store: Store, tmp_path: Path, status: str
):
    transport = FakeTransport(json.dumps(GOOD_ANSWER), status=status)
    result = _run(toy_store, tmp_path, transport)

    assert result.run.status is RunStatus.FAILED
    assert status in result.run.status_reason


def test_an_alias_and_its_approved_symbol_answered_twice_is_a_failure(
    toy_store: Store, tmp_path: Path
):
    answer = {
        "claims": [
            {"gene_symbol": "BCL11A", "confidence": 0.5, "cited_ids": [], "rationale": ""},
            {"gene_symbol": "CTIP1", "confidence": 0.4, "cited_ids": [], "rationale": ""},
        ],
        "refusals": [],
    }
    result = _run(toy_store, tmp_path, FakeTransport(json.dumps(answer)))

    assert result.run.status is RunStatus.FAILED
    assert "BCL11A" in result.run.status_reason


def test_editing_the_prompt_can_never_replay_an_old_response(
    toy_store: Store, tmp_path: Path, monkeypatch
):
    transport = FakeTransport(json.dumps(GOOD_ANSWER))
    _run(toy_store, tmp_path, transport)
    monkeypatch.setattr(
        forecaster_module, "SYSTEM_PROMPT", forecaster_module.SYSTEM_PROMPT + " Be brief."
    )
    after_edit = _run(toy_store, tmp_path, None)

    assert after_edit.run.status is RunStatus.NOT_RUN


def test_a_different_model_never_replays_another_models_response(toy_store: Store, tmp_path: Path):
    _run(toy_store, tmp_path, FakeTransport(json.dumps(GOOD_ANSWER)))
    other = run_llm_slice(
        CUTOFF,
        RetrievalCondition.NONE,
        model_id="some-other-model",
        store_path=toy_store.path,
        cache=ReplayCache(tmp_path / "model_cache"),
        results_dir=tmp_path / "results",
    )

    assert other.run.status is RunStatus.NOT_RUN


def test_tokens_and_cost_are_recorded_for_the_run(toy_store: Store, tmp_path: Path):
    result = _run(toy_store, tmp_path, FakeTransport(json.dumps(GOOD_ANSWER)))

    assert (result.run.input_tokens, result.run.output_tokens) == (1000, 500)
    assert result.run.cost_usd == cost_usd(MODEL, 1000, 500) == 0.002625


def test_a_model_with_no_recorded_price_cannot_be_costed():
    with pytest.raises(KeyError):
        cost_usd("unpriced-model", 1, 1)


def test_the_model_is_sent_the_task_and_candidates_and_nothing_from_the_answer_key(
    toy_store: Store, tmp_path: Path
):
    transport = FakeTransport(json.dumps(GOOD_ANSWER))
    result = _run(toy_store, tmp_path, transport)
    sent = json.dumps(transport.requests[0].model_dump())

    assert "Cutoff date: 2018-01-01" in sent
    assert "EIF2AK1" in sent
    for symbol, entry in load_rulebook().items():
        record = entry.get("establishing_record") or {}
        for field in ("doi", "pmid", "title"):
            if record.get(field):
                assert str(record[field]) not in sent, f"{symbol} {field} reached the model"
    # A gene established before the cutoff is not a question, so it is not asked.
    assert "BCL11A" not in result.run.candidate_symbols
    assert "trap" not in sent.lower()


def test_the_api_key_never_reaches_the_cache_the_result_or_the_trajectory(
    toy_store: Store, tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("GEMINI_API_KEY", "test-sentinel-key-value")
    _run(toy_store, tmp_path, FakeTransport(json.dumps(GOOD_ANSWER)))

    written = list(tmp_path.rglob("*.json"))
    assert len(written) >= 4
    for path in written:
        assert "sk-ant-test-sentinel-value" not in path.read_text(), path


def test_the_cli_reports_not_run_and_exits_zero_with_no_key_and_no_cache(
    toy_store: Store, monkeypatch
):
    from hindcast.cli import app

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    outcome = CliRunner().invoke(
        app, ["llm", "--cutoff", "2018-01-01", "--live", "--db", str(toy_store.path)]
    )

    assert outcome.exit_code == 0
    assert "not run" in outcome.output
