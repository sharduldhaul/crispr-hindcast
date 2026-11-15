"""Grounding: whether each claim rests on evidence the model was given.

Contract. In: a finished `ModelRun`, the slice it ran on and the full store.
Out: a `GroundingReport` that classifies every cited ID and says, claim by
claim, whether the claim is grounded. No model is involved; the same run
record always produces the same report.

Definitions, used unchanged in METHODOLOGY.md and the scorecard:

*   A cited ID is *valid* if the slice holds it, and *in context* if it was
    also among the rows or tool results the model received.
*   A cited ID the slice lacks is *post-cutoff* if the full store holds it,
    and *fabricated* if no store does.
*   A claim is *grounded* if it cites at least one in-context evidence row
    that names its gene.

What this module must never do:

*   Run before the model has answered, or hand anything to the forecaster.
    The full store is opened here only to tell a post-cutoff ID from a
    fabricated one.
*   Read the rule book or the answer key. Grounding says whether a claim
    rests on given evidence, not whether the claim is right; the grader
    scores that, and stays blind to this report.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from hindcast.llm.forecaster import ModelRun
from hindcast.models import Node, NodeType
from hindcast.store import SliceStore, Store


class CitationStatus(StrEnum):
    IN_CONTEXT = "in_context"
    OUT_OF_CONTEXT = "out_of_context"
    POST_CUTOFF = "post_cutoff"
    FABRICATED = "fabricated"


class Rate(BaseModel):
    """A rate as its two counts. With a denominator of 0 there is no rate to report."""

    model_config = ConfigDict(extra="forbid")

    numerator: int
    denominator: int


class CitationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cited_id: str
    status: CitationStatus
    names_gene: bool


class ClaimGrounding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str
    gene_id: str
    grounded: bool
    citations: list[CitationCheck]


class GroundingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Cited IDs the slice holds, over all cited IDs.
    citation_validity: Rate
    #: Cited IDs the model was actually shown, over all cited IDs.
    citations_in_context: Rate
    #: Grounded claims over all claims.
    grounded_claim_rate: Rate
    post_cutoff_ids: list[str] = Field(default_factory=list)
    fabricated_ids: list[str] = Field(default_factory=list)
    claims: list[ClaimGrounding] = Field(default_factory=list)


def names_gene(node: Node, gene_symbol: str, gene_id: str) -> bool:
    """Whether an evidence row names the gene.

    A measurement names the gene it was recorded for. A publication names a
    gene its ingest matched, or one whose approved symbol stands as a word in
    its title. Other node types carry no evidence about a gene: the gene's own
    reference node, cited alone, grounds nothing.
    """
    if node.type is NodeType.MEASUREMENT:
        return node.attrs.get("gene_id") == gene_id
    if node.type is NodeType.PUBLICATION:
        if gene_symbol in (node.attrs.get("matched_genes") or []):
            return True
        pattern = rf"(?<![A-Za-z0-9]){re.escape(gene_symbol)}(?![A-Za-z0-9])"
        return re.search(pattern, node.label, flags=re.IGNORECASE) is not None
    return False


def check_grounding(run: ModelRun, slice_store: SliceStore, store: Store) -> GroundingReport:
    """Classify every citation of a run that produced a forecast."""
    if run.forecast is None:
        raise ValueError("grounding is checked only for a run that produced a forecast")
    context = set(run.context_node_ids)
    claims: list[ClaimGrounding] = []
    for item in run.forecast.items:
        checks: list[CitationCheck] = []
        for cited_id in item.supporting_record_ids:
            node = slice_store.node(cited_id)
            if node is None:
                status = (
                    CitationStatus.FABRICATED
                    if store.node(cited_id) is None
                    else CitationStatus.POST_CUTOFF
                )
            elif cited_id in context:
                status = CitationStatus.IN_CONTEXT
            else:
                status = CitationStatus.OUT_OF_CONTEXT
            checks.append(
                CitationCheck(
                    cited_id=cited_id,
                    status=status,
                    names_gene=node is not None
                    and names_gene(node, item.gene_symbol, item.gene_id),
                )
            )
        claims.append(
            ClaimGrounding(
                gene_symbol=item.gene_symbol,
                gene_id=item.gene_id,
                grounded=any(
                    c.status is CitationStatus.IN_CONTEXT and c.names_gene for c in checks
                ),
                citations=checks,
            )
        )

    cited = [c for claim in claims for c in claim.citations]

    def ids(status: CitationStatus) -> list[str]:
        return sorted({c.cited_id for c in cited if c.status is status})

    in_context = sum(c.status is CitationStatus.IN_CONTEXT for c in cited)
    valid = in_context + sum(c.status is CitationStatus.OUT_OF_CONTEXT for c in cited)
    return GroundingReport(
        citation_validity=Rate(numerator=valid, denominator=len(cited)),
        citations_in_context=Rate(numerator=in_context, denominator=len(cited)),
        grounded_claim_rate=Rate(
            numerator=sum(c.grounded for c in claims), denominator=len(claims)
        ),
        post_cutoff_ids=ids(CitationStatus.POST_CUTOFF),
        fabricated_ids=ids(CitationStatus.FABRICATED),
        claims=claims,
    )
