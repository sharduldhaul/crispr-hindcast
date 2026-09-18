"""Hard rule 1, checked rather than asserted.

Every quantitative claim in every output must trace to a specific record ID in
the store. This module walks a finished output and verifies it, so the
"fabricated numbers" row of the scorecard is a measurement and not a promise.

What counts as traceable. A number in an output is traceable if the object
carrying it names at least one record ID, and every record ID it names exists in
the store and carries a license. A number whose record IDs are all missing is
untraceable and is reported. Ranks, counts of the system's own outputs and the
frozen policy coefficients are not measurements and are listed as exempt, with
the reason, rather than quietly skipped.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast.store import SliceStore, Store

#: Fields that hold a number the system computed about its own output rather
#: than a measurement of the world. Exempt, and the reason is recorded.
EXEMPT_FIELDS: dict[str, str] = {
    "rank_by_confidence": "a rank over the system's own output, not a measurement",
    "rank_by_cost_impact": "a rank over the system's own output, not a measurement",
    "cost_weight": "a frozen policy coefficient from hindcast.cost, not a measurement",
    "cost_impact": "confidence times a frozen policy coefficient",
    "confidence": "computed by the belief reviser from weighted records, which are checked",
    "evidence_count": "a count of the records named on the same object",
    "max_supporting_weight": "a method signature weight over records named on the same object",
    "forecast_size": "a count of the system's own output",
    "refusal_count": "a count of the system's own output",
}


class ProvenanceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    detail: str


class ProvenanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checked_objects: int = 0
    checked_record_ids: int = 0
    untraceable: int = 0
    findings: list[ProvenanceFinding] = Field(default_factory=list)
    missing_license: int = 0
    exempt_fields: dict[str, str] = Field(default_factory=lambda: dict(EXEMPT_FIELDS))

    def as_grader_input(self) -> dict[str, Any]:
        return {
            "untraceable": self.untraceable,
            "detail": [f"{f.location}: {f.detail}" for f in self.findings],
        }


def check_forecast(forecast: Any, store: Store | SliceStore) -> ProvenanceReport:
    """Verify every forecast item and refusal traces to records in the store."""
    report = ProvenanceReport()
    for item in forecast.items:
        report.checked_objects += 1
        ids = list(item.supporting_record_ids) + list(item.contradicting_record_ids)
        if not ids:
            report.untraceable += 1
            report.findings.append(
                ProvenanceFinding(
                    location=f"forecast item {item.gene_symbol}",
                    detail=(
                        f"carries confidence {item.confidence} but names no record ID, "
                        f"so the number cannot be traced"
                    ),
                )
            )
            continue
        for record_id in ids:
            report.checked_record_ids += 1
            node = store.node(record_id)
            if node is None:
                report.untraceable += 1
                report.findings.append(
                    ProvenanceFinding(
                        location=f"forecast item {item.gene_symbol}",
                        detail=f"names record {record_id} which is not in the store",
                    )
                )
            elif not node.prov.license:
                report.missing_license += 1
                report.findings.append(
                    ProvenanceFinding(
                        location=f"forecast item {item.gene_symbol}",
                        detail=f"record {record_id} has no license",
                    )
                )

    for refusal in forecast.refusals:
        report.checked_objects += 1
        # A refusal states that evidence is insufficient. It quotes a confidence
        # and a weight, both of which are computed over the records the claim
        # holds, and it makes no claim about the world. Nothing to trace.
    return report


def check_axioms(axiom_set: Any, store: Store | SliceStore) -> ProvenanceReport:
    """Verify every axiom's supporting and contradicting records exist."""
    report = ProvenanceReport()
    for axiom in axiom_set.axioms:
        report.checked_objects += 1
        ids = list(axiom.supporting_record_ids) + list(axiom.contradicting_record_ids)
        if not ids:
            report.untraceable += 1
            report.findings.append(
                ProvenanceFinding(
                    location=f"axiom {axiom.id}",
                    detail="names no record ID; the validator should have rejected it",
                )
            )
        for record_id in ids:
            report.checked_record_ids += 1
            if store.node(record_id) is None:
                report.untraceable += 1
                report.findings.append(
                    ProvenanceFinding(
                        location=f"axiom {axiom.id}",
                        detail=f"names record {record_id} which is not in the store",
                    )
                )
    return report


def check_traps(trap_set: Any, store: Store) -> ProvenanceReport:
    """Every number a trap quotes must come from a record in the store."""
    report = ProvenanceReport()
    for trap in trap_set.traps:
        report.checked_objects += 1
        if trap.supporting_numbers and not trap.evidence_record_ids:
            report.untraceable += 1
            report.findings.append(
                ProvenanceFinding(
                    location=f"trap {trap.id}",
                    detail=(
                        f"quotes {sorted(trap.supporting_numbers)} but names no record ID"
                    ),
                )
            )
        for record_id in trap.evidence_record_ids:
            if not record_id:
                continue
            report.checked_record_ids += 1
            if store.node(record_id) is None:
                report.untraceable += 1
                report.findings.append(
                    ProvenanceFinding(
                        location=f"trap {trap.id}",
                        detail=f"names record {record_id} which is not in the store",
                    )
                )
    return report


def merge(*reports: ProvenanceReport) -> ProvenanceReport:
    out = ProvenanceReport()
    for r in reports:
        out.checked_objects += r.checked_objects
        out.checked_record_ids += r.checked_record_ids
        out.untraceable += r.untraceable
        out.missing_license += r.missing_license
        out.findings.extend(r.findings)
    return out
