"""The cost lens: what therapeutic route a claim implies, and what that costs.

Why this is in the system at all. Casgevy lists at about $2.2M and Lyfgenia at
about $3.1M, neither figure including the required inpatient stay. Both need
apheresis, GMP manufacturing of an autologous product, and busulfan
myeloablative conditioning. That pathway is unavailable in most of the regions
carrying the disease burden. So a screen hit implying an oral small molecule is
worth orders of magnitude more per unit of confidence than one implying a
multi-edit ex vivo product, and a ranking that ignores this is ranking the
wrong thing.

The inference has to be makeable from pre-T information or it is useless inside
a forecast. It is therefore built from two pre-T facts: the protein class, taken
from the HGNC gene family, and whether the gene's effect is exerted through a
cis-regulatory element that an edit could disrupt. Both were knowable decades
before any slice used here. Nothing in this module reads a tractability
annotation or a drug database, because those reflect what is known now.

Every coefficient is a stated policy. None of it is fitted to the test set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hindcast.models import CostClass

#: Relative value per unit of confidence, by route. Not a price and not a
#: prediction of one. It is an ordering with deliberate gaps, chosen so that a
#: moderately confident small-molecule claim outranks a highly confident
#: multi-edit claim, which is the reordering the cost lens exists to produce.
#:
#: The gaps are justified as follows. A small molecule is an oral therapy
#: deliverable through existing pharmacy infrastructure, so it reaches the
#: populations that carry the disease. An in vivo edit removes apheresis,
#: manufacturing and conditioning but still needs cold chain and a delivery
#: vehicle that works in human HSCs, which does not yet exist at scale. A single
#: ex vivo edit is the Casgevy-class pathway: it works, and it costs millions
#: per patient. A multi-edit ex vivo product multiplies the manufacturing
#: burden without changing the delivery problem. Mechanistic insight that
#: implies no route scores zero, which is not a criticism of the science.
COST_WEIGHTS: dict[CostClass, float] = {
    CostClass.SMALL_MOLECULE: 10.0,
    CostClass.IN_VIVO_EDIT: 4.0,
    CostClass.EX_VIVO_SINGLE_EDIT: 1.0,
    CostClass.EX_VIVO_MULTI_EDIT: 0.4,
    CostClass.NOT_THERAPEUTIC: 0.0,
}

#: Anchor figures quoted in the README. Held here as data so the README and the
#: scorecard cannot drift apart, with the source of each recorded.
PRICE_ANCHORS: dict[str, dict[str, object]] = {
    "exagamglogene autotemcel": {
        "brand": "Casgevy",
        "list_price_usd": 2_200_000,
        "modality": CostClass.EX_VIVO_SINGLE_EDIT,
        "target": "BCL11A erythroid enhancer",
        "note": "List price excludes the required inpatient stay and conditioning.",
        "source": "manufacturer list price as widely reported at US approval, December 2023",
    },
    "lovotibeglogene autotemcel": {
        "brand": "Lyfgenia",
        "list_price_usd": 3_100_000,
        "modality": CostClass.EX_VIVO_SINGLE_EDIT,
        "target": "beta-globin gene addition",
        "note": "List price excludes the required inpatient stay and conditioning.",
        "source": "manufacturer list price as widely reported at US approval, December 2023",
    },
    "hydroxyurea": {
        "brand": "several generic",
        "list_price_usd": 1_000,
        "modality": CostClass.SMALL_MOLECULE,
        "target": "multiple, including HbF induction",
        "note": "Order-of-magnitude annual generic cost. Held as the small-molecule anchor.",
        "source": "generic oral therapy, order of magnitude only",
    },
}

#: HGNC gene-family patterns that imply a small molecule is plausible. Kinases,
#: enzymes with defined catalytic pockets, and nuclear receptors are the classes
#: with a track record of oral inhibitors. Matching is on the HGNC gene family
#: string, which is pre-T information about protein class.
SMALL_MOLECULE_FAMILIES: tuple[str, ...] = (
    r"kinases?\b",
    r"\bphosphatases?\b",
    r"methyltransferases?",
    r"demethylases?",
    r"deacetylases?",
    r"acetyltransferases?",
    r"\bhelicases?\b",
    r"nuclear hormone receptors",
    r"nuclear receptors",
    r"\bproteases?\b",
    r"\bATPases?\b",
    r"bromodomain",
    r"SNF2 related",
    r"deubiquitinases?",
    r"ubiquitin ligases?",
    r"\bsirtuins?\b",
)

#: Classes with no useful small-molecule surface. A sequence-specific
#: transcription factor's job is to bind DNA, and occluding that interface with
#: a drug-like molecule has a long record of failure. This is the geometry
#: problem the brief refers to, stated as a cost consequence: a claim about a
#: zinc-finger transcription factor implies an edit, not a pill.
HARD_TO_DRUG_FAMILIES: tuple[str, ...] = (
    r"zinc fingers",
    r"transcription factors",
    r"Myb/SANT",
    r"homeoboxes",
    r"basic helix-loop-helix",
    r"\bGATA\b",
    r"high mobility group",
)

#: Complexes whose disruption needs more than one edit, or whose members are
#: shared with essential processes. A claim that only works by removing a whole
#: complex implies the most expensive route.
MULTI_EDIT_HINTS: tuple[str, ...] = (
    r"NuRD complex",
    r"CoREST complex",
    r"BAF complex",
    r"SWI/SNF",
    r"Polycomb",
)

_SM_RE = re.compile("|".join(SMALL_MOLECULE_FAMILIES), re.I)
_HARD_RE = re.compile("|".join(HARD_TO_DRUG_FAMILIES), re.I)
_MULTI_RE = re.compile("|".join(MULTI_EDIT_HINTS), re.I)


@dataclass(frozen=True)
class ModalityCall:
    """A modality inference, with the reason it was made."""

    cost_class: CostClass
    rationale: str
    cost_weight: float

    def as_dict(self) -> dict[str, object]:
        return {
            "cost_class": str(self.cost_class),
            "rationale": self.rationale,
            "cost_weight": self.cost_weight,
        }


def infer_modality(
    *,
    symbol: str,
    gene_family: str | None,
    locus_type: str | None = None,
    acts_via_cis_element: bool = False,
    is_pan_essential: bool = False,
    raises_hbf: bool = True,
) -> ModalityCall:
    """Infer the therapeutic route a claim about this gene implies.

    Order of the checks is the policy. Essentiality is checked first because a
    gene whose loss kills the cell is not a target whatever else is true of it,
    and a system that ranks such a gene highly has made the expensive mistake
    this lens exists to catch.
    """
    family = gene_family or ""

    if is_pan_essential:
        return ModalityCall(
            CostClass.NOT_THERAPEUTIC,
            f"{symbol} is pan-essential: loss of function kills the cell, so the "
            f"effect cannot be separated from toxicity in a therapeutic window",
            COST_WEIGHTS[CostClass.NOT_THERAPEUTIC],
        )

    if not raises_hbf:
        return ModalityCall(
            CostClass.NOT_THERAPEUTIC,
            f"{symbol} is not claimed to raise HbF, so no HbF-induction route follows",
            COST_WEIGHTS[CostClass.NOT_THERAPEUTIC],
        )

    if locus_type and "protein product" not in locus_type.lower():
        return ModalityCall(
            CostClass.EX_VIVO_SINGLE_EDIT,
            f"{symbol} is not a protein-coding locus ({locus_type}), so there is no "
            f"protein to bind and the route is an edit",
            COST_WEIGHTS[CostClass.EX_VIVO_SINGLE_EDIT],
        )

    if _SM_RE.search(family):
        hit = _SM_RE.search(family)
        return ModalityCall(
            CostClass.SMALL_MOLECULE,
            f"{symbol} belongs to an enzyme class with a catalytic pocket "
            f"({hit.group(0) if hit else 'enzyme'} in HGNC family {family!r}), so an "
            f"oral inhibitor is a plausible route",
            COST_WEIGHTS[CostClass.SMALL_MOLECULE],
        )

    # The cis-element check comes before the complex check, and the ordering is a
    # policy choice worth stating plainly. A gene can sit in a large complex and
    # still have its phenotype exerted through one cis-regulatory element, in
    # which case a single edit of that element reproduces the effect and the
    # complex membership is irrelevant to cost. BCL11A is the case that forced
    # this ordering: HGNC lists it among BAF complex subunits, which would score
    # it as the most expensive route, while the approved therapy disrupts its
    # erythroid enhancer with one edit. The established pathway wins.
    if acts_via_cis_element:
        return ModalityCall(
            CostClass.EX_VIVO_SINGLE_EDIT,
            f"{symbol} acts through a cis-regulatory element, which one edit can "
            f"disrupt: the Casgevy-class pathway",
            COST_WEIGHTS[CostClass.EX_VIVO_SINGLE_EDIT],
        )

    if _MULTI_RE.search(family):
        hit = _MULTI_RE.search(family)
        return ModalityCall(
            CostClass.EX_VIVO_MULTI_EDIT,
            f"{symbol} acts as part of {hit.group(0) if hit else 'a complex'}, so "
            f"reproducing the effect implies disrupting a complex rather than one gene",
            COST_WEIGHTS[CostClass.EX_VIVO_MULTI_EDIT],
        )

    if _HARD_RE.search(family):
        hit = _HARD_RE.search(family)
        return ModalityCall(
            CostClass.EX_VIVO_SINGLE_EDIT,
            f"{symbol} is a sequence-specific DNA-binding protein "
            f"({hit.group(0) if hit else 'DNA binding'}), a class with no useful "
            f"small-molecule surface, so the route is an edit of the gene or its enhancer",
            COST_WEIGHTS[CostClass.EX_VIVO_SINGLE_EDIT],
        )

    return ModalityCall(
        CostClass.EX_VIVO_SINGLE_EDIT,
        f"{symbol} has no protein class implying a small molecule, so an edit is "
        f"assumed as the conservative route",
        COST_WEIGHTS[CostClass.EX_VIVO_SINGLE_EDIT],
    )


def cost_weighted_score(confidence: float, cost_class: CostClass) -> float:
    """Confidence times the route's weight. The cost-lens ranking key."""
    return confidence * COST_WEIGHTS[cost_class]
