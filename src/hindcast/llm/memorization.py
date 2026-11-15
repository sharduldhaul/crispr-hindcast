"""The memorization signal: correct claims that the given evidence does not explain.

Contract. In: the scorecard and the grounding report of one run. Out: a
`MemorizationReport` listing the recalled claims.

A claim is *recalled* when its gene's role was established on or after the
cutoff, by the frozen rule book, and the claim is not grounded. The model
named a later result and pointed at nothing it was shown, so its training
data is the remaining source. In the `none` condition the model is shown
nothing, so every correct claim there is recalled: that row is the reference
the other conditions are read against.

What this module must never do:

*   Decide what was established. It reads the ground truth the grader already
    wrote to the scorecard and never the rule book itself.
*   Call a grounded claim clean. Grounding shows a claim cites a given row
    that names its gene, not that the row was the reason for the claim.
    LIMITATIONS.md says what the signal cannot detect.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.grader import Scorecard
from hindcast.llm.grounding import GroundingReport, Rate

#: The trap family that asks about a gene with no pre-cutoff evidence.
POSTDATES_CUTOFF = "postdates_cutoff"


class MemorizationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Claimed genes whose role was established on or after the cutoff.
    post_cutoff_claims: list[str] = Field(default_factory=list)
    #: Those among them whose claim is not grounded.
    recalled_claims: list[str] = Field(default_factory=list)
    #: Recalled claims over post-cutoff claims.
    recalled_rate: Rate
    #: Postdates-cutoff traps the forecast failed: genes it claimed although
    #: the slice held no evidence for them.
    postdates_cutoff_traps_failed: list[str] = Field(default_factory=list)


def check_memorization(scorecard: Scorecard, grounding: GroundingReport) -> MemorizationReport:
    truth = set(scorecard.ground_truth_symbols)
    post_cutoff = [c for c in grounding.claims if c.gene_symbol in truth]
    recalled = sorted(c.gene_symbol for c in post_cutoff if not c.grounded)
    return MemorizationReport(
        post_cutoff_claims=sorted(c.gene_symbol for c in post_cutoff),
        recalled_claims=recalled,
        recalled_rate=Rate(numerator=len(recalled), denominator=len(post_cutoff)),
        postdates_cutoff_traps_failed=sorted(
            t.gene_symbol for t in scorecard.traps if t.kind == POSTDATES_CUTOFF and not t.passed
        ),
    )
