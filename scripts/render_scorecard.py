"""Render the scorecard from eval/results/ as the markdown the README leads with.

Reads only committed result files. Prints bad numbers with the same prominence
as good ones, because a middling figure left in place is worth more than a clean
sheet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"


def fmt(value: object, places: int = 3) -> str:
    if value is None:
        return "not run"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def load() -> list[dict]:
    """Slice results only.

    `hindcast heldout` writes its reports into the same directory with a
    different shape, so the glob is filtered on the file name rather than on
    what happens to parse.
    """
    out = []
    for path in sorted(RESULTS.glob("*.json")):
        payload = json.loads(path.read_text())
        # A slice result is the only thing that carries an ablation name. The
        # held-out reports and the ingestion report live in the same directory.
        if "ablation" not in payload:
            continue
        out.append(payload)
    return out


def load_heldout() -> list[dict]:
    out = []
    for path in sorted(RESULTS.glob("heldout_*.json")):
        out.append(json.loads(path.read_text()))
    return out


def main() -> None:
    results = load()
    if not results:
        raise SystemExit("no results in eval/results; run `hindcast run-all` first")

    full = [r for r in results if r["ablation"] == "full system"]
    full.sort(key=lambda r: r["cutoff"])

    lines: list[str] = []

    ingestion_path = RESULTS / "ingestion.json"
    if ingestion_path.exists():
        ing = json.loads(ingestion_path.read_text())
        considered = sum(ing["available_by_source"].values())
        lines.append("### Ingestion\n")
        lines.append("| Measure | Value |")
        lines.append("| --- | --- |")
        lines.append(f"| Source records considered | {considered:,} |")
        lines.append(f"| Nodes loaded | {ing['nodes_loaded']:,} |")
        lines.append(f"| Edges loaded | {ing['edges_loaded']:,} |")
        lines.append(f"| Excluded, with a recorded reason | {ing['excluded']:,} |")
        lines.append(f"| Spurious records created | {ing['spurious']} |")
        lines.append("")
        lines.append("Exclusions by reason:\n")
        lines.append("| Reason | Records |")
        lines.append("| --- | --- |")
        for reason, n in sorted(
            ing["exclusions_by_reason"].items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| {reason} | {n:,} |")
        lines.append("")

    lines.append("### Scorecard, full system\n")
    lines.append(
        "| Slice | Ground truth | Forecast | Refusals | P@5 conf | P@5 cost | P@10 conf | MRR | Judgement traps | Contamination traps | Refusal acc | ECE | Fabricated |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    for r in full:
        c = r["scorecard"]
        conf = c.get("ranking_by_confidence") or {}
        cost = c.get("ranking_by_cost_impact") or {}
        acc = c.get("refusal_accuracy")
        lines.append(
            f"| {c['cutoff']} | {len(c['ground_truth_symbols'])} | {c['forecast_size']} | "
            f"{c['refusal_count']} | {fmt(conf.get('precision_at_5'), 2)} | "
            f"{fmt(cost.get('precision_at_5'), 2)} | {fmt(conf.get('precision_at_10'), 2)} | "
            f"{fmt(conf.get('mean_reciprocal_rank'))} | "
            f"{c.get('judgement_traps_passed', 0)}/{c.get('judgement_traps_total', 0)} | "
            f"{c.get('contamination_traps_passed', 0)}/{c.get('contamination_traps_total', 0)} | "
            f"{c['refusal_correct']}/{c['refusal_total']}"
            + (f" ({fmt(acc, 2)})" if acc is not None else "")
            + f" | {fmt(c.get('expected_calibration_error'))} | {c['fabricated_numbers']} |"
        )

    lines.append("\n### Ablations, primary slice\n")
    primary = sorted(
        [r for r in results if r["cutoff"] == "2017-12-31"],
        key=lambda r: r["ablation"] != "full system",
    )
    lines.append(
        "| Ablation | Forecast | Refusals | P@5 conf | P@10 conf | MRR | Judgement traps | ECE |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in primary:
        c = r["scorecard"]
        conf = c.get("ranking_by_confidence") or {}
        lines.append(
            f"| {r['ablation']} | {c['forecast_size']} | {c['refusal_count']} | "
            f"{fmt(conf.get('precision_at_5'), 2)} | {fmt(conf.get('precision_at_10'), 2)} | "
            f"{fmt(conf.get('mean_reciprocal_rank'))} | "
            f"{c.get('judgement_traps_passed', 0)}/{c.get('judgement_traps_total', 0)} | "
            f"{fmt(c.get('expected_calibration_error'))} |"
        )

    lines.append("\n### Traps, primary slice, named individually\n")
    for r in primary:
        if r["ablation"] != "full system":
            continue
        lines.append("| Trap | Kind | Correct answer | System answer | Result |")
        lines.append("| --- | --- | --- | --- | --- |")
        for t in r["scorecard"]["traps"]:
            mark = "pass" if t["passed"] else "**FAIL**"
            if t["passed"] and t.get("vacuous"):
                mark = "pass (vacuous)"
            if t["passed"] and t["kind"] == "postdates_cutoff":
                mark = "pass (contamination check)"
            lines.append(
                f"| {t['gene_symbol']} | {t['kind']} | {t['correct_answer']} | "
                f"{t['system_answer']} | {mark} |"
            )

    lines.append("\n### Reliability, primary slice, full system\n")
    for r in primary:
        if r["ablation"] != "full system":
            continue
        lines.append("| Confidence bin | Claims | Mean confidence | Observed frequency |")
        lines.append("| --- | --- | --- | --- |")
        for b in r["scorecard"]["calibration_bins"]:
            lines.append(
                f"| {b['lower']:.1f} to {b['upper']:.1f} | {b['n']} | "
                f"{fmt(b['mean_confidence'])} | {fmt(b['observed_frequency'])} |"
            )

    lines.append("\n### Cost lens, full system\n")
    lines.append(
        "| Slice | Forecast | Items reordered by cost weighting | "
        "Top by confidence | Top by cost impact | Surfaces a small molecule |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for r in full:
        c = r["scorecard"]
        lines.append(
            f"| {c['cutoff']} | {c['forecast_size']} | "
            f"{c.get('cost_lens_reordered', 0)} | "
            f"{c.get('cost_lens_top_route_by_confidence') or '--'} | "
            f"{c.get('cost_lens_top_route_by_cost_impact') or '--'} | "
            f"{'yes' if c.get('cost_lens_surfaces_small_molecule') else 'no'} |"
        )

    heldout = load_heldout()
    if heldout:
        lines.append("\n### Held-out recovery\n")
        lines.append(
            "| Slice | Genes tested | Recovered | Rate | Mean confidence drop |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for h in sorted(heldout, key=lambda x: x["cutoff"]):
            lines.append(
                f"| {h['cutoff']} | {h.get('genes_tested', 0)} | "
                f"{h.get('recovered', 0)} | {fmt(h.get('recovery_rate'), 2)} | "
                f"{fmt(h.get('mean_confidence_drop'))} |"
            )

    text = "\n".join(lines)
    out = ROOT / "eval" / "scorecard.md"
    out.write_text(text + "\n")
    print(text)
    print(f"\nwritten to {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
