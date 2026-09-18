"""BELIEF_REVISER: maintain the belief map, one auditable update at a time.

Contract. In: a slice, and the axioms extracted from it. Out: a claim per
candidate gene with a confidence, and an immutable audit row for every update
that produced it.

No language model decides any numeric update. The rule is log-odds
accumulation with per-evidence-class weights from the method signature, which is
the form Bayesian updating takes when independent evidence is combined. It has
the three properties this problem needs: confidence cannot leave the unit
interval however much evidence arrives, the final value does not depend on the
order evidence was applied, and each audit row is arithmetic a reader can check.

See METHODOLOGY.md for the prior and the strength constant, and for why
contradiction subtracts while supersession does not.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.axioms import AxiomSet
from hindcast.agents.base import Agent
from hindcast.models import NodeType
from hindcast.store import SliceStore, Store

#: Every claim starts here. Low, and the same for every claim, because a
#: per-claim prior would be where knowledge of the answers could enter without
#: being visible.
PRIOR_CONFIDENCE = 0.05

#: Log-odds contributed by one unit of method-signature weight. Sets how fast
#: beliefs move, and determines calibration more than any other single number.
EVIDENCE_STRENGTH = 0.85

#: Confidence below which the system refuses rather than forecasts.
REFUSAL_CONFIDENCE_THRESHOLD = 0.25

#: A claim must have at least one supporting measurement this strong to be
#: reportable. Without it, a pile of text-mined co-mentions could carry a claim
#: to the threshold on its own.
MIN_SUPPORTING_WEIGHT = 0.30


def to_log_odds(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def from_log_odds(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


PRIOR_LOG_ODDS = to_log_odds(PRIOR_CONFIDENCE)


class Revision(BaseModel):
    """One audit row. Immutable once written."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    evidence_id: str
    evidence_date: str
    prior_confidence: float
    posterior_confidence: float
    prior_log_odds: float
    posterior_log_odds: float
    weight_applied: float
    direction: str
    rationale: str


class Claim(BaseModel):
    """A proposition about a gene and a phenotype that evidence can move."""

    model_config = ConfigDict(extra="forbid")

    id: str
    gene_id: str
    gene_symbol: str
    phenotype_id: str
    direction: str
    statement: str
    confidence: float
    log_odds: float
    supporting_record_ids: list[str] = Field(default_factory=list)
    contradicting_record_ids: list[str] = Field(default_factory=list)
    max_supporting_weight: float = 0.0
    evidence_count: int = 0
    implied_modality: str | None = None
    modality_rationale: str = ""
    axiom_ids: list[str] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    first_evidence_date: str | None = None
    last_evidence_date: str | None = None

    @property
    def reportable(self) -> bool:
        """Whether this claim clears the refusal thresholds. See METHODOLOGY.md."""
        return (
            self.confidence >= REFUSAL_CONFIDENCE_THRESHOLD
            and self.max_supporting_weight >= MIN_SUPPORTING_WEIGHT
        )

    def refusal_reason(self) -> str:
        if self.confidence < REFUSAL_CONFIDENCE_THRESHOLD:
            return (
                f"The evidence before the cutoff does not support a claim about "
                f"{self.gene_symbol}: confidence {self.confidence:.3f} is below the "
                f"{REFUSAL_CONFIDENCE_THRESHOLD} threshold, from {self.evidence_count} "
                f"piece(s) of evidence."
            )
        return (
            f"The evidence before the cutoff about {self.gene_symbol} is all weak: the "
            f"strongest supporting measurement has weight "
            f"{self.max_supporting_weight:.3f}, below the {MIN_SUPPORTING_WEIGHT} "
            f"minimum, so the claim rests on co-mentions rather than measurements."
        )


class BeliefMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    claims: dict[str, Claim] = Field(default_factory=dict)
    revision_count: int = 0

    def ranked(self, *, reportable_only: bool = True) -> list[Claim]:
        claims = [c for c in self.claims.values() if c.reportable or not reportable_only]
        return sorted(claims, key=lambda c: (-c.confidence, c.gene_symbol))

    def refusals(self) -> list[Claim]:
        return sorted(
            (c for c in self.claims.values() if not c.reportable),
            key=lambda c: (-c.confidence, c.gene_symbol),
        )


class BeliefReviser(Agent):
    name = "belief_reviser"

    def run(
        self,
        slice_store: SliceStore,
        axiom_set: AxiomSet,
        *,
        store: Store | None = None,
        flat_confidence: bool = False,
    ) -> BeliefMap:
        """Build the belief map by replaying evidence in publication-date order.

        `store` is the full store, used only to append audit rows. It is never
        read here, and nothing from it reaches the reasoning. `flat_confidence`
        is the "no belief revision" ablation: claims take the prior and evidence
        does not move them.
        """
        slice_store.assert_no_leak()
        belief = BeliefMap(cutoff=slice_store.cutoff)

        with self.tool("build_claims", axioms=len(axiom_set.axioms)) as call:
            claims = self._seed_claims(slice_store, axiom_set)
            belief.claims = claims
            call.records_out = len(claims)
            call.result_summary = f"{len(claims)} candidate claims seeded from axioms"

        with self.tool("collect_evidence") as call:
            evidence = self._collect_evidence(slice_store, axiom_set, claims)
            call.records_out = sum(len(v) for v in evidence.values())
            call.result_summary = (
                f"{call.records_out} evidence applications over {len(evidence)} claims"
            )

        with self.tool("revise", rule="log-odds accumulation", strength=EVIDENCE_STRENGTH) as call:
            applied = 0
            for claim_id, items in sorted(evidence.items()):
                claim = claims[claim_id]
                # Publication-date order. Ties broken by record ID so a replay is
                # byte-identical on any machine.
                for when, direction, weight, record_id, rationale in sorted(
                    items, key=lambda t: (t[0], t[3])
                ):
                    if flat_confidence:
                        continue
                    prior_lo = claim.log_odds
                    delta = direction * weight * EVIDENCE_STRENGTH
                    post_lo = prior_lo + delta
                    prior_c, post_c = from_log_odds(prior_lo), from_log_odds(post_lo)
                    claim.log_odds = post_lo
                    claim.confidence = post_c
                    claim.evidence_count += 1
                    if direction > 0:
                        claim.supporting_record_ids.append(record_id)
                        claim.max_supporting_weight = max(claim.max_supporting_weight, weight)
                    else:
                        claim.contradicting_record_ids.append(record_id)
                    iso = when.isoformat()
                    claim.first_evidence_date = claim.first_evidence_date or iso
                    claim.last_evidence_date = iso
                    revision = Revision(
                        claim_id=claim_id,
                        evidence_id=record_id,
                        evidence_date=iso,
                        prior_confidence=round(prior_c, 6),
                        posterior_confidence=round(post_c, 6),
                        prior_log_odds=round(prior_lo, 6),
                        posterior_log_odds=round(post_lo, 6),
                        weight_applied=round(weight, 6),
                        direction="supports" if direction > 0 else "contradicts",
                        rationale=rationale,
                    )
                    claim.revisions.append(revision)
                    applied += 1
                    if store is not None:
                        store.log_revision(
                            run_id=self.run_id,
                            claim_id=claim_id,
                            evidence_id=record_id,
                            evidence_date=iso,
                            prior_confidence=revision.prior_confidence,
                            posterior_confidence=revision.posterior_confidence,
                            prior_log_odds=revision.prior_log_odds,
                            posterior_log_odds=revision.posterior_log_odds,
                            weight_applied=revision.weight_applied,
                            direction=revision.direction,
                            rationale=rationale,
                        )
            belief.revision_count = applied
            call.records_out = applied
            call.result_summary = (
                f"{applied} revisions written"
                + (" (flat-confidence ablation: none applied)" if flat_confidence else "")
            )

        reportable = [c for c in belief.claims.values() if c.reportable]
        self.finish(
            {
                "cutoff": slice_store.cutoff,
                "claims": len(belief.claims),
                "reportable": len(reportable),
                "refusals": len(belief.claims) - len(reportable),
                "revisions": belief.revision_count,
                "flat_confidence_ablation": flat_confidence,
                "top": [
                    {"gene": c.gene_symbol, "confidence": round(c.confidence, 4)}
                    for c in belief.ranked()[:10]
                ],
            },
            inputs={"cutoff": slice_store.cutoff, "axioms": len(axiom_set.axioms)},
        )
        return belief

    # -- internals --------------------------------------------------------

    def _seed_claims(self, slice_store: SliceStore, axiom_set: AxiomSet) -> dict[str, Claim]:
        """One claim per gene that any axiom is about.

        The claim asserts the thing the benchmark asks about: that perturbing the
        gene raises fetal hemoglobin. Seeding from axioms rather than from a
        hand-written list means the candidate set is whatever the pre-T evidence
        mentions, which is what the forecast has to work from.
        """
        modality_by_gene = {
            gid: a
            for a in axiom_set.of_kind("implied_modality")
            for gid in a.subject_gene_ids
        }
        claims: dict[str, Claim] = {}
        for axiom in axiom_set.axioms:
            for gene_id in axiom.subject_gene_ids:
                if gene_id in claims:
                    claims[gene_id].axiom_ids.append(axiom.id)
                    continue
                gene = slice_store.node(gene_id)
                if gene is None:
                    continue
                symbol = str(gene.attrs.get("symbol") or gene.label)
                modality = modality_by_gene.get(gene_id)
                claims[gene_id] = Claim(
                    id=f"claim:hbf_increase:{gene_id}",
                    gene_id=gene_id,
                    gene_symbol=symbol,
                    phenotype_id="pheno:hbf_protein",
                    direction="increases",
                    statement=(
                        f"Loss or inhibition of {symbol} increases fetal hemoglobin in "
                        f"human erythroid cells."
                    ),
                    confidence=PRIOR_CONFIDENCE,
                    log_odds=PRIOR_LOG_ODDS,
                    implied_modality=modality.implied_modality if modality else None,
                    modality_rationale=modality.modality_rationale if modality else "",
                    axiom_ids=[axiom.id],
                )
        # Keyed by claim ID from here on.
        return {c.id: c for c in claims.values()}

    def _collect_evidence(
        self, slice_store: SliceStore, axiom_set: AxiomSet, claims: dict[str, Claim]
    ) -> dict[str, list[tuple[date, int, float, str, str]]]:
        """Every evidence application, as (date, direction, weight, record, why).

        Direction is the crux and is decided by rule, never by an LLM:

        *   A fitness hit is evidence *against* the therapeutic claim, not for
            it. A gene whose loss kills the cell cannot be a target, so an
            essentiality axiom contributes negative log-odds. This is the single
            most important sign convention in the module and it is what makes
            the pan-essentiality trap survivable.
        *   A functional HbF measurement supports the claim.
        *   A genetic association supports it, discounted by the method
            signature's author-reported-gene penalty where that applies.
        *   A literature co-mention supports it very weakly, and cannot on its
            own make a claim reportable because of `MIN_SUPPORTING_WEIGHT`.
        """
        by_claim: dict[str, list[tuple[date, int, float, str, str]]] = defaultdict(list)
        claim_by_gene = {c.gene_id: c.id for c in claims.values()}
        weights = axiom_set.weights

        measurements = {m.id: m for m in slice_store.nodes(NodeType.MEASUREMENT)}
        publications = {p.id: p for p in slice_store.nodes(NodeType.PUBLICATION)}

        for axiom in axiom_set.axioms:
            for gene_id in axiom.subject_gene_ids:
                claim_id = claim_by_gene.get(gene_id)
                if claim_id is None:
                    continue
                if axiom.kind == "essentiality":
                    if not axiom.scope_conditions.get("pan_essential"):
                        continue
                    for rid in axiom.supporting_record_ids:
                        node = measurements.get(rid)
                        if node is None or node.prov.effective_date is None:
                            continue
                        if not node.attrs.get("hit"):
                            continue
                        by_claim[claim_id].append(
                            (
                                node.prov.effective_date,
                                -1,
                                weights.get(rid, 0.1),
                                rid,
                                "fitness hit: loss of this gene reduces cell fitness, "
                                "which counts against it as a therapeutic target",
                            )
                        )
                elif axiom.kind in ("functional_hbf", "genetic_support"):
                    for rid in axiom.supporting_record_ids:
                        node = measurements.get(rid)
                        if node is None or node.prov.effective_date is None:
                            continue
                        why = (
                            "direct functional measurement on an HbF readout"
                            if axiom.kind == "functional_hbf"
                            else "genome-wide significant human genetic association "
                            "to the HbF trait family"
                        )
                        by_claim[claim_id].append(
                            (node.prov.effective_date, 1, weights.get(rid, 0.1), rid, why)
                        )
                elif axiom.kind == "literature_association":
                    hbf_specific = axiom.scope_conditions.get("hbf_specific_publications", 0)
                    for rid in axiom.supporting_record_ids:
                        node = publications.get(rid)
                        if node is None or node.prov.effective_date is None:
                            continue
                        tiers = node.attrs.get("matched_tiers") or []
                        weight = 0.20 if "hbf" in tiers else 0.05
                        by_claim[claim_id].append(
                            (
                                node.prov.effective_date,
                                1,
                                weight,
                                rid,
                                f"publication co-mentioning the gene with "
                                f"{'fetal hemoglobin' if 'hbf' in tiers else 'the erythroid context'}"
                                f"; {hbf_specific} HbF-specific records for this gene",
                            )
                        )
        return by_claim
