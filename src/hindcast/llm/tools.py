"""Graph tools: the read-only queries the model may call in the `graph` condition.

Contract. In: a slice connection, the candidate gene symbols, a tool name and
the arguments the model gave. Out: a `ToolResult` holding the text returned to
the model and the IDs of every node that text names.

Every tool returns node IDs, so a claim built on a tool result can cite the
rows it came from, and the IDs a run was shown are known exactly.

What this module must never do:

*   Read anything but the slice connection it is handed. No tool takes a
    path, a date or a query string, so none can ask for a later row.
*   Raise on a bad argument. An unknown gene or a malformed input is returned
    to the model as an error result, because it is the model's mistake to
    recover from and the run's to record.
*   Return unbounded text. A tool returns at most `ROWS_PER_TOOL_RESULT` rows
    and states the total, so the model knows what it was not shown.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from hindcast.store import SliceStore

#: Tool calls the model may make in one run. About one call per candidate
#: gene at the 2017 cutoff. See METHODOLOGY.md.
TOOL_CALL_BUDGET = 40

#: Rows a tool returns at most. The total is always stated beside them.
ROWS_PER_TOOL_RESULT = 20


class GraphTool(StrEnum):
    GENE_EVIDENCE_SUMMARY = "gene_evidence_summary"
    GENE_MEASUREMENTS = "gene_measurements"
    GENE_PUBLICATIONS = "gene_publications"
    COMPLEX_PARTNERS = "complex_partners"
    GENES_BY_PUBLICATION_COUNT = "genes_by_publication_count"


class GeneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str = Field(min_length=1)


class NoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel):
    """What one tool call returned: the text for the model and the IDs in it."""

    model_config = ConfigDict(extra="forbid")

    is_error: bool
    content: str
    node_ids: list[str] = Field(default_factory=list)


_GENE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "gene_symbol": {
            "type": "string",
            "description": "An HGNC gene symbol or alias, for example BCL11A.",
        }
    },
    "required": ["gene_symbol"],
}

_NO_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
}

#: The tool definitions sent to the API. Part of the request, so part of the
#: cache key: editing a description can never replay an old response.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": str(GraphTool.GENE_EVIDENCE_SUMMARY),
        "description": (
            "Counts of what the graph holds about one gene before the cutoff: "
            "publications naming it, measurements by assay, and complex partners. "
            "Call this first to decide whether a gene is worth a closer look."
        ),
        "parameters": _GENE_SCHEMA,
    },
    {
        "type": "function",
        "name": str(GraphTool.GENE_MEASUREMENTS),
        "description": (
            "Measurements recorded for one gene before the cutoff, most recent first: "
            "ID, date, assay, data source, phenotype and value. Returns at most "
            f"{ROWS_PER_TOOL_RESULT} rows and the total."
        ),
        "parameters": _GENE_SCHEMA,
    },
    {
        "type": "function",
        "name": str(GraphTool.GENE_PUBLICATIONS),
        "description": (
            "Publications dated before the cutoff that name one gene, most recent "
            "first: ID, publication date and title. Returns at most "
            f"{ROWS_PER_TOOL_RESULT} rows and the total."
        ),
        "parameters": _GENE_SCHEMA,
    },
    {
        "type": "function",
        "name": str(GraphTool.COMPLEX_PARTNERS),
        "description": (
            "Genes recorded as members of the same protein complex as one gene: "
            "gene ID, symbol and the complex they share."
        ),
        "parameters": _GENE_SCHEMA,
    },
    {
        "type": "function",
        "name": str(GraphTool.GENES_BY_PUBLICATION_COUNT),
        "description": (
            "The candidate genes ranked by how many publications dated before the "
            "cutoff name them. A count measures attention, not evidence of a role."
        ),
        "parameters": _NO_INPUT_SCHEMA,
    },
]


def _publication_count(slice_store: SliceStore, symbol: str) -> int:
    rows = slice_store.sql(
        """
        SELECT count(*) FROM node
         WHERE type = 'Publication'
           AND EXISTS (SELECT 1 FROM json_each(attrs, '$.matched_genes')
                        WHERE json_each.value = ?)
        """,
        (symbol,),
    )
    return int(rows[0][0])


def _partners(slice_store: SliceStore, gene_id: str) -> list[dict[str, str]]:
    rows = slice_store.sql(
        "SELECT src, dst, attrs FROM edge WHERE type = 'ACTS_THROUGH' "
        "AND (src = ? OR dst = ?) ORDER BY id",
        (gene_id, gene_id),
    )
    partners: dict[tuple[str, str], dict[str, str]] = {}
    for src, dst, attrs_json in rows:
        attrs = json.loads(attrs_json)
        outgoing = src == gene_id
        partner_id = str(dst if outgoing else src)
        symbol = str(attrs.get("dst_symbol" if outgoing else "src_symbol") or "")
        group = str(attrs.get("gene_group") or "")
        partners[(partner_id, group)] = {
            "node_id": partner_id,
            "gene_symbol": symbol,
            "complex": group,
        }
    return [partners[key] for key in sorted(partners)]


def _gene_evidence_summary(
    slice_store: SliceStore, candidates: Sequence[str], args: GeneInput
) -> ToolResult:
    gene = slice_store.gene_by_symbol(args.gene_symbol)
    if gene is None:
        return _unknown_gene(args.gene_symbol)
    symbol = str(gene.attrs.get("symbol") or gene.label)
    by_assay: dict[str, int] = {}
    for m in slice_store.measurements_for_gene(gene.id):
        assay = str(m.attrs.get("assay") or "unspecified")
        by_assay[assay] = by_assay.get(assay, 0) + 1
    return _ok(
        {
            "node_id": gene.id,
            "gene_symbol": symbol,
            "publications_naming_gene": _publication_count(slice_store, symbol),
            "measurements_by_assay": dict(sorted(by_assay.items())),
            "complex_partners": len(_partners(slice_store, gene.id)),
        },
        [gene.id],
    )


def _gene_measurements(
    slice_store: SliceStore, candidates: Sequence[str], args: GeneInput
) -> ToolResult:
    gene = slice_store.gene_by_symbol(args.gene_symbol)
    if gene is None:
        return _unknown_gene(args.gene_symbol)
    measurements = slice_store.measurements_for_gene(gene.id)
    measurements.sort(key=lambda m: m.id)
    measurements.sort(key=lambda m: str(m.prov.effective_date), reverse=True)
    rows = [
        {
            "node_id": m.id,
            "date": str(m.prov.effective_date),
            "assay": m.attrs.get("assay"),
            "data_source": m.attrs.get("datasource"),
            "phenotype_id": m.attrs.get("phenotype_id"),
            "value": m.attrs.get("value"),
        }
        for m in measurements[:ROWS_PER_TOOL_RESULT]
    ]
    return _ok(
        {"gene_node_id": gene.id, "total": len(measurements), "rows": rows},
        [gene.id, *(str(r["node_id"]) for r in rows)],
    )


def _gene_publications(
    slice_store: SliceStore, candidates: Sequence[str], args: GeneInput
) -> ToolResult:
    gene = slice_store.gene_by_symbol(args.gene_symbol)
    if gene is None:
        return _unknown_gene(args.gene_symbol)
    symbol = str(gene.attrs.get("symbol") or gene.label)
    found = slice_store.sql(
        """
        SELECT id, effective_date, label FROM node
         WHERE type = 'Publication'
           AND EXISTS (SELECT 1 FROM json_each(attrs, '$.matched_genes')
                        WHERE json_each.value = ?)
         ORDER BY effective_date DESC, id LIMIT ?
        """,
        (symbol, ROWS_PER_TOOL_RESULT),
    )
    rows = [
        {"node_id": str(r[0]), "publication_date": str(r[1]), "title": str(r[2])} for r in found
    ]
    return _ok(
        {
            "gene_node_id": gene.id,
            "total": _publication_count(slice_store, symbol),
            "rows": rows,
        },
        [gene.id, *(r["node_id"] for r in rows)],
    )


def _complex_partners(
    slice_store: SliceStore, candidates: Sequence[str], args: GeneInput
) -> ToolResult:
    gene = slice_store.gene_by_symbol(args.gene_symbol)
    if gene is None:
        return _unknown_gene(args.gene_symbol)
    partners = _partners(slice_store, gene.id)
    rows = partners[:ROWS_PER_TOOL_RESULT]
    return _ok(
        {"gene_node_id": gene.id, "total": len(partners), "rows": rows},
        [gene.id, *(r["node_id"] for r in rows)],
    )


def _genes_by_publication_count(
    slice_store: SliceStore, candidates: Sequence[str], args: NoInput
) -> ToolResult:
    rows: list[dict[str, Any]] = []
    for symbol in sorted(candidates):
        gene = slice_store.gene_by_symbol(symbol)
        if gene is None:
            continue
        rows.append(
            {
                "node_id": gene.id,
                "gene_symbol": symbol,
                "publications_naming_gene": _publication_count(slice_store, symbol),
            }
        )
    rows.sort(key=lambda r: (-r["publications_naming_gene"], r["gene_symbol"]))
    return _ok({"total": len(rows), "rows": rows}, [r["node_id"] for r in rows])


def _ok(payload: dict[str, Any], node_ids: Sequence[str]) -> ToolResult:
    return ToolResult(
        is_error=False,
        content=json.dumps(payload, sort_keys=True),
        node_ids=sorted(set(node_ids)),
    )


def _unknown_gene(name: str) -> ToolResult:
    return ToolResult(
        is_error=True,
        content=f"No gene in the graph resolves from {name!r} at this cutoff.",
    )


_Handler = Callable[[SliceStore, Sequence[str], Any], ToolResult]

_TOOLS: dict[GraphTool, tuple[type[BaseModel], _Handler]] = {
    GraphTool.GENE_EVIDENCE_SUMMARY: (GeneInput, _gene_evidence_summary),
    GraphTool.GENE_MEASUREMENTS: (GeneInput, _gene_measurements),
    GraphTool.GENE_PUBLICATIONS: (GeneInput, _gene_publications),
    GraphTool.COMPLEX_PARTNERS: (GeneInput, _complex_partners),
    GraphTool.GENES_BY_PUBLICATION_COUNT: (NoInput, _genes_by_publication_count),
}


def run_tool(
    slice_store: SliceStore, candidates: Sequence[str], name: str, tool_input: Any
) -> ToolResult:
    """Run one tool call against the slice. A bad name or input is an error result."""
    if name not in GraphTool:
        return ToolResult(is_error=True, content=f"There is no tool named {name!r}.")
    input_model, handler = _TOOLS[GraphTool(name)]
    try:
        args = input_model.model_validate(tool_input)
    except ValidationError as exc:
        return ToolResult(
            is_error=True,
            content=f"The input to {name} did not match its schema "
            f"({exc.error_count()} validation error(s)).",
        )
    return handler(slice_store, candidates, args)
