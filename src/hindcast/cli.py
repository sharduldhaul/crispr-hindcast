"""Command line interface.

    hindcast build                  build the graph from the committed snapshot
    hindcast slice --cutoff DATE    run one evaluation slice
    hindcast run-all                run every slice and every ablation
    hindcast scorecard              render the scorecard table from results
    hindcast verify                 run the checks that must pass to ship
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hindcast.pipeline import (
    ABLATIONS,
    DEFAULT_DB,
    RESULTS_DIR,
    SNAPSHOT_DIR,
    build_graph,
    build_snapshot,
    load_snapshot,
    run_all_slices,
    run_slice,
)
from hindcast.scope import ALL_SLICES, PRIMARY_SLICE

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

ROOT = Path(__file__).resolve().parents[2]


@app.command()
def build(
    raw_dir: Path = typer.Option(ROOT / "data" / "raw", help="Raw payload directory."),
    snapshot: Path = typer.Option(
        ROOT / "data" / "snapshot", help="Committed snapshot directory."
    ),
    db: Path = typer.Option(DEFAULT_DB, help="Graph database to write."),
    from_snapshot: bool = typer.Option(
        True, help="Build from the committed snapshot rather than raw payloads."
    ),
) -> None:
    """Build the graph. Uses the committed snapshot by default, so it works offline.

    The two paths are not interchangeable. `--from-snapshot` reads the committed
    rows and needs no network and no raw payloads, which is the path a clone
    takes. `--no-from-snapshot` re-normalizes the fetched payloads, which is the
    path used after a re-fetch, and it needs data/raw to be populated.
    """
    if from_snapshot:
        report = load_snapshot(snapshot, db)
        console.print(f"built from the committed snapshot at {snapshot}")
    else:
        report = build_graph(raw_dir, db)
        console.print(f"built by re-normalizing the raw payloads at {raw_dir}")
    console.print(f"[bold]nodes[/bold] {report.nodes_loaded}  [bold]edges[/bold] {report.edges_loaded}")
    console.print(f"[bold]excluded[/bold] {report.excluded}  [bold]spurious[/bold] {report.spurious}")
    table = Table("source", "available", "loaded")
    for key, n in report.available_by_source.items():
        table.add_row(key, str(n), str(report.nodes_by_source.get(key.split(".")[0], 0)))
    console.print(table)


@app.command()
def slice(
    cutoff: str = typer.Option(PRIMARY_SLICE.isoformat(), help="Evaluation cutoff, YYYY-MM-DD."),
    db: Path = typer.Option(DEFAULT_DB),
    ablation: str = typer.Option("full system", help="Ablation row name."),
) -> None:
    """Run one evaluation slice."""
    spec = next((a for a in ABLATIONS if a.name == ablation), None)
    if spec is None:
        raise typer.BadParameter(f"unknown ablation {ablation!r}; one of {[a.name for a in ABLATIONS]}")
    result = run_slice(date.fromisoformat(cutoff), store_path=db, ablation=spec)
    card = result.scorecard
    console.print(f"\n[bold]slice {result.cutoff}[/bold]  ablation: {result.ablation}")
    console.print(f"ground truth: {', '.join(card.ground_truth_symbols) or 'none'}")
    console.print(
        f"forecast {card.forecast_size} items, {card.refusal_count} refusals, "
        f"{result.axiom_count} axioms, {result.revision_count} revisions"
    )
    if card.ranking_by_confidence:
        r = card.ranking_by_confidence
        console.print(
            f"by confidence: P@5 {r.precision_at_5:.2f}  P@10 {r.precision_at_10:.2f}  "
            f"MRR {r.mean_reciprocal_rank:.3f}  hits {r.hits_at_10}"
        )
    if card.ranking_by_cost_impact:
        r = card.ranking_by_cost_impact
        console.print(
            f"by cost impact: P@5 {r.precision_at_5:.2f}  P@10 {r.precision_at_10:.2f}  "
            f"MRR {r.mean_reciprocal_rank:.3f}  hits {r.hits_at_10}"
        )
    console.print(f"traps {card.traps_passed}/{card.traps_total}  refusals correct {card.refusal_correct}/{card.refusal_total}")
    console.print(f"ECE {card.expected_calibration_error}  untraceable numbers {card.fabricated_numbers}")


@app.command("run-all")
def run_all(db: Path = typer.Option(DEFAULT_DB)) -> None:
    """Run every slice and every ablation, and write results."""
    results = run_all_slices(store_path=db)
    console.print(f"{len(results)} runs written to {RESULTS_DIR}")
    scorecard()


@app.command()
def scorecard() -> None:
    """Render the scorecard table from the written results."""
    files = sorted(RESULTS_DIR.glob("*.json"))
    if not files:
        console.print("no results; run `hindcast run-all` first")
        raise typer.Exit(1)
    table = Table("slice", "ablation", "P@5 conf", "P@5 cost", "MRR", "traps", "refusals", "ECE", "fabricated")
    for path in files:
        data = json.loads(path.read_text())
        card = data["scorecard"]
        conf = card.get("ranking_by_confidence") or {}
        cost = card.get("ranking_by_cost_impact") or {}
        table.add_row(
            card["cutoff"],
            data["ablation"],
            f"{conf.get('precision_at_5', 0):.2f}",
            f"{cost.get('precision_at_5', 0):.2f}",
            f"{conf.get('mean_reciprocal_rank', 0):.3f}",
            f"{card['traps_passed']}/{card['traps_total']}",
            f"{card['refusal_correct']}/{card['refusal_total']}",
            f"{card.get('expected_calibration_error')}",
            str(card["fabricated_numbers"]),
        )
    console.print(table)


@app.command("build-snapshot")
def build_snapshot_cmd(
    raw_dir: Path = typer.Option(ROOT / "data" / "raw"),
    snapshot: Path = typer.Option(SNAPSHOT_DIR),
) -> None:
    """Normalize the raw payloads into the committed snapshot."""
    manifest = build_snapshot(raw_dir, snapshot)
    console.print(f"snapshot written to {snapshot}")
    table = Table("file", "bytes", "sha256")
    for name, meta in manifest["files"].items():
        table.add_row(name, f"{meta['bytes']:,}", meta["sha256"][:16] + "...")
    console.print(table)
    console.print(f"counts: {manifest['counts']}")


@app.command()
def verify(db: Path = typer.Option(DEFAULT_DB)) -> None:
    """Run the checks that must pass before this repository ships."""
    import subprocess

    console.print("[bold]running the test suite[/bold]")
    proc = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), "-m", "pytest", "-q"], cwd=ROOT
    )
    raise typer.Exit(proc.returncode)


if __name__ == "__main__":
    app()
