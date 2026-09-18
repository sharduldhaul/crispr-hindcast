"""Ontology resolution: symbols to HGNC, cell lines to Cellosaurus.

Two jobs, both load bearing.

The first is normalization. A screen that reports "gamma-globin" and a GWAS
study that reports "HBG1" are talking about the same gene, and unless both
resolve to the same HGNC ID the evidence never meets. The adversary's alias
attacks exist to test exactly this, so alias resolution is a graph property and
not a string comparison performed at query time.

The second is the leak that SCHEMA.md describes. Gene nodes are built from the
full HGNC release and dated by `date_approved_reserved`, so the presence of a
gene node reflects the gene universe rather than the corpus, and a symbol coined
after T is absent from a slice at T.

Anything that does not resolve is flagged, never guessed. A screen hit whose
symbol cannot be resolved becomes an exclusion with a reason, and the ingestion
metric reports it.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from pathlib import Path

from hindcast.models import Exclusion

#: Cell system classes, coarsest to most relevant. The method signature reads
#: this, not the cell line name. See METHODOLOGY.md for the weights.
SYSTEM_CLASSES = (
    "primary_human_hspc",
    "human_erythroid_progenitor_line",
    "human_immortalized_line",
    "human_cancer_line",
    "mouse_model",
    "mouse_line",
    "non_human_other",
    "cell_free_or_unspecified",
)

#: Cellosaurus accessions whose system class cannot be read off the ontology
#: category alone, because the category says "Transformed cell line" for both an
#: erythroid progenitor model and an unrelated immortalized line. The
#: distinction matters more than any other term in the weighting function, so it
#: is stated explicitly rather than inferred.
KNOWN_SYSTEMS: dict[str, str] = {
    "CVCL_VI06": "human_erythroid_progenitor_line",  # HUDEP-2
    "CVCL_VI05": "human_erythroid_progenitor_line",  # HUDEP-1
    "CVCL_0004": "human_cancer_line",  # K-562, CML
    "CVCL_0001": "human_cancer_line",  # HEL, erythroleukemia
    "CVCL_0379": "human_cancer_line",  # KU812
    "CVCL_0559": "human_cancer_line",  # TF-1
    "CVCL_0045": "human_immortalized_line",  # HEK293
    "CVCL_0030": "human_cancer_line",  # HeLa
}

#: Names that mean primary human CD34+ cells or their erythroid derivatives.
#: Primary cells have no Cellosaurus accession, so they are matched by name.
PRIMARY_HSPC_TERMS = (
    "cd34",
    "hspc",
    "primary human erythroid",
    "primary erythroid",
    "peripheral blood stem",
    "mobilized peripheral blood",
    "bone marrow cd34",
    "cord blood",
    "hematopoietic stem and progenitor",
    "haematopoietic stem and progenitor",
)

MOUSE_TERMS = ("mouse", "murine", "mus musculus", "m. musculus")


@dataclass
class GeneRecord:
    hgnc_id: str
    symbol: str
    name: str
    approved: date | None
    aliases: tuple[str, ...]
    prev_symbols: tuple[str, ...]
    ensembl_gene_id: str | None
    entrez_id: str | None
    locus_type: str
    location: str | None
    gene_family: str


@dataclass
class CellRecord:
    accession: str
    name: str
    category: str | None
    system_class: str
    species: tuple[str, ...]
    diseases: tuple[str, ...]


def _parse_hgnc_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _split(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in (raw or "").split("|") if p.strip())


@dataclass
class OntologyIndex:
    """Loaded once, queried everywhere. Built from the committed raw releases."""

    hgnc_path: Path
    cellosaurus_path: Path | None = None
    exclusions: list[Exclusion] = field(default_factory=list)

    @cached_property
    def genes(self) -> dict[str, GeneRecord]:
        out: dict[str, GeneRecord] = {}
        with self.hgnc_path.open() as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                hgnc_id = (row.get("hgnc_id") or "").strip()
                symbol = (row.get("symbol") or "").strip()
                if not hgnc_id or not symbol:
                    continue
                approved = _parse_hgnc_date(row.get("date_approved_reserved", ""))
                if approved is None:
                    # No approval date means no defensible effective_date, so the
                    # gene cannot be placed in time and is excluded rather than
                    # given a guessed date. Counted in the exclusions table.
                    self.exclusions.append(
                        Exclusion(
                            source="hgnc",
                            source_id=hgnc_id,
                            reason="unresolvable_date",
                            detail=f"{symbol}: no date_approved_reserved in HGNC release",
                        )
                    )
                    continue
                out[hgnc_id] = GeneRecord(
                    hgnc_id=hgnc_id,
                    symbol=symbol,
                    name=(row.get("name") or "").strip(),
                    approved=approved,
                    aliases=_split(row.get("alias_symbol", "")),
                    prev_symbols=_split(row.get("prev_symbol", "")),
                    ensembl_gene_id=(row.get("ensembl_gene_id") or "").strip() or None,
                    entrez_id=(row.get("entrez_id") or "").strip() or None,
                    locus_type=(row.get("locus_type") or "").strip(),
                    location=(row.get("location") or "").strip() or None,
                    gene_family=(row.get("gene_group") or "").strip(),
                )
        return out

    @cached_property
    def _by_symbol(self) -> dict[str, str]:
        return {g.symbol.upper(): g.hgnc_id for g in self.genes.values()}

    @cached_property
    def _by_alias(self) -> dict[str, list[str]]:
        """Aliases and withdrawn symbols. A list, because aliases collide."""
        out: dict[str, list[str]] = {}
        for gene in self.genes.values():
            for name in (*gene.aliases, *gene.prev_symbols):
                out.setdefault(name.upper(), []).append(gene.hgnc_id)
        return out

    @cached_property
    def _by_entrez(self) -> dict[str, str]:
        return {g.entrez_id: g.hgnc_id for g in self.genes.values() if g.entrez_id}

    @cached_property
    def _by_ensembl(self) -> dict[str, str]:
        return {g.ensembl_gene_id: g.hgnc_id for g in self.genes.values() if g.ensembl_gene_id}

    # -- gene resolution ---------------------------------------------------

    def resolve_gene(
        self, symbol: str | None = None, *, entrez: str | None = None, ensembl: str | None = None
    ) -> GeneRecord | None:
        """Resolve to one gene, or None. Never guesses between two candidates.

        Order of preference: a stable numeric ID, then the current symbol, then
        an unambiguous alias. An ambiguous alias resolves to nothing, because
        picking one of two genes with the same old name is exactly the sort of
        silent error that would put a fabricated number in an output.
        """
        if entrez and (hid := self._by_entrez.get(str(entrez).strip())):
            return self.genes[hid]
        if ensembl and (hid := self._by_ensembl.get(str(ensembl).strip())):
            return self.genes[hid]
        if not symbol:
            return None
        key = symbol.strip().upper()
        if not key:
            return None
        if hid := self._by_symbol.get(key):
            return self.genes[hid]
        candidates = self._by_alias.get(key, [])
        if len(candidates) == 1:
            return self.genes[candidates[0]]
        return None

    def resolution_failure(self, symbol: str | None) -> str:
        """Why a symbol did not resolve, for the exclusions table."""
        key = (symbol or "").strip().upper()
        if not key:
            return "empty symbol"
        n = len(self._by_alias.get(key, []))
        if n > 1:
            return f"ambiguous alias: {key} maps to {n} HGNC IDs"
        return f"unknown symbol: {key}"

    # -- cell line resolution ---------------------------------------------

    @cached_property
    def cells(self) -> dict[str, CellRecord]:
        if not self.cellosaurus_path or not self.cellosaurus_path.exists():
            return {}
        raw = json.loads(self.cellosaurus_path.read_text())
        out: dict[str, CellRecord] = {}
        for acc, rec in raw.items():
            out[acc] = CellRecord(
                accession=acc,
                name=rec.get("name") or acc,
                category=rec.get("category"),
                system_class=self._class_from_cellosaurus(acc, rec),
                species=tuple(s for s in rec.get("species") or [] if s),
                diseases=tuple(
                    d.get("term") for d in rec.get("diseases") or [] if d.get("term")
                ),
            )
        return out

    @staticmethod
    def _class_from_cellosaurus(acc: str, rec: dict) -> str:
        if acc in KNOWN_SYSTEMS:
            return KNOWN_SYSTEMS[acc]
        species = " ".join(str(s).lower() for s in rec.get("species") or [])
        if any(term in species for term in MOUSE_TERMS):
            return "mouse_line"
        if species and "sapiens" not in species and "human" not in species:
            return "non_human_other"
        category = (rec.get("category") or "").lower()
        if "cancer" in category:
            return "human_cancer_line"
        if "transformed" in category or "immortal" in category:
            return "human_immortalized_line"
        if "stem cell" in category or "primary" in category or "finite" in category:
            return "primary_human_hspc"
        return "human_immortalized_line"

    def resolve_cell(
        self, accession: str | None, name: str | None = None, cell_type: str | None = None
    ) -> CellRecord | None:
        if accession and (rec := self.cells.get(accession)):
            return rec
        blob = " ".join(x.lower() for x in (name, cell_type) if x)
        if not blob:
            return None
        # Primary human cells carry no Cellosaurus accession, so they are matched
        # by name against a stated term list. This is the one place a name match
        # decides a class, and it only ever produces the primary-cell class,
        # which the weighting function treats as the strongest system. A false
        # positive here would inflate a weight, so the terms are specific.
        if any(term in blob for term in PRIMARY_HSPC_TERMS):
            return CellRecord(
                accession=accession or f"unregistered:{name or cell_type}",
                name=name or cell_type or "primary human cells",
                category="Primary cells (no Cellosaurus accession)",
                system_class="primary_human_hspc",
                species=("Homo sapiens",),
                diseases=(),
            )
        if any(term in blob for term in MOUSE_TERMS):
            return CellRecord(
                accession=accession or f"unregistered:{name or cell_type}",
                name=name or cell_type or "mouse system",
                category="Mouse system",
                system_class="mouse_model",
                species=("Mus musculus",),
                diseases=(),
            )
        return None
