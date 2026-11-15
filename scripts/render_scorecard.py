"""Render the scorecard from eval/results/.

Writes every table to eval/scorecard.md, headline first, and copies the
headline alone into the README between its markers, so a number in the README
cannot drift from the result files.

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

#: The README holds the headline between these two lines.
README_START = "<!-- SCORECARD:START -->"
README_END = "<!-- SCORECARD:END -->"


def fmt(value: object, places: int = 3) -> str:
    if value is None:
        return "not run"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def with_interval(score: dict, field: str, places: int) -> str:
    """A metric with its bootstrap interval: `0.20 [0.00, 0.60]`."""
    if field not in score:
        return "not run"
    interval = score[f"{field}_interval"]
    return (
        f"{score[field]:.{places}f} "
        f"[{interval['lower']:.{places}f}, {interval['upper']:.{places}f}]"
    )


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


def load_llm() -> list[dict]:
    """Language-model rows, written by `hindcast run-all` whether or not they ran."""
    return [json.loads(p.read_text()) for p in sorted((RESULTS / "llm").glob("*.json"))]


def rate(value: dict, empty: str) -> str:
    """A rate with its counts: `0.20 (1 of 5)`. `empty` stands in when nothing was counted."""
    if value["denominator"] == 0:
        return empty
    return (
        f"{value['numerator'] / value['denominator']:.2f} "
        f"({value['numerator']} of {value['denominator']})"
    )


def comparison_cells(card: dict) -> list[str]:
    """The columns every row of the comparison shares, from a scorecard."""
    conf = card["ranking_by_confidence"]
    accuracy = card["refusal_accuracy"]
    refusals = f"{card['refusal_correct']}/{card['refusal_total']}"
    return [
        with_interval(conf, "precision_at_5", 2),
        with_interval(conf, "mean_reciprocal_rank", 3),
        f"{card['traps_passed']}/{card['traps_total']}",
        refusals if accuracy is None else f"{refusals} ({accuracy:.2f})",
        fmt(card["expected_calibration_error"]),
    ]


#: The model rows of the comparison, in the order they are printed.
LLM_CONDITIONS = {
    "none": "model alone",
    "text": "model with text retrieval",
    "graph": "model with graph tools",
}

#: The rule-based rows of the comparison: the ablation name and its label.
RULE_BASED_ROWS = {
    "full system": "rule-based system",
    "no graph": "flat literature baseline",
}


def headline(results: list[dict], llm: list[dict]) -> list[str]:
    """The four forecasters at each cutoff, on the four columns that carry the result."""
    lines = [
        "### Headline\n",
        "| Cutoff | Forecaster | P@5 [95% interval] | Traps passed | Grounded claims | Recalled claims |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    by_ablation = {(r["cutoff"], r["ablation"]): r for r in results}
    by_condition = {(r["cutoff"], r["run"]["condition"]): r for r in llm}
    for cutoff in sorted({r["cutoff"] for r in llm}):
        card = by_ablation[cutoff, "full system"]["scorecard"]
        cells = comparison_cells(card)
        lines.append(f"| {cutoff} | rule-based system | {cells[0]} | {cells[2]} | n/a | n/a |")
        for condition, label in LLM_CONDITIONS.items():
            row = by_condition[cutoff, condition]
            status = row["run"]["status"]
            if status != "ran":
                rest = " | ".join([status.replace("_", " ")] * 4)
            else:
                cells = comparison_cells(row["scorecard"])
                grounded = row["grounding"]["grounded_claim_rate"]
                recalled = row["memorization"]["recalled_rate"]
                rest = " | ".join(
                    [
                        cells[0],
                        cells[2],
                        f"{grounded['numerator']} of {grounded['denominator']}",
                        f"{recalled['numerator']} of {recalled['denominator']}",
                    ]
                )
            lines.append(f"| {cutoff} | {label} | {rest} |")
    lines.append("")
    for term, definition in HEADLINE_DEFINITIONS:
        lines.append(f"- **{term}**: {definition}")
    return lines


#: The headline's columns in one line each. The comparison table defines the rest.
HEADLINE_DEFINITIONS = (
    ("P@5", "of the 5 highest-confidence claims, the share the field later established."),
    ("Traps passed", "trap questions answered correctly, over all traps at that cutoff."),
    ("Grounded claims", "claims that cite a row the model was given that names the gene."),
    (
        "Recalled claims",
        (
            "claims for a gene established after the cutoff that cite no such row: "
            "the answer came from training, not from the evidence."
        ),
    ),
)


def write_readme_headline(lines: list[str]) -> None:
    """Replace what the README holds between its markers with the headline."""
    path = ROOT / "README.md"
    readme = path.read_text()
    if README_START not in readme or README_END not in readme:
        raise SystemExit(f"README is missing the {README_START} / {README_END} markers")
    head, rest = readme.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    body = "\n".join(lines).strip()
    path.write_text(f"{head}{README_START}\n\n{body}\n\n{README_END}{tail}")


def comparison(results: list[dict], llm: list[dict]) -> list[str]:
    lines = ["\n### Rule-based system and language model, every metric\n"]
    header = [
        "Slice",
        "System",
        "P@5 [95% interval]",
        "MRR [95% interval]",
        "Traps passed",
        "Refusal acc",
        "ECE",
        "Grounded-claim rate [95% interval]",
        "Fabricated IDs",
        "Recalled claims",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + " --- |" * len(header))
    by_ablation = {(r["cutoff"], r["ablation"]): r for r in results}
    by_condition = {(r["cutoff"], r["run"]["condition"]): r for r in llm}
    for cutoff in sorted({r["cutoff"] for r in llm}):
        for ablation, label in RULE_BASED_ROWS.items():
            cells = comparison_cells(by_ablation[cutoff, ablation]["scorecard"])
            lines.append("| " + " | ".join([cutoff, label, *cells, "n/a", "n/a", "n/a"]) + " |")
        for condition, label in LLM_CONDITIONS.items():
            row = by_condition[cutoff, condition]
            status = row["run"]["status"]
            if status != "ran":
                cells = [status.replace("_", " ")] * (len(header) - 2)
            else:
                grounding = row["grounding"]
                interval = grounding["grounded_claim_rate_interval"]
                grounded = rate(grounding["grounded_claim_rate"], "no claims")
                if grounding["grounded_claim_rate"]["denominator"]:
                    grounded += f" [{interval['lower']:.2f}, {interval['upper']:.2f}]"
                recalled = row["memorization"]["recalled_rate"]
                cells = [
                    *comparison_cells(row["scorecard"]),
                    grounded,
                    str(len(grounding["fabricated_ids"])),
                    f"{recalled['numerator']} of {recalled['denominator']}",
                ]
            lines.append("| " + " | ".join([cutoff, label, *cells]) + " |")

    models = sorted({r["run"]["model_id"] for r in llm})
    not_run = sum(r["run"]["status"] == "not_run" for r in llm)
    lines.append("")
    lines.append(f"Model: {', '.join(f'`{m}`' for m in models)}.")
    if not_run:
        lines.append(
            f"Not run: {not_run} of {len(llm)} model rows have no response in "
            "`eval/model_cache/`. They are reported as not run, never estimated."
        )
    lines.append("")
    lines.append("| Column | Definition |")
    lines.append("| --- | --- |")
    for column, definition in COMPARISON_DEFINITIONS:
        lines.append(f"| {column} | {definition} |")
    return lines


#: One line per column of the comparison. METHODOLOGY.md holds the full definitions.
COMPARISON_DEFINITIONS = (
    (
        "P@5",
        "Precision at 5: genes later established among the 5 highest-confidence claims, over 5.",
    ),
    ("MRR", "Reciprocal rank of the first established gene in the ranking."),
    ("Traps passed", "Traps answered correctly, over all traps for the slice."),
    ("Refusal acc", "Genes refused, over the genes the slice holds too little evidence to answer."),
    ("ECE", "Expected calibration error over five confidence bins."),
    (
        "Grounded-claim rate",
        (
            "Claims citing at least one row the model was given that names the claimed gene, "
            "over all claims. A lower bar than the faithfulness metrics of RAG evaluation: "
            "it does not test that the row supports the claim."
        ),
    ),
    ("Fabricated IDs", "Cited IDs that no store holds."),
    (
        "Recalled claims",
        (
            "Claims for a gene established on or after the cutoff that are not grounded, "
            "over all claims for such genes."
        ),
    ),
    ("n/a", "The rule-based rows cite no IDs, so the column does not apply."),
)


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

    llm = load_llm()
    if llm:
        top = headline(results, llm)
        write_readme_headline(top)
        lines.extend(top)
        lines.append("")

    lines.append("### Rule-based system, every metric\n")
    lines.append(
        "| Slice | Ground truth | Forecast | Refusals | P@5 conf [95% interval] | P@5 cost | P@10 conf | MRR [95% interval] | Judgement traps | Contamination traps | Refusal acc | ECE | Fabricated |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in full:
        c = r["scorecard"]
        conf = c.get("ranking_by_confidence") or {}
        cost = c.get("ranking_by_cost_impact") or {}
        acc = c.get("refusal_accuracy")
        lines.append(
            f"| {c['cutoff']} | {len(c['ground_truth_symbols'])} | {c['forecast_size']} | "
            f"{c['refusal_count']} | {with_interval(conf, 'precision_at_5', 2)} | "
            f"{fmt(cost.get('precision_at_5'), 2)} | {fmt(conf.get('precision_at_10'), 2)} | "
            f"{with_interval(conf, 'mean_reciprocal_rank', 3)} | "
            f"{c.get('judgement_traps_passed', 0)}/{c.get('judgement_traps_total', 0)} | "
            f"{c.get('contamination_traps_passed', 0)}/{c.get('contamination_traps_total', 0)} | "
            f"{c['refusal_correct']}/{c['refusal_total']}"
            + (f" ({fmt(acc, 2)})" if acc is not None else "")
            + f" | {fmt(c.get('expected_calibration_error'))} | {c['fabricated_numbers']} |"
        )

    if llm:
        lines.extend(comparison(results, llm))

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
        lines.append("| Slice | Genes tested | Recovered | Rate | Mean confidence drop |")
        lines.append("| --- | --- | --- | --- | --- |")
        for h in sorted(heldout, key=lambda x: x["cutoff"]):
            lines.append(
                f"| {h['cutoff']} | {h.get('genes_tested', 0)} | "
                f"{h.get('recovered', 0)} | {fmt(h.get('recovery_rate'), 2)} | "
                f"{fmt(h.get('mean_confidence_drop'))} |"
            )

    ingestion_path = RESULTS / "ingestion.json"
    if ingestion_path.exists():
        ing = json.loads(ingestion_path.read_text())
        considered = sum(ing["available_by_source"].values())
        lines.append("\n### Ingestion\n")
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
        for reason, n in sorted(ing["exclusions_by_reason"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {reason} | {n:,} |")

    text = "\n".join(lines)
    out = ROOT / "eval" / "scorecard.md"
    out.write_text(text + "\n")
    print(text)
    print(f"\nwritten to {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
