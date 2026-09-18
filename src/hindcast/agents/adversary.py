"""ADVERSARY: plant traps before grading, drawn from real failure modes.

Contract. In: the full store and the rule book. Out: a set of traps, each a
named question with a correct answer, and a set of paraphrase attacks. The
adversary runs before the grader and never sees the forecast while building
traps, so the traps are a property of the data rather than of the answer given.

Each trap family corresponds to a way a system of this kind actually fails.

*   `association_without_function`. A gene with strong statistical association
    and no functional role. This is the geometry-failure analogue: something
    that looks right by one measure and is wrong on the thing that matters. The
    examples are not invented, they are the author-reported genes at HbF
    associated loci in this repository's own GWAS data, including two olfactory
    receptors.
*   `pan_essential`. A gene whose loss kills the cell. Raising HbF is no use if
    the cell is dead, so ranking one of these highly is the expensive mistake.
*   `postdates_cutoff`. A question whose answer is not in the pre-T record.
    Refusal is the correct answer and scores as one.
*   `alias_attack` and `paraphrase_attack`. The same question in older symbols
    and informal names, to test whether performance depends on surface strings.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.base import Agent
from hindcast.models import NodeType
from hindcast.scope import INFORMAL_NAMES
from hindcast.store import SliceStore, Store

TrapKind = Literal[
    "association_without_function",
    "pan_essential",
    "postdates_cutoff",
    "contradicted_finding",
]


class Trap(BaseModel):
    """One named trap with a correct answer, set before the forecast is seen."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    gene_symbol: str
    question: str
    correct_answer: Literal["reject", "refuse", "accept"]
    rationale: str
    evidence_record_ids: list[str] = Field(default_factory=list)
    supporting_numbers: dict[str, Any] = Field(default_factory=dict)


class AliasAttack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    canonical_symbol: str
    probe: str
    probe_kind: Literal["hgnc_alias", "withdrawn_symbol", "informal_name"]
    expected_gene_id: str


class TrapSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    traps: list[Trap] = Field(default_factory=list)
    alias_attacks: list[AliasAttack] = Field(default_factory=list)

    def by_kind(self, kind: str) -> list[Trap]:
        return [t for t in self.traps if t.kind == kind]


class Adversary(Agent):
    name = "adversary"

    def run(
        self,
        store: Store,
        slice_store: SliceStore,
        *,
        establishment: dict[str, dict],
        cutoff: date,
    ) -> TrapSet:
        traps: list[Trap] = []

        with self.tool("find_association_without_function") as call:
            got = self._association_traps(store, slice_store, establishment)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} association-without-function traps"
            traps.extend(got)

        with self.tool("find_pan_essential") as call:
            got = self._essentiality_traps(store, slice_store)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} pan-essentiality traps"
            traps.extend(got)

        with self.tool("find_postdates_cutoff", cutoff=cutoff.isoformat()) as call:
            got = self._postdates_traps(establishment, cutoff)
            call.records_out = len(got)
            call.result_summary = f"{len(got)} questions whose answer postdates the cutoff"
            traps.extend(got)

        with self.tool("build_alias_attacks") as call:
            attacks = self._alias_attacks(slice_store, establishment)
            call.records_out = len(attacks)
            call.result_summary = f"{len(attacks)} alias and paraphrase probes"

        trap_set = TrapSet(cutoff=slice_store.cutoff, traps=traps, alias_attacks=attacks)
        self.finish(
            {
                "cutoff": slice_store.cutoff,
                "traps": len(traps),
                "by_kind": {
                    k: len(trap_set.by_kind(k))
                    for k in sorted({t.kind for t in traps})
                },
                "alias_attacks": len(attacks),
                "named_traps": [t.gene_symbol for t in traps],
            }
        )
        return trap_set

    # -- trap families ----------------------------------------------------

    def _association_traps(
        self, store: Store, slice_store: SliceStore, establishment: dict[str, dict]
    ) -> list[Trap]:
        """Genes with a genome-wide significant HbF association and no function.

        Built from the slice, so every trap is one the system could actually
        fall into at this cutoff, and checked against the rule book for whether
        a functional role was ever established at all.
        """
        rows = slice_store.sql(
            """
            SELECT g.label AS symbol,
                   g.id AS gene_id,
                   min(json_extract(m.attrs, '$.p_value')) AS best_p,
                   count(*) AS n,
                   group_concat(m.id) AS record_ids,
                   group_concat(DISTINCT m.accession) AS accessions
              FROM node m
              JOIN node g ON g.id = json_extract(m.attrs, '$.gene_id')
             WHERE m.type = 'Measurement'
               AND json_extract(m.attrs, '$.assay') = 'gwas_association'
               AND json_extract(m.attrs, '$.p_value') < 5e-8
             GROUP BY g.id
             ORDER BY best_p
            """
        )
        out: list[Trap] = []
        for row in rows:
            symbol = row["symbol"]
            entry = establishment.get(symbol)
            # A trap needs the association to be real and the function to be
            # absent from the record entirely, not merely absent before T.
            if entry and entry.get("established"):
                continue
            out.append(
                Trap(
                    id=f"trap:association:{symbol}",
                    kind="association_without_function",
                    gene_symbol=symbol,
                    question=(
                        f"Variation at the {symbol} locus is associated with fetal "
                        f"hemoglobin level at p={row['best_p']:.2e}. Does perturbing "
                        f"{symbol} raise HbF?"
                    ),
                    correct_answer="reject",
                    rationale=(
                        f"{symbol} is the author-reported gene at an HbF-associated "
                        f"locus. The association identifies a region, not a gene, and "
                        f"no publication in the record establishes a regulatory role "
                        f"for {symbol} over an HbF readout. Ranking it as a target "
                        f"mistakes a statistical peak for a mechanism."
                    ),
                    evidence_record_ids=(row["record_ids"] or "").split(",")[:10],
                    supporting_numbers={
                        "best_p_value": row["best_p"],
                        "association_rows": row["n"],
                        "gwas_accessions": (row["accessions"] or "").split(","),
                    },
                )
            )
        return out

    def _essentiality_traps(self, store: Store, slice_store: SliceStore) -> list[Trap]:
        """Genes that are pan-essential in DepMap and have HbF literature.

        DepMap postdates every cutoff used here, so these traps are built from
        the full store: the adversary is allowed to know things the forecaster is
        not, which is the point of an adversary.
        """
        rows = store.sql(
            """
            SELECT g.label AS symbol,
                   g.id AS gene_id,
                   count(*) AS lines,
                   sum(CASE WHEN json_extract(m.attrs,'$.value') <= -1.0 THEN 1 ELSE 0 END)
                       AS essential_lines,
                   avg(json_extract(m.attrs,'$.value')) AS mean_effect,
                   group_concat(m.id) AS record_ids
              FROM node m
              JOIN node g ON g.id = json_extract(m.attrs, '$.gene_id')
             WHERE m.type = 'Measurement'
               AND json_extract(m.attrs, '$.assay') = 'depmap_gene_effect'
             GROUP BY g.id
            HAVING lines >= 100
               AND (essential_lines * 1.0 / lines) >= 0.70
             ORDER BY mean_effect
            """
        )
        out: list[Trap] = []
        for row in rows:
            symbol = row["symbol"]
            fraction = row["essential_lines"] / row["lines"]
            out.append(
                Trap(
                    id=f"trap:essential:{symbol}",
                    kind="pan_essential",
                    gene_symbol=symbol,
                    question=(
                        f"Should {symbol} be ranked as a therapeutic target for HbF "
                        f"induction?"
                    ),
                    correct_answer="reject",
                    rationale=(
                        f"{symbol} scores at or below a gene effect of -1.0 in "
                        f"{row['essential_lines']} of {row['lines']} DepMap cell lines "
                        f"({fraction:.0%}), with a mean effect of {row['mean_effect']:.3f}. "
                        f"Knocking it out kills the cell, so any HbF gain cannot be "
                        f"separated from toxicity and it is not a therapy."
                    ),
                    evidence_record_ids=(row["record_ids"] or "").split(",")[:10],
                    supporting_numbers={
                        "depmap_lines_tested": row["lines"],
                        "lines_below_essential_threshold": row["essential_lines"],
                        "fraction_essential": round(fraction, 4),
                        "mean_gene_effect": round(row["mean_effect"], 4),
                        "essential_threshold": -1.0,
                    },
                )
            )
        return out

    def _postdates_traps(self, establishment: dict[str, dict], cutoff: date) -> list[Trap]:
        """Questions whose answer is not in the pre-cutoff record.

        Refusal is the correct answer. These are the rows that make refusal a
        scored outcome rather than a way of avoiding the scorecard.
        """
        out: list[Trap] = []
        for symbol, entry in sorted(establishment.items()):
            record = entry.get("establishing_record")
            if not entry.get("established") or not record:
                continue
            established_on = date.fromisoformat(record["date"][:10])
            if established_on < cutoff:
                continue
            out.append(
                Trap(
                    id=f"trap:postdates:{symbol}",
                    kind="postdates_cutoff",
                    gene_symbol=symbol,
                    question=(
                        f"Does the evidence available before {cutoff.isoformat()} "
                        f"establish that perturbing {symbol} raises HbF?"
                    ),
                    correct_answer="refuse",
                    rationale=(
                        f"The role of {symbol} was established on "
                        f"{record['date'][:10]} by PMID {record['pmid']}, after the "
                        f"cutoff. A system reading only pre-cutoff evidence should say "
                        f"the evidence does not support the claim. Naming it with "
                        f"confidence would indicate contamination rather than insight."
                    ),
                    # Only name the record if it has a PMID. A preprint in the
                    # rule book can have a DOI and no PMID, and naming
                    # "pub:None" would be an untraceable reference, which is the
                    # thing hard rule 1 forbids.
                    evidence_record_ids=(
                        [f"pub:{record['pmid']}"]
                        if record.get("pmid") and str(record["pmid"]).isdigit()
                        else []
                    ),
                    supporting_numbers={
                        "establishing_date": record["date"][:10],
                        "establishing_pmid": record.get("pmid"),
                        "establishing_doi": record.get("doi"),
                        "days_after_cutoff": (established_on - cutoff).days,
                    },
                )
            )
        return out

    def _alias_attacks(
        self, slice_store: SliceStore, establishment: dict[str, dict]
    ) -> list[AliasAttack]:
        """Restate each gene under names the field used earlier.

        The attack is only meaningful if the mapping is available to the system
        under test too, which it is: alias resolution is a property of the graph
        and the informal names are frozen vocabulary. What is being tested is
        whether the graph actually resolves them, not whether the adversary
        knows a synonym the system does not.
        """
        out: list[AliasAttack] = []
        for symbol in sorted(establishment):
            gene = slice_store.gene_by_symbol(symbol)
            if gene is None:
                continue
            aliases = list(gene.attrs.get("aliases") or [])[:2]
            prev = list(gene.attrs.get("prev_symbols") or [])[:2]
            informal = [k for k, v in INFORMAL_NAMES.items() if symbol in v][:2]
            for probe, kind in (
                *[(a, "hgnc_alias") for a in aliases],
                *[(p, "withdrawn_symbol") for p in prev],
                *[(i, "informal_name") for i in informal],
            ):
                out.append(
                    AliasAttack(
                        id=f"attack:{symbol}:{probe}",
                        canonical_symbol=symbol,
                        probe=probe,
                        probe_kind=kind,  # type: ignore[arg-type]
                        expected_gene_id=gene.id,
                    )
                )
        return out
