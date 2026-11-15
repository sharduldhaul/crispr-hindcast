"""The scorecard's comparison table, rendered from results built in the test.

The committed model rows may all be `not_run`, so the path that prints a row
that ran is exercised here with a fake transport.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from hindcast.llm.client import ModelRequest, ModelResponse, ReplayCache
from hindcast.llm.forecaster import RetrievalCondition
from hindcast.llm.run import run_llm_slice
from hindcast.pipeline import ABLATIONS, run_slice
from hindcast.store import Store

CUTOFF = date(2018, 1, 1)
ANSWER = {
    "claims": [
        {"gene_symbol": "EIF2AK1", "confidence": 0.7, "cited_ids": [], "rationale": "a guess"},
    ],
    "refusals": [{"gene_symbol": "NFIX", "reason": "nothing known"}],
}


def _renderer() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "render_scorecard.py"
    spec = importlib.util.spec_from_file_location("render_scorecard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _answering(request: ModelRequest) -> ModelResponse:
    return ModelResponse(
        served_model_id=request.model_id,
        steps=[{"type": "model_output", "content": [{"type": "text", "text": json.dumps(ANSWER)}]}],
        status="completed",
        input_tokens=1000,
        output_tokens=500,
    )


def _rows(toy_store: Store, tmp_path: Path) -> tuple[list[dict], list[dict]]:
    rule_based = [
        json.loads(
            run_slice(
                CUTOFF, store_path=toy_store.path, ablation=spec, write_results=False
            ).model_dump_json()
        )
        for spec in ABLATIONS
        if spec.name in ("full system", "no graph")
    ]
    llm = [
        json.loads(
            run_llm_slice(
                CUTOFF,
                condition,
                store_path=toy_store.path,
                cache=ReplayCache(tmp_path / "model_cache"),
                # Only the `none` row is given a model, so the others are not run.
                transport=_answering if condition is RetrievalCondition.NONE else None,
                results_dir=tmp_path / "results",
            ).model_dump_json()
        )
        for condition in RetrievalCondition
    ]
    return rule_based, llm


def test_the_comparison_has_one_row_per_system_and_marks_rows_that_did_not_run(
    toy_store: Store, tmp_path: Path
):
    rule_based, llm = _rows(toy_store, tmp_path)
    lines = _renderer().comparison(rule_based, llm)
    rows = {line.split(" | ")[1]: line for line in lines if line.startswith("| 2018-01-01")}

    assert list(rows) == [
        "rule-based system",
        "flat literature baseline",
        "model alone",
        "model with text retrieval",
        "model with graph tools",
    ]
    assert rows["model with graph tools"].count("not run") == 8
    assert "not run" not in rows["model alone"]
    assert rows["rule-based system"].count("n/a") == 3
    assert any(line.startswith("Not run: 2 of 3 model rows") for line in lines)


def test_a_model_row_that_ran_reports_its_rates_with_their_counts(toy_store: Store, tmp_path: Path):
    rule_based, llm = _rows(toy_store, tmp_path)
    lines = _renderer().comparison(rule_based, llm)
    cells = next(line for line in lines if "| model alone |" in line).split(" | ")

    # One claim, shown nothing: ungrounded, and recalled because it came true.
    assert cells[-3].startswith("0.00 (0 of 1) [")
    assert cells[-2] == "0"
    assert cells[-1] == "1 of 1 |"


def test_the_headline_has_one_row_per_forecaster_and_marks_rows_that_did_not_run(
    toy_store: Store, tmp_path: Path
):
    rule_based, llm = _rows(toy_store, tmp_path)
    lines = _renderer().headline(rule_based, llm)
    rows = {line.split(" | ")[1]: line for line in lines if line.startswith("| 2018-01-01")}

    assert list(rows) == [
        "rule-based system",
        "model alone",
        "model with text retrieval",
        "model with graph tools",
    ]
    assert rows["rule-based system"].count("n/a") == 2
    assert rows["model alone"].endswith("| 0 of 1 | 1 of 1 |")
    assert rows["model with graph tools"].count("not run") == 4


def test_the_results_chart_is_refused_when_a_model_row_did_not_run(
    toy_store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    chart = importlib.import_module("render_results_chart")
    rule_based, llm = _rows(toy_store, tmp_path)

    with pytest.raises(SystemExit, match="not run"):
        chart.cards_by_cutoff(rule_based, llm)
