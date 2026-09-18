"""Freeze the rule book and every stated policy, before the first evaluation run.

What gets frozen. The answer key, meaning each gene's establishment date and the
record it came from. The method signature coefficients. The belief revision
constants. The refusal thresholds. The cost lens weights.

Why it is a separate step. All of these are policies that could be tuned against
the answers, and the only credible evidence that they were not is that they were
committed before any evaluation ran. This script writes them to eval/rulebook/
and prints the git tag command. The commit timestamp is the proof.

Run it, commit, tag, and only then run the evaluation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hindcast.agents.axioms import (  # noqa: E402
    COMPOSITION_DISCOUNT,
    GWAS_SIGNIFICANCE,
    PAN_ESSENTIAL_FRACTION,
)
from hindcast.agents.belief_reviser import (  # noqa: E402
    ESSENTIALITY_CEILING,
    EVIDENCE_STRENGTH,
    LITERATURE_SCALE,
    MIN_COMPOSITION_WEIGHT,
    MIN_HBF_PUBLICATIONS,
    MIN_SUPPORTING_WEIGHT,
    PRIOR_CONFIDENCE,
    REFUSAL_CONFIDENCE_THRESHOLD,
)
from hindcast.ingest.sources import COMPLEX_GROUP_SUFFIX  # noqa: E402
from hindcast.textmatch import MIN_ALIAS_LENGTH, SHORT_ALIASES  # noqa: E402
from hindcast.agents.method_signature import coefficient_manifest  # noqa: E402
from hindcast.cost import COST_WEIGHTS, PRICE_ANCHORS  # noqa: E402
from hindcast.scope import (  # noqa: E402
    ALL_SCOPE_GENES,
    ALL_SLICES,
    INFORMAL_NAMES,
    PHENOTYPE_FAMILIES,
)

RULEBOOK = ROOT / "eval" / "rulebook"
TAG = "rulebook-frozen-v1"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> None:
    RULEBOOK.mkdir(parents=True, exist_ok=True)
    answer_key = RULEBOOK / "gene_establishment.json"
    if not answer_key.exists():
        raise SystemExit(
            f"{answer_key} is missing. Run scripts/build_rulebook.py first."
        )

    policy = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "note": (
            "Every number in this file is a stated policy, not a measurement and "
            "not a fitted value. It was committed before the first evaluation run "
            "and tagged, so the commit timestamp is the evidence it was not tuned "
            "against the answer key. The reasoning for each value is in "
            "METHODOLOGY.md."
        ),
        "method_signature": coefficient_manifest(),
        "belief_revision": {
            "prior_confidence": PRIOR_CONFIDENCE,
            "evidence_strength_log_odds_per_unit_weight": EVIDENCE_STRENGTH,
            "update_rule": "log-odds accumulation, order independent",
            "contradiction": "subtracts; does not zero a claim",
            "supersession": "does not subtract; the earlier claim was coarse, not wrong",
            "literature_scale": LITERATURE_SCALE,
            "literature_accumulation": (
                "logarithmic: the k-th publication contributes ln(1+k) - ln(k), so n "
                "publications total LITERATURE_SCALE * ln(1+n). Publications are "
                "correlated observations of one literature, not independent "
                "experiments."
            ),
            "essentiality_ceiling": ESSENTIALITY_CEILING,
            "essentiality_accumulation": (
                "harmonic increments normalised to ESSENTIALITY_CEILING times the "
                "fitness hit fraction, so a gene measured in 26,171 correlated "
                "screens cannot be driven to zero confidence."
            ),
            "composition_discount": COMPOSITION_DISCOUNT,
        },
        "refusal": {
            "confidence_threshold": REFUSAL_CONFIDENCE_THRESHOLD,
            "min_supporting_weight": MIN_SUPPORTING_WEIGHT,
            "min_hbf_publications": MIN_HBF_PUBLICATIONS,
            "min_composition_weight": MIN_COMPOSITION_WEIGHT,
            "rationale": (
                "A confidence above the threshold is necessary but not sufficient. "
                "The claim must also have evidence of substance by one of three "
                "routes: a measurement at or above the weight floor, at least "
                "MIN_HBF_PUBLICATIONS HbF-specific publications, or a "
                "complex-composition step at or above its own floor. The floors are "
                "what stop a pile of co-mentions carrying a claim over the line, and "
                "they count different kinds of evidence so that they stay distinct."
            ),
        },
        "evidence_admission": {
            "gene_named_by": "title_names_gene",
            "rationale": (
                "A publication supports a gene only if its title names the gene. The "
                "Europe PMC query searches full text, so retrieval tags a record with "
                "every scope gene whose name or alias appears anywhere in the article."
            ),
            "min_alias_length": MIN_ALIAS_LENGTH,
            "short_alias_allowlist": {k: list(v) for k, v in SHORT_ALIASES.items()},
            "acts_through_basis": (
                f"HGNC gene groups whose name ends {COMPLEX_GROUP_SUFFIX!r}"
            ),
            "acts_through_excluded": (
                "Structural domain groups such as 'Zinc fingers C2H2-type' and 'BTB "
                "domain containing'. Sharing a domain is not sharing a mechanism."
            ),
        },
        "thresholds": {
            "gwas_significance": GWAS_SIGNIFICANCE,
            "pan_essential_fraction": PAN_ESSENTIAL_FRACTION,
        },
        "cost_lens": {
            "weights": {str(k): v for k, v in COST_WEIGHTS.items()},
            "price_anchors": {
                k: {kk: (str(vv) if hasattr(vv, "value") else vv) for kk, vv in v.items()}
                for k, v in PRICE_ANCHORS.items()
            },
        },
        "scope": {
            "genes": list(ALL_SCOPE_GENES),
            "phenotype_families": PHENOTYPE_FAMILIES,
            "informal_names": {k: list(v) for k, v in INFORMAL_NAMES.items()},
            "slices": [d.isoformat() for d in ALL_SLICES],
        },
    }
    policy_path = RULEBOOK / "policy.json"
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True))

    answer_key_text = answer_key.read_text()
    checksums = {
        "gene_establishment.json": sha256_text(answer_key_text),
        "policy.json": sha256_text(policy_path.read_text()),
    }
    adjudications = RULEBOOK / "adjudications.json"
    if adjudications.exists():
        checksums["adjudications.json"] = sha256_text(adjudications.read_text())
    (RULEBOOK / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True))

    key = json.loads(answer_key_text)
    established = {
        s: e["establishing_record"]["date"][:10]
        for s, e in key.items()
        if e.get("established") and e.get("establishing_record")
    }
    print(f"answer key: {len(key)} genes, {len(established)} with an establishing record")
    for cutoff in ALL_SLICES:
        n = sum(1 for d in established.values() if d >= cutoff.isoformat())
        print(f"  ground truth at {cutoff}: {n} genes established on or after the cutoff")
    print(f"\nwrote {policy_path.relative_to(ROOT)} and checksums.json")
    print("\nNow commit and tag, before running any evaluation:")
    print(f"  git add eval/rulebook && git commit -m 'Freeze the rule book' && git tag {TAG}")

    try:
        out = subprocess.run(
            ["git", "tag", "--list", TAG], cwd=ROOT, capture_output=True, text=True
        )
        if out.stdout.strip():
            print(f"\nNote: tag {TAG} already exists. The rule book is already frozen.")
    except OSError:
        pass


if __name__ == "__main__":
    main()
