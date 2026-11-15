"""The graph tools and the tool loop, tested offline with a scripted transport."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from hindcast.llm import forecaster as forecaster_module
from hindcast.llm.client import ModelRequest, ModelResponse, ReplayCache
from hindcast.llm.forecaster import RetrievalCondition, RunStatus, ToolOutcome
from hindcast.llm.run import run_llm_slice
from hindcast.llm.tools import TOOL_DEFINITIONS, GraphTool, run_tool
from hindcast.models import Edge, EdgeType, Node
from hindcast.store import Store
from tests.conftest import dated_prov
from tests.retrieval_fakes import publication

CUTOFF = date(2018, 1, 1)
MODEL = "gemini-3.8-flash"
CANDIDATES = ["EIF2AK1", "NFIX"]

ANSWER = {
    "claims": [
        {
            "gene_symbol": "EIF2AK1",
            "confidence": 0.6,
            "cited_ids": ["pub:100"],
            "rationale": "named beside heme-regulated translation",
        }
    ],
    "refusals": [],
}


def naming(node: Node, *symbols: str) -> Node:
    node.attrs["matched_genes"] = list(symbols)
    return node


def add_graph_rows(store: Store) -> None:
    """Pre-cutoff rows for EIF2AK1: one publication and one complex partner."""
    store.add_nodes(
        [naming(publication("pub:100", "Heme-regulated kinase", date(2015, 5, 1)), "EIF2AK1")]
    )
    store.add_edges(
        [
            Edge(
                id="edge:partner",
                type=EdgeType.ACTS_THROUGH,
                src="gene:HGNC:3005",
                dst="gene:HGNC:13221",
                attrs={
                    "src_symbol": "EIF2AK1",
                    "dst_symbol": "BCL11A",
                    "gene_group": "toy complex",
                    "basis": "test",
                },
                prov=dated_prov("test:partner", date(2010, 1, 1)),
            )
        ]
    )


def function_call(call_id: str, name: str, **arguments: str) -> dict:
    return {"type": "function_call", "id": call_id, "name": name, "arguments": arguments}


def model_output(text: str) -> dict:
    return {"type": "model_output", "content": [{"type": "text", "text": text}]}


class ScriptedTransport:
    """Returns the next scripted response and records every request."""

    def __init__(self, *turns: list[dict] | str) -> None:
        self.turns = list(turns)
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> ModelResponse:
        # After the script ends the last turn repeats, for the runaway test.
        turn = self.turns[min(len(self.requests), len(self.turns) - 1)]
        self.requests.append(request)
        answered = isinstance(turn, str)
        return ModelResponse(
            served_model_id=request.model_id,
            steps=[model_output(turn)] if answered else turn,
            status="completed" if answered else "requires_action",
            input_tokens=100,
            output_tokens=10,
        )


def _run(store: Store, tmp_path: Path, transport: ScriptedTransport | None):
    return run_llm_slice(
        CUTOFF,
        RetrievalCondition.GRAPH,
        model_id=MODEL,
        store_path=store.path,
        cache=ReplayCache(tmp_path / "model_cache"),
        transport=transport,
        trajectory_dir=tmp_path / "trajectories",
        results_dir=tmp_path / "results",
    )


def test_every_tool_is_defined_as_a_function_with_an_object_schema():
    assert [d["name"] for d in TOOL_DEFINITIONS] == [str(t) for t in GraphTool]
    for definition in TOOL_DEFINITIONS:
        assert definition["type"] == "function"
        assert definition["parameters"]["type"] == "object"


def test_each_tool_returns_the_ids_of_the_rows_it_names(toy_store: Store):
    add_graph_rows(toy_store)
    with toy_store.open_slice(CUTOFF) as slice_store:
        for tool in GraphTool:
            arguments = (
                {} if tool is GraphTool.GENES_BY_PUBLICATION_COUNT else {"gene_symbol": "HRI"}
            )
            result = run_tool(slice_store, CANDIDATES, tool, arguments)
            assert not result.is_error, tool
            assert "gene:HGNC:3005" in result.node_ids, tool
            for node_id in result.node_ids:
                assert node_id in result.content, (tool, node_id)

        publications = run_tool(
            slice_store, CANDIDATES, GraphTool.GENE_PUBLICATIONS, {"gene_symbol": "EIF2AK1"}
        )
        partners = run_tool(
            slice_store, CANDIDATES, GraphTool.COMPLEX_PARTNERS, {"gene_symbol": "BCL11A"}
        )
    assert json.loads(publications.content)["rows"] == [
        {"node_id": "pub:100", "publication_date": "2015-05-01", "title": "Heme-regulated kinase"}
    ]
    assert json.loads(partners.content)["rows"] == [
        {"node_id": "gene:HGNC:3005", "gene_symbol": "EIF2AK1", "complex": "toy complex"}
    ]


def test_a_bad_tool_call_is_an_error_result_and_never_raises(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as slice_store:
        unknown_gene = run_tool(
            slice_store, CANDIDATES, GraphTool.GENE_MEASUREMENTS, {"gene_symbol": "NOT_A_GENE"}
        )
        unknown_tool = run_tool(slice_store, CANDIDATES, "run_sql", {"query": "SELECT 1"})
        extra_field = run_tool(
            slice_store,
            CANDIDATES,
            GraphTool.GENE_MEASUREMENTS,
            {"gene_symbol": "BCL11A", "cutoff": "2030-01-01"},
        )
    for result in (unknown_gene, unknown_tool, extra_field):
        assert result.is_error and result.node_ids == []


def test_the_tool_loop_records_each_call_and_replays_offline(toy_store: Store, tmp_path: Path):
    add_graph_rows(toy_store)
    transport = ScriptedTransport(
        [
            {"type": "thought", "signature": "c2ln"},
            function_call("call_1", "gene_publications", gene_symbol="EIF2AK1"),
            function_call("call_2", "gene_measurements", gene_symbol="NOT_A_GENE"),
        ],
        json.dumps(ANSWER),
    )
    live = _run(toy_store, tmp_path, transport)
    offline = _run(toy_store, tmp_path, None)

    assert live.run.status is RunStatus.RAN
    assert (live.run.calls_live, offline.run.calls_live, offline.run.calls_replayed) == (2, 0, 2)
    assert offline.run.cache_keys == live.run.cache_keys
    assert offline.run.forecast == live.run.forecast and offline.scorecard == live.scorecard
    assert [(c.turn, c.tool, c.outcome) for c in live.run.tool_calls] == [
        (1, "gene_publications", ToolOutcome.RETURNED),
        (1, "gene_measurements", ToolOutcome.ERROR),
    ]
    assert live.run.tool_calls[0].arguments == {"gene_symbol": "EIF2AK1"}
    assert live.run.context_node_ids == ["gene:HGNC:3005", "pub:100"]

    # The second request carries the first response verbatim and one result per call.
    first, second = transport.requests
    assert first.tools == TOOL_DEFINITIONS and len(first.input) == 1
    assert second.input[0] == first.input[0]
    assert second.input[1:4] == transport.turns[0]
    results = second.input[4:]
    assert [(r["type"], r["call_id"]) for r in results] == [
        ("function_result", "call_1"),
        ("function_result", "call_2"),
    ]
    assert [r["name"] for r in results] == ["gene_publications", "gene_measurements"]
    assert "pub:100" in results[0]["result"][0]["text"] and "is_error" not in results[0]
    assert results[1]["is_error"] is True

    trajectory = json.loads(
        (tmp_path / "trajectories" / live.run_id / "llm_forecaster.json").read_text()
    )
    logged = [c for c in trajectory["tool_calls"] if c["name"].startswith("graph_tool:")]
    assert logged[0]["args"] == {"arguments": {"gene_symbol": "EIF2AK1"}}
    assert "pub:100" in logged[0]["result_summary"]


def test_calls_past_the_budget_are_not_run_and_the_model_is_told(
    toy_store: Store, tmp_path: Path, monkeypatch
):
    add_graph_rows(toy_store)
    monkeypatch.setattr(forecaster_module, "TOOL_CALL_BUDGET", 1)
    transport = ScriptedTransport(
        [
            function_call("call_1", "gene_publications", gene_symbol="EIF2AK1"),
            function_call("call_2", "gene_publications", gene_symbol="BCL11A"),
        ],
        json.dumps(ANSWER),
    )
    result = _run(toy_store, tmp_path, transport)

    assert [c.outcome for c in result.run.tool_calls] == [
        ToolOutcome.RETURNED,
        ToolOutcome.OVER_BUDGET,
    ]
    assert result.run.tool_calls[1].node_ids == []
    refused = transport.requests[1].input[-1]
    assert refused["is_error"] is True
    assert refused["result"] == [{"type": "text", "text": forecaster_module.BUDGET_SPENT}]


def test_a_model_that_never_answers_is_a_failure(toy_store: Store, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(forecaster_module, "MAX_MODEL_TURNS", 3)
    transport = ScriptedTransport([function_call("call_1", "genes_by_publication_count")])
    result = _run(toy_store, tmp_path, transport)

    assert result.run.status is RunStatus.FAILED
    assert "3 model turns" in result.run.status_reason
    assert len(transport.requests) == 3


def test_a_loop_cut_short_by_a_cache_miss_is_not_run_and_reports_no_context(
    toy_store: Store, tmp_path: Path
):
    add_graph_rows(toy_store)
    transport = ScriptedTransport(
        [function_call("call_1", "gene_publications", gene_symbol="EIF2AK1")], json.dumps(ANSWER)
    )
    _run(toy_store, tmp_path, transport)
    second_key = transport.requests[1].cache_key()
    (tmp_path / "model_cache" / f"{second_key}.json").unlink()
    result = _run(toy_store, tmp_path, None)

    assert result.run.status is RunStatus.NOT_RUN
    assert result.run.tool_calls == [] and result.run.context_node_ids == []
