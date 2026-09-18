"""Run one evaluation slice end to end, or all of them.

The order is fixed and each step gets only what its contract allows. The
forecaster sees a slice. The grader sees the finished forecast and the rule
book, never the slice. The adversary sees the full store, because an adversary
that only knows what the forecaster knows cannot set a trap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast import provenance
from hindcast.provenance import ProvenanceReport
from hindcast.agents.adversary import Adversary, TrapSet
from hindcast.agents.axioms import AxiomExtractor, AxiomSet
from hindcast.agents.baseline import CachedModelBaseline, FlatLiteratureBaseline
from hindcast.agents.belief_reviser import BeliefMap, BeliefReviser
from hindcast.agents.curator import Curator, IngestionReport
from hindcast.agents.forecast import Forecast, Forecaster
from hindcast.agents.grader import Grader, Scorecard
from hindcast.agents.method_signature import MethodSignature, UniformSignature
from hindcast.scope import ALL_SLICES
from hindcast.store import Store

ROOT = Path(__file__).resolve().parents[2]
RULEBOOK = ROOT / "eval" / "rulebook" / "gene_establishment.json"
ADJUDICATIONS = ROOT / "eval" / "rulebook" / "adjudications.json"
DEFAULT_DB = ROOT / "data" / "work" / "graph.db"
RESULTS_DIR = ROOT / "eval" / "results"


class AblationSpec(BaseModel):
    """One ablation row. The name is what appears in the scorecard table."""

    model_config = ConfigDict(extra="forbid")

    name: str
    uniform_weights: bool = False
    flat_confidence: bool = False
    no_ontology_normalization: bool = False
    no_graph: bool = False
    description: str = ""


ABLATIONS: tuple[AblationSpec, ...] = (
    AblationSpec(name="full system", description="every component enabled"),
    AblationSpec(
        name="no method signature",
        uniform_weights=True,
        description="every measurement weighs the same",
    ),
    AblationSpec(
        name="no belief revision",
        flat_confidence=True,
        description="claims hold the prior; evidence does not move them",
    ),
    AblationSpec(
        name="no ontology normalization",
        no_ontology_normalization=True,
        description="gene symbols matched as strings, aliases unresolved",
    ),
    AblationSpec(
        name="no graph",
        no_graph=True,
        description="pre-cutoff publication counts only, ranked by count",
    ),
)


class SliceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    run_id: str
    ablation: str
    scorecard: Scorecard
    forecast: Forecast
    axiom_count: int = 0
    claim_count: int = 0
    revision_count: int = 0
    trap_count: int = 0
    provenance_report: ProvenanceReport | None = None
    slice_manifest: dict[str, str] = Field(default_factory=dict)


def load_rulebook() -> dict[str, dict]:
    """The frozen rule book, with adjudications applied and flagged.

    Adjudications exist because the rule book's rule is blunt: it reads titles.
    Where it is demonstrably wrong, a correction is recorded in
    `eval/rulebook/adjudications.json` with the PMID and the reason, and the
    entry is flagged `adjudicated`. Every adjudication was made before the first
    evaluation run and is committed under the same tag, so a reader can
    recompute the scorecard without them and see what changes.
    """
    if not RULEBOOK.exists():
        raise FileNotFoundError(
            f"rule book missing at {RULEBOOK}. Run scripts/build_rulebook.py and tag it."
        )
    book = json.loads(RULEBOOK.read_text())
    if ADJUDICATIONS.exists():
        for symbol, fix in json.loads(ADJUDICATIONS.read_text()).items():
            entry = book.setdefault(symbol, {"symbol": symbol, "core_scope": False})
            entry["established"] = fix.get("established", entry.get("established", False))
            entry["establishing_record"] = fix.get("establishing_record")
            entry["adjudicated"] = True
            entry["adjudication_reason"] = fix.get("reason", "")
    return book


def run_slice(
    cutoff: date,
    *,
    store_path: Path | str = DEFAULT_DB,
    ablation: AblationSpec | None = None,
    trajectory_dir: Path | None = None,
    write_results: bool = True,
) -> SliceResult:
    spec = ablation or ABLATIONS[0]
    run_id = f"{cutoff.isoformat()}_{spec.name.replace(' ', '-')}"
    store = Store(store_path)
    try:
        slice_store = store.open_slice(cutoff)
        try:
            slice_store.assert_no_leak()
            establishment = load_rulebook()

            if spec.no_graph:
                baseline = FlatLiteratureBaseline(run_id, trajectory_dir=trajectory_dir)
                result = baseline.run(slice_store)
                forecast = result.forecast
                assert forecast is not None
                axioms = AxiomSet(cutoff=slice_store.cutoff)
                belief = BeliefMap(cutoff=slice_store.cutoff)
            else:
                signature = (
                    UniformSignature() if spec.uniform_weights else MethodSignature()
                )
                extractor = AxiomExtractor(
                    run_id, signature=signature, trajectory_dir=trajectory_dir
                )
                axioms = extractor.run(slice_store)

                reviser = BeliefReviser(run_id, trajectory_dir=trajectory_dir)
                belief = reviser.run(
                    slice_store,
                    axioms,
                    store=store,
                    flat_confidence=spec.flat_confidence,
                )

                established_before = {
                    symbol
                    for symbol, entry in establishment.items()
                    if entry.get("established")
                    and entry.get("establishing_record")
                    and date.fromisoformat(entry["establishing_record"]["date"][:10]) < cutoff
                }
                forecaster = Forecaster(run_id, trajectory_dir=trajectory_dir)
                forecast = forecaster.run(
                    belief, established_before_cutoff=established_before
                )

            adversary = Adversary(run_id, trajectory_dir=trajectory_dir)
            traps = adversary.run(
                store, slice_store, establishment=establishment, cutoff=cutoff
            )

            alias_check = _check_alias_resolution(slice_store, traps)
            prov = provenance.merge(
                provenance.check_forecast(forecast, store),
                provenance.check_axioms(axioms, store),
                provenance.check_traps(traps, store),
            )

            grader = Grader(run_id, trajectory_dir=trajectory_dir)
            card = grader.run(
                forecast,
                traps,
                establishment=establishment,
                cutoff=cutoff,
                provenance_check=prov.as_grader_input(),
                alias_check=alias_check,
            )
            if spec.no_graph:
                card.notes.append(
                    "No-graph baseline: publication counts only. Refusal, cost lens and "
                    "calibration are not meaningful for this row and are reported as "
                    "whatever the flat ranking produces."
                )
            if spec.flat_confidence:
                card.notes.append(
                    "Flat-confidence ablation: every claim holds the 0.05 prior, so "
                    "nothing clears the refusal threshold and the forecast is empty by "
                    "construction."
                )

            result = SliceResult(
                cutoff=cutoff.isoformat(),
                run_id=run_id,
                ablation=spec.name,
                scorecard=card,
                forecast=forecast,
                axiom_count=len(axioms.axioms),
                claim_count=len(belief.claims),
                revision_count=belief.revision_count,
                trap_count=len(traps.traps),
                provenance_report=prov,
                slice_manifest=slice_store.manifest(),
            )
            if write_results:
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                out = RESULTS_DIR / f"{run_id}.json"
                out.write_text(
                    json.dumps(result.model_dump(), indent=2, sort_keys=True, default=str)
                )
            return result
        finally:
            slice_store.close()
    finally:
        store.close()


def _check_alias_resolution(slice_store: Any, traps: TrapSet) -> dict[str, int]:
    """Run the adversary's alias probes against the graph.

    This is the paraphrase attack scored: each probe is an older symbol or an
    informal name, and the graph must resolve it to the same gene node.
    """
    resolved = 0
    for attack in traps.alias_attacks:
        node = slice_store.gene_by_symbol(attack.probe)
        if node is not None and node.id == attack.expected_gene_id:
            resolved += 1
    return {"total": len(traps.alias_attacks), "resolved": resolved}


SNAPSHOT_DIR = ROOT / "data" / "snapshot"


def build_graph(
    raw_dir: Path | str, store_path: Path | str = DEFAULT_DB, *, run_id: str = "build"
) -> IngestionReport:
    """Normalize the raw payloads straight into a graph. Needs the raw payloads."""
    path = Path(store_path)
    if path.exists():
        path.unlink()
    store = Store(path)
    try:
        return Curator(run_id, Path(raw_dir)).run(store)
    finally:
        store.close()


def build_snapshot(
    raw_dir: Path | str = ROOT / "data" / "raw",
    snapshot_dir: Path | str = SNAPSHOT_DIR,
    *,
    run_id: str = "snapshot",
) -> dict[str, Any]:
    """Normalize the raw payloads and write the committed snapshot.

    This is the step that turns fetched payloads into what ships. It refuses to
    write a row carrying article text, so a licensing mistake fails the build
    rather than reaching the repository.
    """
    from hindcast.ingest.licenses import EXCLUDED_SOURCES, SOURCES
    from hindcast.snapshot import write_snapshot

    curator = Curator(run_id, Path(raw_dir))
    result = curator.normalize()
    manifest = write_snapshot(
        Path(snapshot_dir),
        nodes=result.nodes,
        edges=result.edges,
        exclusions=result.exclusions,
        sources={
            key: {
                "name": spec.name,
                "license": spec.license,
                "institution": spec.institution,
                "url": spec.url,
                "attribution": spec.attribution,
                "attribution_required": spec.attribution_required,
                "note": spec.note,
            }
            for key, spec in SOURCES.items()
        },
        notes=[
            "Identifiers, structured metadata and numeric measurements only. No "
            "abstracts and no full text: per-article licenses vary and many do not "
            "permit redistribution.",
            *[f"Excluded source: {k}. {v}" for k, v in EXCLUDED_SOURCES.items()],
        ],
    )
    payload = manifest.model_dump()
    payload["available_by_source"] = dict(sorted(result.available_by_source.items()))
    return payload


def load_snapshot(
    snapshot_dir: Path | str = SNAPSHOT_DIR, store_path: Path | str = DEFAULT_DB
) -> IngestionReport:
    """Build the graph from the committed snapshot. No network, no raw payloads."""
    from hindcast.agents.curator import _build_report
    from hindcast.ingest.sources import IngestResult
    from hindcast.snapshot import read_snapshot, verify_snapshot

    snapshot_dir = Path(snapshot_dir)
    problems = verify_snapshot(snapshot_dir)
    if problems:
        raise RuntimeError("committed snapshot failed verification:\n  " + "\n  ".join(problems))
    nodes, edges, exclusions = read_snapshot(snapshot_dir)
    path = Path(store_path)
    if path.exists():
        path.unlink()
    store = Store(path)
    try:
        store.add_nodes(nodes)
        store.add_edges(edges)
        store.add_exclusions(exclusions)
        result = IngestResult(nodes=nodes, edges=edges, exclusions=exclusions)
        manifest_path = snapshot_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            result.available_by_source = manifest.get("available_by_source", {})
            result.available = sum(result.available_by_source.values())
        return _build_report(result)
    finally:
        store.close()


def run_heldout(
    cutoff: date,
    *,
    store_path: Path | str = DEFAULT_DB,
    max_genes: int = 12,
    write_results: bool = True,
) -> Any:
    """Run the held-out prediction evaluation for one slice."""
    from hindcast.heldout import HeldOutEvaluator

    store = Store(store_path)
    try:
        report = HeldOutEvaluator(f"{cutoff.isoformat()}_heldout").run(
            store, cutoff, max_genes=max_genes
        )
        if write_results:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            (RESULTS_DIR / f"heldout_{cutoff.isoformat()}.json").write_text(
                json.dumps(report.model_dump(), indent=2, sort_keys=True, default=str)
            )
        return report
    finally:
        store.close()


def run_all_slices(
    *,
    store_path: Path | str = DEFAULT_DB,
    ablations: tuple[AblationSpec, ...] = ABLATIONS,
    slices: tuple[date, ...] = ALL_SLICES,
) -> list[SliceResult]:
    out: list[SliceResult] = []
    for cutoff in slices:
        for spec in ablations:
            out.append(run_slice(cutoff, store_path=store_path, ablation=spec))
    return out
