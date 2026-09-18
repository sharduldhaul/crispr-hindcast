"""AXIOM_EXTRACTOR: turn pre-T evidence into executable rules.

Contract. In: a slice of the graph. Out: a list of `Axiom` objects, each with a
statement, scope conditions, supporting and contradicting record IDs, a
confidence and the modality it implies.

Axioms are rules, not summaries. Each one is applicable: `Axiom.applies_to`
answers whether a gene and context fall inside its scope, and the forecaster
composes axioms to reach a prediction rather than re-reading the evidence.

The validator is the point of this module. An axiom with no supporting record ID
is rejected, which is hard rule 1 made structural: a rule that cannot name the
rows it came from cannot enter the system, so no downstream output can quote a
number that has no source.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hindcast.agents.base import Agent
from hindcast.agents.method_signature import MethodSignature, Weighting
from hindcast.cost import ModalityCall, infer_modality
from hindcast.models import CostClass, NodeType
from hindcast.scope import PHENOTYPE_FAMILIES
from hindcast.store import SliceStore

#: Genome-wide significance. The conventional threshold, stated not derived.
GWAS_SIGNIFICANCE = 5e-8

#: DepMap gene effect at or below which a gene is treated as essential in a line.
ESSENTIAL_EFFECT = -1.0

#: Fraction of tested lines that must be essential for a pan-essential call.
PAN_ESSENTIAL_FRACTION = 0.70


class AxiomValidationError(ValueError):
    """An axiom that cannot enter the system, and why."""


class Axiom(BaseModel):
    """One executable rule derived from evidence in a slice."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str = Field(description="Rule family, e.g. genetic_support, essentiality, mechanism.")
    statement: str = Field(description="What the rule asserts, in one sentence.")
    subject_gene_ids: list[str] = Field(default_factory=list)
    object_gene_ids: list[str] = Field(default_factory=list)
    phenotype_id: str | None = None
    direction: str = Field(default="increases", description="increases, decreases or none.")
    scope_conditions: dict[str, Any] = Field(
        default_factory=dict,
        description="Conditions under which the rule holds: system class, perturbation, cutoff.",
    )
    supporting_record_ids: list[str] = Field(default_factory=list)
    contradicting_record_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    implied_modality: str | None = None
    modality_rationale: str = ""
    evidence_weight_total: float = 0.0
    derivation: str = Field(default="", description="How the rule was produced.")

    @field_validator("direction")
    @classmethod
    def _known_direction(cls, v: str) -> str:
        if v not in ("increases", "decreases", "none"):
            raise ValueError(f"direction must be increases, decreases or none, got {v!r}")
        return v

    def applies_to(
        self,
        *,
        gene_id: str,
        system_class: str | None = None,
        phenotype_id: str | None = None,
    ) -> bool:
        """Whether this rule covers the given gene and context. This is what
        makes an axiom executable rather than prose."""
        if self.subject_gene_ids and gene_id not in self.subject_gene_ids:
            return False
        if phenotype_id and self.phenotype_id and phenotype_id != self.phenotype_id:
            return False
        allowed = self.scope_conditions.get("system_classes")
        if allowed and system_class and system_class not in allowed:
            return False
        return True


def validate_axiom(axiom: Axiom) -> None:
    """Reject an axiom that cannot be traced, scoped or applied.

    This is the gate hard rule 1 depends on. Everything downstream, including
    every number in every output, descends from axioms that passed here.
    """
    if not axiom.supporting_record_ids:
        raise AxiomValidationError(
            f"axiom {axiom.id!r} has no supporting record IDs; an untraceable rule "
            f"cannot enter the system"
        )
    if not axiom.statement.strip():
        raise AxiomValidationError(f"axiom {axiom.id!r} has an empty statement")
    if not (0.0 <= axiom.confidence <= 1.0):
        raise AxiomValidationError(
            f"axiom {axiom.id!r} has confidence {axiom.confidence} outside 0 to 1"
        )
    if axiom.direction != "none" and axiom.phenotype_id is None:
        raise AxiomValidationError(
            f"axiom {axiom.id!r} asserts a direction but names no phenotype, so it "
            f"cannot be checked against anything"
        )
    if not axiom.subject_gene_ids and axiom.kind != "corpus_level":
        raise AxiomValidationError(
            f"axiom {axiom.id!r} names no subject gene and is not a corpus-level rule"
        )
    if axiom.evidence_weight_total < 0:
        raise AxiomValidationError(f"axiom {axiom.id!r} has negative total evidence weight")


class AxiomSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    axioms: list[Axiom] = Field(default_factory=list)
    rejected: list[dict[str, str]] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)

    def by_gene(self, gene_id: str) -> list[Axiom]:
        return [a for a in self.axioms if gene_id in a.subject_gene_ids]

    def of_kind(self, kind: str) -> list[Axiom]:
        return [a for a in self.axioms if a.kind == kind]


class AxiomExtractor(Agent):
    name = "axiom_extractor"

    def __init__(
        self,
        run_id: str,
        signature: MethodSignature | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(run_id, **kw)
        self.signature = signature or MethodSignature()

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _directness(slice_store: SliceStore, phenotype_id: str | None) -> str:
        if not phenotype_id:
            return "proxy"
        node = slice_store.node(phenotype_id)
        if node is None:
            return "proxy"
        return str(node.attrs.get("directness") or "proxy")

    def _gene_label(self, slice_store: SliceStore, gene_id: str) -> str:
        node = slice_store.node(gene_id)
        return node.label if node else gene_id

    # -- extraction -------------------------------------------------------

    def run(self, slice_store: SliceStore) -> AxiomSet:
        slice_store.assert_no_leak()
        cutoff = slice_store.cutoff
        axioms: list[Axiom] = []
        rejected: list[dict[str, str]] = []
        weights: dict[str, float] = {}

        with self.tool("load_measurements", cutoff=cutoff) as call:
            measurements = slice_store.nodes(NodeType.MEASUREMENT)
            call.records_out = len(measurements)
            call.result_summary = f"{len(measurements)} measurements visible before {cutoff}"

        # Replication counts and genetic support feed the weighting function, and
        # both must be computed from inside the slice. Computing them from the
        # full store would leak.
        with self.tool("compute_replication_and_genetic_support") as call:
            labs_by_gene: dict[str, set[str]] = defaultdict(set)
            genetic_support: set[str] = set()
            for m in measurements:
                gid = str(m.attrs.get("gene_id") or "")
                if not gid:
                    continue
                if m.prov.pmid:
                    labs_by_gene[gid].add(m.prov.pmid)
                if (
                    m.attrs.get("assay") == "gwas_association"
                    and float(m.attrs.get("p_value") or 1.0) < GWAS_SIGNIFICANCE
                ):
                    genetic_support.add(gid)
            self.signature.replication_counts = {
                g: len(p) for g, p in labs_by_gene.items()
            }
            self.signature.human_genetic_support = genetic_support
            call.records_out = len(genetic_support)
            call.result_summary = (
                f"{len(genetic_support)} genes with genome-wide significant HbF support, "
                f"replication counted over distinct PMIDs"
            )

        with self.tool("weight_measurements") as call:
            weighted: list[tuple[Any, Weighting]] = []
            for m in measurements:
                w = self.signature.weight_measurement(
                    m.attrs,
                    measurement_id=m.id,
                    directness=self._directness(slice_store, m.attrs.get("phenotype_id")),
                )
                weights[m.id] = w.weight
                weighted.append((m, w))
            call.records_in = len(measurements)
            call.records_out = len(weighted)
            call.result_summary = f"weights assigned, max {max(weights.values(), default=0):.3f}"

        with self.tool("extract_genetic_support_axioms") as call:
            got = self._genetic_support_axioms(slice_store, weighted)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} genetic support axioms"
            axioms.extend(got)

        with self.tool("extract_essentiality_axioms") as call:
            got = self._essentiality_axioms(slice_store, weighted)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} essentiality axioms"
            axioms.extend(got)

        with self.tool("extract_functional_axioms") as call:
            got = self._functional_axioms(slice_store, weighted)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} functional HbF axioms"
            axioms.extend(got)

        with self.tool("extract_literature_axioms") as call:
            got = self._literature_axioms(slice_store)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} literature association axioms"
            axioms.extend(got)

        with self.tool("extract_modality_axioms") as call:
            got = self._modality_axioms(slice_store, axioms)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} modality axioms"
            axioms.extend(got)

        with self.tool("validate") as call:
            kept: list[Axiom] = []
            for axiom in axioms:
                try:
                    validate_axiom(axiom)
                except AxiomValidationError as exc:
                    rejected.append({"id": axiom.id, "reason": str(exc)})
                    continue
                kept.append(axiom)
            call.records_in = len(axioms)
            call.records_out = len(kept)
            call.result_summary = f"{len(rejected)} axioms rejected by the validator"

        result = AxiomSet(cutoff=cutoff, axioms=kept, rejected=rejected, weights=weights)
        self.finish(
            {
                "cutoff": cutoff,
                "axioms": len(kept),
                "rejected": len(rejected),
                "by_kind": {
                    k: len(result.of_kind(k)) for k in sorted({a.kind for a in kept})
                },
            },
            inputs={"cutoff": cutoff, "measurements": len(measurements)},
        )
        return result

    # -- axiom families ---------------------------------------------------

    def _genetic_support_axioms(
        self, slice_store: SliceStore, weighted: list[tuple[Any, Weighting]]
    ) -> list[Axiom]:
        """Genome-wide significant association to the HbF trait family.

        One axiom per gene, carrying every association row that supports it. The
        author-reported-gene caveat travels with the axiom rather than being
        dropped, because it is the difference between a locus and a mechanism.
        """
        by_gene: dict[str, list[tuple[Any, Weighting]]] = defaultdict(list)
        for m, w in weighted:
            if m.attrs.get("assay") != "gwas_association":
                continue
            by_gene[str(m.attrs.get("gene_id"))].append((m, w))

        out: list[Axiom] = []
        for gene_id, rows in sorted(by_gene.items()):
            significant = [
                (m, w) for m, w in rows if float(m.attrs.get("p_value") or 1.0) < GWAS_SIGNIFICANCE
            ]
            if not significant:
                continue
            best = min(significant, key=lambda r: float(r[0].attrs.get("p_value") or 1.0))
            symbol = self._gene_label(slice_store, gene_id)
            total = sum(w.weight for _, w in significant)
            author_reported = all(
                m.attrs.get("gene_assignment") == "author_reported" for m, _ in significant
            )
            phenotype = str(best[0].attrs.get("phenotype_id"))
            out.append(
                Axiom(
                    id=f"axiom:genetic:{gene_id}",
                    kind="genetic_support",
                    statement=(
                        f"Common variation at the {symbol} locus is associated with the "
                        f"HbF trait family in human populations, with a best reported "
                        f"p-value of {float(best[0].attrs.get('p_value')):.2e}."
                    ),
                    subject_gene_ids=[gene_id],
                    phenotype_id=phenotype,
                    direction="none",
                    scope_conditions={
                        "system_classes": ["human_population"],
                        "significance_threshold": GWAS_SIGNIFICANCE,
                        "gene_assignment": "author_reported" if author_reported else "mixed",
                        "caveat": (
                            "The association identifies a locus. The gene named is the "
                            "author-reported gene at that locus and is not established "
                            "as causal."
                        )
                        if author_reported
                        else "",
                    },
                    supporting_record_ids=sorted(m.id for m, _ in significant),
                    confidence=0.0,
                    evidence_weight_total=round(total, 6),
                    derivation=(
                        f"{len(significant)} GWAS Catalog associations below "
                        f"{GWAS_SIGNIFICANCE:g}, weighted by method signature"
                    ),
                )
            )
        return out

    def _essentiality_axioms(
        self, slice_store: SliceStore, weighted: list[tuple[Any, Weighting]]
    ) -> list[Axiom]:
        """Genes whose loss reduces fitness across many contexts.

        This is the axiom family that keeps the system from proposing a target
        that kills the cell. It is derived from dated fitness screens inside the
        slice, not from the DepMap release, which postdates every cutoff used
        here.
        """
        by_gene: dict[str, list[tuple[Any, Weighting]]] = defaultdict(list)
        for m, w in weighted:
            pheno = slice_store.node(str(m.attrs.get("phenotype_id") or ""))
            if pheno is None or pheno.attrs.get("family") != "FITNESS":
                continue
            by_gene[str(m.attrs.get("gene_id"))].append((m, w))

        out: list[Axiom] = []
        for gene_id, rows in sorted(by_gene.items()):
            hits = [(m, w) for m, w in rows if m.attrs.get("hit")]
            fraction = len(hits) / len(rows) if rows else 0.0
            symbol = self._gene_label(slice_store, gene_id)
            if len(rows) < 3:
                continue
            essential = fraction >= PAN_ESSENTIAL_FRACTION
            out.append(
                Axiom(
                    id=f"axiom:essentiality:{gene_id}",
                    kind="essentiality",
                    statement=(
                        f"{symbol} scored as a fitness hit in {len(hits)} of {len(rows)} "
                        f"dated fitness screens that tested it "
                        f"({fraction:.0%}), so loss of function "
                        f"{'reduces' if essential else 'does not consistently reduce'} "
                        f"cell fitness."
                    ),
                    subject_gene_ids=[gene_id],
                    phenotype_id=str(rows[0][0].attrs.get("phenotype_id")),
                    direction="decreases" if essential else "none",
                    scope_conditions={
                        "fitness_hit_fraction": round(fraction, 4),
                        "screens_tested": len(rows),
                        "pan_essential": essential,
                        "pan_essential_threshold": PAN_ESSENTIAL_FRACTION,
                    },
                    supporting_record_ids=sorted(m.id for m, _ in rows),
                    confidence=0.0,
                    evidence_weight_total=round(sum(w.weight for _, w in rows), 6),
                    derivation=(
                        "fitness hit fraction over dated screens that tested the gene"
                    ),
                )
            )
        return out

    def _functional_axioms(
        self, slice_store: SliceStore, weighted: list[tuple[Any, Weighting]]
    ) -> list[Axiom]:
        """Direct functional evidence that perturbing a gene changes HbF."""
        by_gene: dict[str, list[tuple[Any, Weighting]]] = defaultdict(list)
        for m, w in weighted:
            pheno = slice_store.node(str(m.attrs.get("phenotype_id") or ""))
            if pheno is None or pheno.attrs.get("family") != "HBF":
                continue
            if m.attrs.get("assay") == "gwas_association":
                continue
            by_gene[str(m.attrs.get("gene_id"))].append((m, w))

        out: list[Axiom] = []
        for gene_id, rows in sorted(by_gene.items()):
            symbol = self._gene_label(slice_store, gene_id)
            systems = sorted({str(m.attrs.get("system_class")) for m, _ in rows})
            best = max(rows, key=lambda r: r[1].weight)
            out.append(
                Axiom(
                    id=f"axiom:functional:{gene_id}",
                    kind="functional_hbf",
                    statement=(
                        f"Perturbing {symbol} changes an HbF-family readout in "
                        f"{len(rows)} measurement(s) across {len(systems)} system(s)."
                    ),
                    subject_gene_ids=[gene_id],
                    phenotype_id=str(best[0].attrs.get("phenotype_id")),
                    direction="increases",
                    scope_conditions={
                        "system_classes": systems,
                        "measurements": len(rows),
                        "best_weight": best[1].weight,
                    },
                    supporting_record_ids=sorted(m.id for m, _ in rows),
                    confidence=0.0,
                    evidence_weight_total=round(sum(w.weight for _, w in rows), 6),
                    derivation="direct functional measurements on an HbF-family phenotype",
                )
            )
        return out

    def _literature_axioms(self, slice_store: SliceStore) -> list[Axiom]:
        """Dated literature association between a gene and the HbF phenotype.

        The weakest axiom family, and the one that has to be handled most
        carefully. A publication linking a gene to fetal hemoglobin is evidence
        that the field was looking, not evidence of an effect or of its
        direction. So these axioms carry `direction = none`, they are weighted at
        the literature co-mention rate, and the refusal rule requires at least
        one stronger measurement before any claim built on them can be reported.
        """
        pubs = slice_store.nodes(NodeType.PUBLICATION)
        by_gene: dict[str, list[Any]] = defaultdict(list)
        hbf_by_gene: dict[str, list[Any]] = defaultdict(list)
        genes_by_symbol: dict[str, str] = {}
        for pub in pubs:
            tiers = pub.attrs.get("matched_tiers") or []
            for symbol in pub.attrs.get("matched_genes") or []:
                if symbol not in genes_by_symbol:
                    node = slice_store.gene_by_symbol(symbol)
                    if node is None:
                        continue
                    genes_by_symbol[symbol] = node.id
                gid = genes_by_symbol[symbol]
                by_gene[gid].append(pub)
                if "hbf" in tiers:
                    hbf_by_gene[gid].append(pub)

        out: list[Axiom] = []
        for gene_id, pub_list in sorted(by_gene.items()):
            symbol = self._gene_label(slice_store, gene_id)
            hbf_pubs = hbf_by_gene.get(gene_id, [])
            earliest = min(p.prov.effective_date for p in pub_list)
            out.append(
                Axiom(
                    id=f"axiom:literature:{gene_id}",
                    kind="literature_association",
                    statement=(
                        f"{symbol} appears in {len(pub_list)} publication(s) in an "
                        f"erythroid or HbF context before the cutoff, of which "
                        f"{len(hbf_pubs)} name fetal hemoglobin or gamma globin "
                        f"specifically. Earliest {earliest.isoformat()}."
                    ),
                    subject_gene_ids=[gene_id],
                    phenotype_id=None,
                    direction="none",
                    scope_conditions={
                        "publications": len(pub_list),
                        "hbf_specific_publications": len(hbf_pubs),
                        "earliest": earliest.isoformat(),
                        "caveat": (
                            "A co-mention is evidence that the field was looking, not "
                            "evidence of an effect or its direction."
                        ),
                    },
                    supporting_record_ids=sorted(p.id for p in hbf_pubs or pub_list)[:200],
                    confidence=0.0,
                    evidence_weight_total=round(
                        len(hbf_pubs) * 0.20 + (len(pub_list) - len(hbf_pubs)) * 0.05, 6
                    ),
                    derivation=(
                        "Europe PMC co-mention counts, split by whether the record names "
                        "HbF specifically or only the erythroid context"
                    ),
                )
            )
        return out

    def _modality_axioms(self, slice_store: SliceStore, existing: list[Axiom]) -> list[Axiom]:
        """What therapeutic route a claim about each gene would imply.

        Derived from the gene's protein class and from whether the pre-T record
        shows its effect running through a cis-regulatory element. Both are pre-T
        facts. See `hindcast.cost`.
        """
        essential: set[str] = {
            gid
            for a in existing
            if a.kind == "essentiality" and a.scope_conditions.get("pan_essential")
            for gid in a.subject_gene_ids
        }
        genetic: dict[str, Axiom] = {
            gid: a for a in existing if a.kind == "genetic_support" for gid in a.subject_gene_ids
        }
        subjects: dict[str, list[Axiom]] = defaultdict(list)
        for a in existing:
            for gid in a.subject_gene_ids:
                subjects[gid].append(a)

        out: list[Axiom] = []
        for gene_id, axiom_list in sorted(subjects.items()):
            gene = slice_store.node(gene_id)
            if gene is None:
                continue
            # A gene whose HbF association is genetic and whose reported locus is
            # non-coding is the cis-element case: the evidence points at a
            # regulatory region rather than at the protein.
            cis = gene_id in genetic and any(
                a.kind == "genetic_support" for a in axiom_list
            )
            call: ModalityCall = infer_modality(
                symbol=str(gene.attrs.get("symbol") or gene.label),
                gene_family=str(gene.attrs.get("gene_family") or ""),
                locus_type=str(gene.attrs.get("locus_type") or ""),
                acts_via_cis_element=cis,
                is_pan_essential=gene_id in essential,
            )
            support = sorted(
                {rid for a in axiom_list for rid in a.supporting_record_ids}
            )[:50]
            if not support:
                continue
            out.append(
                Axiom(
                    id=f"axiom:modality:{gene_id}",
                    kind="implied_modality",
                    statement=(
                        f"A claim that {gene.label} raises HbF implies the "
                        f"{call.cost_class} route. {call.rationale}"
                    ),
                    subject_gene_ids=[gene_id],
                    phenotype_id=None,
                    direction="none",
                    scope_conditions={
                        "gene_family": gene.attrs.get("gene_family"),
                        "locus_type": gene.attrs.get("locus_type"),
                        "acts_via_cis_element": cis,
                        "pan_essential": gene_id in essential,
                    },
                    supporting_record_ids=support,
                    confidence=0.0,
                    implied_modality=str(call.cost_class),
                    modality_rationale=call.rationale,
                    evidence_weight_total=0.0,
                    derivation="hindcast.cost.infer_modality over HGNC protein class",
                )
            )
        return out
