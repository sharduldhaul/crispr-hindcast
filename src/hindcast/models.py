"""Typed schema for nodes, edges and provenance.

The database enforces provenance and time. These models enforce shape. Every
row that reaches the store passes through `Node` or `Edge`, and every row that
leaves it is rebuilt as one, so a malformed record cannot exist in the graph.

See SCHEMA.md for the reason each type exists.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NodeType(StrEnum):
    GENE = "Gene"
    PERTURBATION = "Perturbation"
    SCREEN = "Screen"
    CELL_CONTEXT = "CellContext"
    PHENOTYPE = "Phenotype"
    MEASUREMENT = "Measurement"
    PUBLICATION = "Publication"
    CLAIM = "Claim"
    MODALITY = "Modality"
    TRIAL = "Trial"


class EdgeType(StrEnum):
    SCREEN_TESTED = "SCREEN_TESTED"
    PERTURBS = "PERTURBS"
    MEASURED_IN = "MEASURED_IN"
    REPORTS = "REPORTS"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    IMPLIES_MODALITY = "IMPLIES_MODALITY"
    ACTS_THROUGH = "ACTS_THROUGH"


class TimeScope(StrEnum):
    """What fills `effective_date`. See SCHEMA.md."""

    DATED = "DATED"
    REFERENCE = "REFERENCE"
    VOCABULARY = "VOCABULARY"


#: The floor date given to project vocabulary, which predates every slice.
VOCABULARY_DATE = date(1, 1, 1)


class CostClass(StrEnum):
    """Therapeutic route cost classes, ordered cheapest route first.

    The order is the ranking order used by the cost lens. It is a stated policy,
    not a measurement. See METHODOLOGY.md.
    """

    SMALL_MOLECULE = "SMALL_MOLECULE"
    IN_VIVO_EDIT = "IN_VIVO_EDIT"
    EX_VIVO_SINGLE_EDIT = "EX_VIVO_SINGLE_EDIT"
    EX_VIVO_MULTI_EDIT = "EX_VIVO_MULTI_EDIT"
    NOT_THERAPEUTIC = "NOT_THERAPEUTIC"


class Provenance(BaseModel):
    """Carried by every node and every edge. No field here is decorative.

    `license` is not optional. A row with no known license cannot be created,
    which is what makes the redistribution scan enforceable rather than advisory.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1, description="Dataset name plus that dataset's record key.")
    license: str = Field(min_length=1, description="License of the source this row came from.")
    time_scope: TimeScope = TimeScope.DATED
    effective_date: date | None = Field(
        default=None, description="The one column the time slice filters on."
    )
    accession: str | None = None
    pmid: str | None = None
    publication_date: date | None = None
    publication_date_online: date | None = None
    publication_date_issue: date | None = None
    ingest_hash: str | None = None

    @field_validator("pmid")
    @classmethod
    def _pmid_is_digits(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v.isdigit():
            raise ValueError(f"pmid must be digits, got {v!r}")
        return v

    @model_validator(mode="after")
    def _resolve_effective_date(self) -> Provenance:
        """Fill and check `effective_date` according to `time_scope`.

        A DATED row with no resolvable date is rejected here rather than loaded
        with a guess. The caller catches this and records an exclusion.
        """
        eff = self.effective_date
        if self.time_scope is TimeScope.VOCABULARY:
            eff = VOCABULARY_DATE
        elif eff is None:
            eff = self.publication_date
        if eff is None:
            raise ValueError(
                f"effective_date unresolvable for source_id={self.source_id!r} "
                f"(time_scope={self.time_scope}); exclude the record instead of guessing"
            )
        object.__setattr__(self, "effective_date", eff)
        return self


def content_hash(payload: Any) -> str:
    """SHA-256 over a normalized source record. Stable across runs and machines."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Stable ID, namespaced by type.")
    type: NodeType
    label: str = Field(min_length=1)
    attrs: dict[str, Any] = Field(default_factory=dict)
    prov: Provenance

    @model_validator(mode="after")
    def _require_type_attrs(self) -> Node:
        required = REQUIRED_ATTRS.get(self.type, ())
        missing = [k for k in required if self.attrs.get(k) is None]
        if missing:
            raise ValueError(f"{self.type} node {self.id!r} missing attrs: {missing}")
        return self


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: EdgeType
    src: str = Field(min_length=1)
    dst: str = Field(min_length=1)
    attrs: dict[str, Any] = Field(default_factory=dict)
    prov: Provenance


#: Attributes without which a node of this type would be unusable downstream.
#: Kept deliberately short: these are the fields the weighting function, the
#: slice filter or the provenance trace actually read.
REQUIRED_ATTRS: dict[NodeType, tuple[str, ...]] = {
    NodeType.GENE: ("hgnc_id", "symbol"),
    NodeType.MEASUREMENT: ("value", "gene_id", "phenotype_id", "assay"),
    NodeType.PUBLICATION: ("pmid",),
    NodeType.SCREEN: ("screen_id",),
    NodeType.CELL_CONTEXT: ("system_class",),
    NodeType.PHENOTYPE: ("family", "directness"),
    NodeType.MODALITY: ("cost_class",),
    NodeType.CLAIM: ("gene_id", "phenotype_id", "direction"),
    NodeType.PERTURBATION: ("perturbation_class",),
    NodeType.TRIAL: ("nct_id",),
}


class Exclusion(BaseModel):
    """A record that was not loaded, and why. Reported in the scorecard."""

    model_config = ConfigDict(extra="forbid")

    source: str
    source_id: str
    reason: Literal[
        "unresolvable_date",
        "unresolved_symbol",
        "unresolved_cell_line",
        "missing_license",
        "out_of_scope",
        "malformed_record",
        "no_numeric_value",
    ]
    detail: str = ""
