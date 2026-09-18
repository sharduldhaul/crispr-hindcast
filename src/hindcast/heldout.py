"""Held-out prediction: hide measured rows inside the pre-T window, test recovery.

The forecast evaluation asks whether the system can reach a finding that had not
been made yet. This asks a different and easier question: if a measurement that
*was* in the pre-T record is taken away, can the system still reach the claim it
supported from everything else?

It matters because it separates two abilities that the forecast conflates.
Ranking a gene highly because one strong measurement says so is retrieval.
Ranking it highly when that measurement is gone, because the surrounding
evidence implies it, is inference. A system that scores well on the forecast and
badly here is passing on retrieval.

The holdout is by gene, not by row. Hiding one of a gene's twelve measurements
proves little when the other eleven remain. Hiding every measurement a gene has,
and leaving the rest of the graph intact, asks whether the rest of the graph
knows about that gene.

Selection is deterministic: genes are taken in sorted order of their identifier,
so a replay picks the same genes with no seed and no sampling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.axioms import AxiomExtractor
from hindcast.agents.base import Agent
from hindcast.agents.belief_reviser import (
    REFUSAL_CONFIDENCE_THRESHOLD,
    BeliefReviser,
)
from hindcast.models import NodeType
from hindcast.store import SliceStore, Store


class GeneHoldout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str
    gene_id: str
    measurements_hidden: int
    hidden_record_ids: list[str] = Field(default_factory=list)
    confidence_with_measurements: float
    confidence_without_measurements: float
    reportable_with: bool
    reportable_without: bool
    recovered: bool
    remaining_evidence_count: int
    note: str = ""


class HeldOutReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    genes_tested: int = 0
    recovered: int = 0
    recovery_rate: float | None = None
    mean_confidence_drop: float | None = None
    holdouts: list[GeneHoldout] = Field(default_factory=list)
    note: str = ""


class HeldOutEvaluator(Agent):
    name = "heldout"

    def run(
        self,
        store: Store,
        cutoff: date,
        *,
        max_genes: int = 12,
        min_measurements: int = 2,
    ) -> HeldOutReport:
        """Hold out each eligible gene's measurements in turn and re-run.

        `store` is the full store because the slice has to be rebuilt for each
        holdout. Nothing post-cutoff reaches the reasoning: every run below goes
        through `open_slice(cutoff)` exactly as the forecast does.
        """
        with self.tool("find_eligible_genes", cutoff=cutoff.isoformat()) as call:
            with store.open_slice(cutoff) as sl:
                counts: dict[str, list[str]] = {}
                labels: dict[str, str] = {}
                for m in sl.nodes(NodeType.MEASUREMENT):
                    # Literature is not a measurement and is not held out. What
                    # is being tested is whether the graph survives losing a
                    # measured row.
                    if m.attrs.get("assay") == "literature_comention":
                        continue
                    gid = str(m.attrs.get("gene_id") or "")
                    if not gid:
                        continue
                    counts.setdefault(gid, []).append(m.id)
                for gid in counts:
                    node = sl.node(gid)
                    labels[gid] = node.label if node else gid
            eligible = sorted(
                (gid for gid, ids in counts.items() if len(ids) >= min_measurements),
                key=lambda g: (labels.get(g, g), g),
            )[:max_genes]
            call.records_out = len(eligible)
            call.result_summary = (
                f"{len(eligible)} genes have at least {min_measurements} measurements "
                f"in the slice and are eligible for holdout"
            )

        with self.tool("baseline_run") as call:
            baseline = self._confidences(store, cutoff, hidden=frozenset())
            call.records_out = len(baseline)
            call.result_summary = f"{len(baseline)} claims in the unmodified slice"

        holdouts: list[GeneHoldout] = []
        for gid in eligible:
            hidden = frozenset(counts[gid])
            with self.tool("holdout_run", gene=labels.get(gid, gid)) as call:
                without = self._confidences(store, cutoff, hidden=hidden)
                call.records_in = len(hidden)
                call.result_summary = (
                    f"{labels.get(gid, gid)}: {len(hidden)} measurements hidden"
                )
            claim_id = f"claim:hbf_increase:{gid}"
            with_conf, with_report, _ = baseline.get(claim_id, (0.0, False, 0))
            no_conf, no_report, remaining = without.get(claim_id, (0.0, False, 0))
            holdouts.append(
                GeneHoldout(
                    gene_symbol=labels.get(gid, gid),
                    gene_id=gid,
                    measurements_hidden=len(hidden),
                    hidden_record_ids=sorted(hidden)[:20],
                    confidence_with_measurements=round(with_conf, 6),
                    confidence_without_measurements=round(no_conf, 6),
                    reportable_with=with_report,
                    reportable_without=no_report,
                    recovered=no_report,
                    remaining_evidence_count=remaining,
                    note=(
                        "recovered from the remaining evidence"
                        if no_report
                        else "not recoverable once its measurements were hidden"
                    ),
                )
            )

        tested = [h for h in holdouts if h.reportable_with]
        recovered = [h for h in tested if h.recovered]
        drops = [
            h.confidence_with_measurements - h.confidence_without_measurements
            for h in tested
        ]
        report = HeldOutReport(
            cutoff=cutoff.isoformat(),
            genes_tested=len(tested),
            recovered=len(recovered),
            recovery_rate=round(len(recovered) / len(tested), 6) if tested else None,
            mean_confidence_drop=round(sum(drops) / len(drops), 6) if drops else None,
            holdouts=holdouts,
            note=(
                "Only genes that were reportable with their measurements present are "
                "counted in the recovery rate. A gene the system could not rank in the "
                "first place says nothing about recovery."
            ),
        )
        self.finish(report.model_dump(exclude={"holdouts"}))
        return report

    def _confidences(
        self, store: Store, cutoff: date, *, hidden: frozenset[str]
    ) -> dict[str, tuple[float, bool, int]]:
        with store.open_slice(cutoff) as sl:
            masked = _MaskedSlice(sl, hidden) if hidden else sl
            axioms = AxiomExtractor(f"{self.run_id}-ho").run(masked)  # type: ignore[arg-type]
            belief = BeliefReviser(f"{self.run_id}-ho").run(masked, axioms)  # type: ignore[arg-type]
            return {
                cid: (c.confidence, c.reportable, c.evidence_count)
                for cid, c in belief.claims.items()
            }


@dataclass
class _MaskedSlice:
    """A slice with some measurement rows hidden.

    A wrapper rather than a second database, because the holdout is a question
    about the reasoning and not about the storage guarantee. The wrapped slice is
    still the only thing underneath, so nothing post-cutoff becomes reachable by
    masking rows inside it.
    """

    inner: SliceStore
    hidden: frozenset[str]

    @property
    def cutoff(self) -> str:
        return self.inner.cutoff

    @property
    def conn(self) -> Any:
        return self.inner.conn

    def assert_no_leak(self) -> None:
        self.inner.assert_no_leak()

    def node(self, node_id: str):
        if node_id in self.hidden:
            return None
        return self.inner.node(node_id)

    def nodes(self, type=None, **kw):
        return [n for n in self.inner.nodes(type, **kw) if n.id not in self.hidden]

    def gene_by_symbol(self, symbol: str):
        return self.inner.gene_by_symbol(symbol)

    def edges(self, **kw):
        return [
            e
            for e in self.inner.edges(**kw)
            if e.src not in self.hidden and e.dst not in self.hidden
        ]

    def sql(self, query: str, args=()):
        return self.inner.sql(query, args)

    def manifest(self) -> dict[str, str]:
        return self.inner.manifest()
