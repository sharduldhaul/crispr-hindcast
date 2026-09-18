"""METHOD_SIGNATURE: how much one measurement is worth, from how it was made.

The contract is narrow and worth stating precisely. This module reads how a
measurement was produced and returns a weight. It never reads what the
measurement concluded. A screen that found nothing and a screen that found a
strong effect, run the same way in the same system, get the same weight. The
weight is about the evidence's standing, and the direction and size of the
effect are the belief reviser's business.

Every coefficient below is a stated policy with a reason. None of it is fitted
to anything. The values were chosen and frozen before the first evaluation run,
and the freeze is a git tag, so the commit timestamp is the evidence that they
were not tuned against the answers. See METHODOLOGY.md for the argument behind
each number and eval/rulebook/ for the frozen copy.

The five terms are the ones named in the brief: system, perturbation type,
readout directness, independent replication, and human genetic support. They
combine multiplicatively, because these are not independent contributions that
add up. A direct HbF protein readout in a cell line that cannot make adult
hemoglobin is not worth the sum of its parts, it is worth the product: a weak
system discounts everything measured in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# term 1: the system a measurement was made in
# --------------------------------------------------------------------------
#
# The largest term, and the one most often glossed over when screen results are
# compared. Primary human CD34+ cells differentiated down the erythroid pathway
# perform the fetal-to-adult switch that the disease is about. HUDEP-2 is an
# immortalized human erythroid progenitor line that does perform the switch, so
# it is close behind and far ahead of a leukemia line. K-562 is an
# erythroleukemia line that expresses fetal and embryonic globins and does not
# silence them, so a result showing "more HbF" in K-562 may be showing nothing
# about silencing at all. A mouse carries a different globin locus with a
# different switch, and the cases where mouse and human globin regulation
# disagree are the reason this term dominates.
#
# Human population sits above every cell system. A genetic association measured
# in people is measured in the only system that has to work.
SYSTEM_WEIGHTS: dict[str, float] = {
    "human_population": 1.00,
    "primary_human_hspc": 1.00,
    "human_erythroid_progenitor_line": 0.75,
    "human_cancer_line": 0.35,
    "human_immortalized_line": 0.30,
    "mouse_model": 0.30,
    "mouse_line": 0.20,
    "non_human_other": 0.10,
    "cell_free_or_unspecified": 0.10,
}

# --------------------------------------------------------------------------
# term 2: how the gene was perturbed
# --------------------------------------------------------------------------
#
# A defined allele is the strongest perturbation: a base edit or knock-in
# produces a known sequence change whose consequence can be reasoned about. A
# naturally occurring human variant is equally strong for a different reason,
# being the experiment nature already ran at population scale. CRISPRi
# represses transcription without cutting, so it avoids the indel heterogeneity
# and the DNA-damage response that confound knockouts, at the cost of being
# incomplete. A pooled knockout is the workhorse and is weighted as such.
# Overexpression is weakest: forcing a factor above its physiological range
# routinely produces effects that never occur at native levels, and the
# literature on globin regulation has several of those.
PERTURBATION_WEIGHTS: dict[str, float] = {
    "base_edit": 1.00,
    "knock_in": 1.00,
    "genetic_variant": 1.00,
    "crispri": 0.85,
    "crispra": 0.70,
    "knockout": 0.70,
    "rnai": 0.40,
    "overexpression": 0.30,
    "unspecified": 0.35,
}

# --------------------------------------------------------------------------
# term 3: how directly the readout measures what matters
# --------------------------------------------------------------------------
#
# The endpoint that matters clinically is hemoglobin F protein per red cell, and
# the distribution across cells, because a given mean HbF protects far better
# when spread evenly than when concentrated in a few F-cells. Protein and
# F-cell readouts are therefore the standard. Transcript is one step removed and
# the step is not free: gamma-globin mRNA and HbF protein come apart through
# translational control, which is exactly the mechanism the EIF2AK1 result turns
# on. A reporter or a sorted population is a proxy for a proxy.
DIRECTNESS_WEIGHTS: dict[str, float] = {
    "direct_protein": 1.00,
    "transcript": 0.65,
    "proxy": 0.35,
}

# --------------------------------------------------------------------------
# term 4: independent replication across distinct laboratories
# --------------------------------------------------------------------------
#
# Replication by the same group in the same system is close to free and is not
# counted. Replication by an unrelated group is the single most informative
# thing that can happen to a finding. The multiplier saturates, because the
# fourth independent replication adds less than the second, and it is capped so
# that no amount of replication can rescue a weak system.
REPLICATION_MULTIPLIER: dict[int, float] = {
    0: 1.00,
    1: 1.00,
    2: 1.35,
    3: 1.55,
}
REPLICATION_CAP = 1.70

# --------------------------------------------------------------------------
# term 5: human genetic support
# --------------------------------------------------------------------------
#
# Whether a gene has genome-wide significant genetic support for the trait in
# people. This is a property of the gene's evidence as a whole rather than of
# one measurement, and it is applied as a multiplier on measurements about that
# gene. The size of the bonus is deliberately smaller than the system term: a
# genetic association says a gene matters, not that a given cell-line experiment
# was well done.
#
# The penalty for a locus association whose causal gene is unresolved is the
# geometry problem in its statistical form. A GWAS peak names a region, and the
# author-reported gene at that region is an assignment, not a result. The
# olfactory receptor genes reported at the HBB locus in HbF studies are the
# standing example: strong association, no plausible function.
HUMAN_GENETIC_SUPPORT_BONUS = 1.30
NO_HUMAN_GENETIC_SUPPORT = 1.00
AUTHOR_REPORTED_GENE_PENALTY = 0.55

#: Floor and ceiling. A weight of zero would make a measurement unable to move
#: any belief, and nothing in this corpus is worth exactly nothing. The ceiling
#: keeps a single measurement from dominating an accumulation.
MIN_WEIGHT = 0.01
MAX_WEIGHT = 2.00

#: Assay-level standing, for sources whose rows are not experiments in the usual
#: sense. An Open Targets text-mined literature co-mention is a statement that
#: two terms appeared together, which is the weakest evidence in the corpus and
#: is weighted accordingly.
ASSAY_MODIFIERS: dict[str, float] = {
    "gwas_association": 1.00,
    "depmap_gene_effect": 1.00,
    "orcs_screen_score": 1.00,
    "opentargets_genetic_association": 1.00,
    "opentargets_genetic_literature": 0.80,
    "opentargets_clinical": 1.00,
    "opentargets_animal_model": 0.60,
    "opentargets_literature": 0.25,
    "literature_comention": 0.20,
}


class Weighting(BaseModel):
    """One measurement's weight, with every term that produced it."""

    model_config = ConfigDict(extra="forbid")

    measurement_id: str
    weight: float
    system_class: str
    system_weight: float
    perturbation_class: str
    perturbation_weight: float
    directness: str
    directness_weight: float
    replication_count: int
    replication_multiplier: float
    human_genetic_support: bool
    human_genetic_multiplier: float
    assay: str
    assay_modifier: float
    penalties: list[str] = Field(default_factory=list)

    def explain(self) -> str:
        parts = [
            f"system {self.system_class}={self.system_weight:.2f}",
            f"perturbation {self.perturbation_class}={self.perturbation_weight:.2f}",
            f"readout {self.directness}={self.directness_weight:.2f}",
            f"replication x{self.replication_multiplier:.2f} ({self.replication_count} labs)",
            f"human genetics x{self.human_genetic_multiplier:.2f}",
            f"assay {self.assay}x{self.assay_modifier:.2f}",
        ]
        if self.penalties:
            parts.append("penalties: " + ", ".join(self.penalties))
        return f"weight {self.weight:.4f} = " + " * ".join(parts)


@dataclass
class MethodSignature:
    """The weighting function. Stateless apart from the frozen coefficients."""

    replication_counts: dict[str, int] = field(default_factory=dict)
    human_genetic_support: set[str] = field(default_factory=set)

    def weight(
        self,
        *,
        measurement_id: str,
        assay: str,
        system_class: str,
        perturbation_class: str,
        directness: str,
        gene_id: str,
        gene_assignment: str | None = None,
    ) -> Weighting:
        sysw = SYSTEM_WEIGHTS.get(system_class, SYSTEM_WEIGHTS["cell_free_or_unspecified"])
        pertw = PERTURBATION_WEIGHTS.get(
            perturbation_class, PERTURBATION_WEIGHTS["unspecified"]
        )
        dirw = DIRECTNESS_WEIGHTS.get(directness, DIRECTNESS_WEIGHTS["proxy"])
        reps = self.replication_counts.get(gene_id, 0)
        repm = REPLICATION_MULTIPLIER.get(reps, REPLICATION_CAP)
        has_genetics = gene_id in self.human_genetic_support
        genm = HUMAN_GENETIC_SUPPORT_BONUS if has_genetics else NO_HUMAN_GENETIC_SUPPORT
        assaym = ASSAY_MODIFIERS.get(assay, 0.5)

        penalties: list[str] = []
        raw = sysw * pertw * dirw * repm * genm * assaym
        if gene_assignment == "author_reported":
            raw *= AUTHOR_REPORTED_GENE_PENALTY
            penalties.append(
                f"author-reported gene at an associated locus, not an established "
                f"causal gene (x{AUTHOR_REPORTED_GENE_PENALTY})"
            )

        return Weighting(
            measurement_id=measurement_id,
            weight=round(min(max(raw, MIN_WEIGHT), MAX_WEIGHT), 6),
            system_class=system_class,
            system_weight=sysw,
            perturbation_class=perturbation_class,
            perturbation_weight=pertw,
            directness=directness,
            directness_weight=dirw,
            replication_count=reps,
            replication_multiplier=repm,
            human_genetic_support=has_genetics,
            human_genetic_multiplier=genm,
            assay=assay,
            assay_modifier=assaym,
            penalties=penalties,
        )

    def weight_measurement(
        self, measurement_attrs: dict[str, Any], *, measurement_id: str, directness: str
    ) -> Weighting:
        """Weight a `Measurement` node's attributes directly."""
        return self.weight(
            measurement_id=measurement_id,
            assay=str(measurement_attrs.get("assay") or "unknown"),
            system_class=str(measurement_attrs.get("system_class") or "cell_free_or_unspecified"),
            perturbation_class=str(
                measurement_attrs.get("perturbation_class") or "unspecified"
            ),
            directness=directness,
            gene_id=str(measurement_attrs.get("gene_id") or ""),
            gene_assignment=measurement_attrs.get("gene_assignment"),
        )


def coefficient_manifest() -> dict[str, Any]:
    """Every coefficient, for the frozen rule book and the ablation harness."""
    return {
        "system_weights": dict(SYSTEM_WEIGHTS),
        "perturbation_weights": dict(PERTURBATION_WEIGHTS),
        "directness_weights": dict(DIRECTNESS_WEIGHTS),
        "replication_multiplier": {str(k): v for k, v in REPLICATION_MULTIPLIER.items()},
        "replication_cap": REPLICATION_CAP,
        "human_genetic_support_bonus": HUMAN_GENETIC_SUPPORT_BONUS,
        "author_reported_gene_penalty": AUTHOR_REPORTED_GENE_PENALTY,
        "assay_modifiers": dict(ASSAY_MODIFIERS),
        "min_weight": MIN_WEIGHT,
        "max_weight": MAX_WEIGHT,
        "combination": "multiplicative across all five terms, then clamped",
    }


#: The uniform-weight variant, for the "no method signature" ablation row.
class UniformSignature(MethodSignature):
    """Every measurement weighs the same. Used only by the ablation."""

    def weight(self, **kwargs: Any) -> Weighting:  # type: ignore[override]
        base = super().weight(**kwargs)
        return base.model_copy(
            update={
                "weight": 1.0,
                "system_weight": 1.0,
                "perturbation_weight": 1.0,
                "directness_weight": 1.0,
                "replication_multiplier": 1.0,
                "human_genetic_multiplier": 1.0,
                "assay_modifier": 1.0,
                "penalties": ["uniform weighting ablation: method signature disabled"],
            }
        )
