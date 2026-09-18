"""Normalize each raw source into typed nodes and edges.

One function per source. Each returns an `IngestResult` holding nodes, edges and
exclusions, and each obeys the same three rules:

*   Every number carries the record it came from. A `Measurement` node exists for
    each individual value, keyed by the source's own record identifier, so hard
    rule 1 is satisfied by construction rather than by later checking.
*   Nothing is guessed. A symbol that does not resolve, a date that cannot be
    found, a value that is not numeric: each produces an `Exclusion` with a
    reason, and the ingestion metric reports the counts.
*   Every row gets a license from the registry in `hindcast.ingest.licenses`.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from hindcast.ingest.dates import DateIndex
from hindcast.ingest.licenses import license_of
from hindcast.ingest.ontology import OntologyIndex
from hindcast.models import (
    CostClass,
    Edge,
    EdgeType,
    Exclusion,
    Node,
    NodeType,
    Provenance,
    TimeScope,
    content_hash,
)
from hindcast.scope import (
    ALL_SCOPE_GENES,
    PHENOTYPE_FAMILIES,
    is_erythroid_context,
    is_hbf_phenotype,
)


@dataclass
class IngestResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    exclusions: list[Exclusion] = field(default_factory=list)
    available: int = 0
    available_by_source: dict[str, int] = field(default_factory=dict)

    def avail(self, source: str, n: int = 1) -> None:
        """Count source records considered, at the granularity of the nodes made.

        Counted per source rather than globally, and at the same granularity as
        the rows produced. An earlier version counted one available record per
        screen while producing one node per gene per screen, which made the
        ingestion rate 1.38 and therefore meaningless as a rate. A denominator
        that does not match its numerator is not a metric.
        """
        self.available += n
        self.available_by_source[source] = self.available_by_source.get(source, 0) + n

    def extend(self, other: IngestResult) -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.exclusions.extend(other.exclusions)
        self.available += other.available
        for key, n in other.available_by_source.items():
            self.available_by_source[key] = self.available_by_source.get(key, 0) + n

    def counts(self) -> dict[str, int]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "exclusions": len(self.exclusions),
            "available": self.available,
        }


# --------------------------------------------------------------------------
# identifiers
# --------------------------------------------------------------------------

def gene_id(hgnc_id: str) -> str:
    return f"gene:{hgnc_id}"


def pub_id(pmid: str) -> str:
    return f"pub:{pmid}"


def pheno_id(key: str) -> str:
    return f"pheno:{key}"


def cell_id(accession: str) -> str:
    return f"cell:{accession}"


def modality_id(cost_class: CostClass | str) -> str:
    return f"modality:{cost_class}"


def perturbation_id(cls: str) -> str:
    return f"perturbation:{cls}"


# --------------------------------------------------------------------------
# vocabulary: phenotypes, modalities, perturbation classes
# --------------------------------------------------------------------------

#: Perturbation classes, and the direction of evidence each provides. Kept as
#: vocabulary because the weighting function keys on it. See METHODOLOGY.md.
PERTURBATION_CLASSES: dict[str, str] = {
    "base_edit": "Base editing or knock-in of a defined allele.",
    "knock_in": "Targeted knock-in of a defined sequence.",
    "crispri": "CRISPR interference: transcriptional repression without a cut.",
    "crispra": "CRISPR activation: transcriptional activation without a cut.",
    "knockout": "Nuclease-mediated knockout, typically frameshifting indels.",
    "rnai": "RNA interference knockdown.",
    "overexpression": "Forced expression above the physiological range.",
    "genetic_variant": "A naturally occurring human sequence variant.",
    "unspecified": "The source does not state how the gene was perturbed.",
}


def vocabulary_nodes() -> IngestResult:
    """Phenotype, modality and perturbation nodes. Frozen project vocabulary."""
    res = IngestResult()
    lic = license_of("hindcast_vocabulary")

    def prov(source_id: str) -> Provenance:
        return Provenance(
            source_id=source_id,
            license=lic,
            time_scope=TimeScope.VOCABULARY,
            ingest_hash=content_hash(source_id),
        )

    for key, spec in PHENOTYPE_FAMILIES.items():
        res.nodes.append(
            Node(
                id=pheno_id(key),
                type=NodeType.PHENOTYPE,
                label=spec["label"],
                attrs={
                    "family": spec["family"],
                    "directness": spec["directness"],
                    "note": spec["note"],
                    "key": key,
                },
                prov=prov(f"vocab:phenotype:{key}"),
            )
        )

    from hindcast.cost import COST_WEIGHTS

    for cost_class, weight in COST_WEIGHTS.items():
        res.nodes.append(
            Node(
                id=modality_id(cost_class),
                type=NodeType.MODALITY,
                label=str(cost_class),
                attrs={"cost_class": str(cost_class), "cost_weight": weight},
                prov=prov(f"vocab:modality:{cost_class}"),
            )
        )

    for cls, note in PERTURBATION_CLASSES.items():
        res.nodes.append(
            Node(
                id=perturbation_id(cls),
                type=NodeType.PERTURBATION,
                label=cls,
                attrs={"perturbation_class": cls, "note": note},
                prov=prov(f"vocab:perturbation:{cls}"),
            )
        )
    res.avail("hindcast_vocabulary", len(res.nodes))
    return res


# --------------------------------------------------------------------------
# HGNC: the gene universe
# --------------------------------------------------------------------------

def ingest_hgnc(idx: OntologyIndex) -> IngestResult:
    """Every approved HGNC gene becomes a reference node, dated by approval.

    The whole release is loaded, not only the genes the corpus mentions. That is
    the point: node presence then reflects the gene universe, so it cannot leak
    which genes a later paper turned out to care about. See SCHEMA.md.
    """
    res = IngestResult()
    lic = license_of("hgnc")
    scope = {s.upper() for s in ALL_SCOPE_GENES}
    for gene in idx.genes.values():
        res.avail("hgnc.genes")
        res.nodes.append(
            Node(
                id=gene_id(gene.hgnc_id),
                type=NodeType.GENE,
                label=gene.symbol,
                attrs={
                    "hgnc_id": gene.hgnc_id,
                    "symbol": gene.symbol,
                    "name": gene.name,
                    "aliases": list(gene.aliases),
                    "prev_symbols": list(gene.prev_symbols),
                    "gene_family": gene.gene_family,
                    "locus_type": gene.locus_type,
                    "location": gene.location,
                    "ensembl_gene_id": gene.ensembl_gene_id,
                    "entrez_id": gene.entrez_id,
                    "in_scope": gene.symbol.upper() in scope,
                },
                prov=Provenance(
                    source_id=f"hgnc:{gene.hgnc_id}",
                    accession=gene.hgnc_id,
                    license=lic,
                    time_scope=TimeScope.REFERENCE,
                    effective_date=gene.approved,
                    ingest_hash=content_hash(
                        [gene.hgnc_id, gene.symbol, str(gene.approved), gene.gene_family]
                    ),
                ),
            )
        )
    res.exclusions.extend(idx.exclusions)
    return res


# --------------------------------------------------------------------------
# Europe PMC: publications
# --------------------------------------------------------------------------

def ingest_publications(raw_dir: Path, dates: DateIndex) -> IngestResult:
    """Publication nodes. Bibliographic metadata only, never article text."""
    res = IngestResult()
    lic = license_of("europepmc")
    seen: set[str] = set()
    for name in ("europepmc/scope_literature.json", "europepmc/orcs_publications.json"):
        path = raw_dir / name
        if not path.exists():
            continue
        for rec in json.loads(path.read_text()):
            res.avail("europepmc.publications")
            pmid = (rec.get("pmid") or "").strip()
            if not pmid:
                res.exclusions.append(
                    Exclusion(
                        source="europepmc",
                        source_id=str(rec.get("id") or "unknown"),
                        reason="malformed_record",
                        detail="no PMID; cannot be keyed or cited",
                    )
                )
                continue
            if pmid in seen:
                continue
            resolved = dates.get(pmid)
            if resolved is None:
                res.exclusions.append(
                    Exclusion(
                        source="europepmc",
                        source_id=pmid,
                        reason="unresolvable_date",
                        detail="no firstPublicationDate and no print publication date",
                    )
                )
                continue
            seen.add(pmid)
            res.nodes.append(
                Node(
                    id=pub_id(pmid),
                    type=NodeType.PUBLICATION,
                    label=(rec.get("title") or f"PMID {pmid}")[:300],
                    attrs={
                        "pmid": pmid,
                        "doi": rec.get("doi"),
                        "journal": rec.get("journalTitle"),
                        "author_string": (rec.get("authorString") or "")[:300],
                        "pub_type": rec.get("pubType"),
                        "is_open_access": rec.get("isOpenAccess"),
                        "article_license": rec.get("license"),
                        "cited_by_count": rec.get("citedByCount"),
                        "matched_genes": rec.get("matched_genes") or [],
                        "date_rule": resolved.rule,
                    },
                    prov=Provenance(
                        source_id=f"europepmc:{pmid}",
                        accession=rec.get("doi") or f"PMID:{pmid}",
                        pmid=pmid,
                        license=lic,
                        time_scope=TimeScope.DATED,
                        publication_date=resolved.resolved,
                        publication_date_online=resolved.online,
                        publication_date_issue=resolved.issue,
                        ingest_hash=content_hash([pmid, str(resolved.resolved)]),
                    ),
                )
            )
    return res


# --------------------------------------------------------------------------
# BioGRID ORCS: screens and per-gene scores
# --------------------------------------------------------------------------

#: ORCS phenotype strings that are fitness readouts. These are the ones ORCS
#: actually carries in quantity, and they matter here because a gene whose loss
#: kills the cell is not a therapeutic target however well it raises HbF.
ORCS_FITNESS_PHENOTYPES: frozenset[str] = frozenset(
    {
        "cell proliferation",
        "viability",
        "cell viability",
        "cell death",
        "cell growth",
        "growth",
        "cell fitness",
    }
)

#: ORCS phenotype strings that are differentiation readouts. Only counted when
#: the screen is also in an erythroid context, since differentiation of an
#: unrelated lineage says nothing about globin.
ORCS_DIFFERENTIATION_PHENOTYPES: frozenset[str] = frozenset(
    {"erythroid differentiation", "cell differentiation", "differentiation"}
)

#: How an HbF-family screen's readout maps to a phenotype, most direct first.
#: Only reached when the screen's own text names fetal hemoglobin or gamma
#: globin, checked with `hindcast.scope.is_hbf_phenotype`.
ORCS_HBF_READOUTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("f-cell", "f cell"), "f_cell"),
    (("protein", "hplc", "flow", "stain", "antibody"), "hbf_protein"),
    (("mrna", "transcript", "rna-seq", "expression"), "hbg_mrna"),
    (("reporter", "gfp", "sorted", "sort"), "hbg_reporter"),
)

#: ORCS library "Type" and "Methodology" mapped to perturbation classes.
ORCS_PERTURBATION_MAP: dict[str, str] = {
    "crispri": "crispri",
    "crispra": "crispra",
    "crisprn": "knockout",
    "crispr-cas9": "knockout",
    "knockout": "knockout",
    "knockdown": "crispri",
    "activation": "crispra",
    "inhibition": "crispri",
    "base editing": "base_edit",
    "knock-in": "knock_in",
}


def _clean_phenotype(rec: dict) -> str | None:
    """Map one ORCS screen to a phenotype family, or None if it is out of scope.

    The order of these checks is a correctness fix, not a preference. An earlier
    version mapped the bare ORCS phenotype label "Gene Expression" to HbG mRNA
    and "Protein/peptide Accumulation" to an HbG reporter. Those labels are
    generic, and the mapping invented six hundred pre-2018 HbF measurements out
    of screens about autophagy, virus response and protein trafficking. In a
    benchmark about what the HbF evidence supported at a date, that is
    fabricated evidence.

    So an HbF family is assigned only when the screen's own text names fetal
    hemoglobin or gamma globin. BioGRID ORCS as released carries no such human
    screen, which is a real finding about the source and is reported in
    LIMITATIONS.md rather than papered over.
    """
    label = (rec.get("phenotype") or "").split("[")[0].strip().lower()
    blob = (
        rec.get("phenotype"),
        rec.get("notes"),
        rec.get("screen_rationale"),
        rec.get("title"),
        rec.get("condition"),
    )
    if is_hbf_phenotype(*blob):
        text = " ".join(t.lower() for t in blob if t)
        for terms, pheno in ORCS_HBF_READOUTS:
            if any(term in text for term in terms):
                return pheno
        return "hbg_reporter"
    if label in ORCS_FITNESS_PHENOTYPES:
        return "cell_fitness"
    if label in ORCS_DIFFERENTIATION_PHENOTYPES and is_erythroid_context(
        rec.get("cell_line_name"), rec.get("cell_type_name"), rec.get("title"), rec.get("notes")
    ):
        return "erythroid_differentiation"
    return None


def _orcs_perturbation(rec: dict) -> str:
    for key in ("type", "methodology"):
        raw = (rec.get(key) or "").strip().lower()
        if raw in ORCS_PERTURBATION_MAP:
            return ORCS_PERTURBATION_MAP[raw]
    return "unspecified"


def _numeric(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text == "-":
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    return val if math.isfinite(val) else None


def ingest_orcs(
    raw_dir: Path,
    hits_dir: Path,
    ontology: OntologyIndex,
    dates: DateIndex,
    *,
    scope_only: bool = True,
) -> IngestResult:
    """Screens, the genes they tested, and the score for each scope gene.

    Only rows for genes in scope become `Measurement` nodes, because a
    genome-scale screen carries twenty thousand rows and the benchmark asks
    about sixty-eight genes. `SCREEN_TESTED` edges are written for those genes
    whether or not they scored, which is what makes a negative result readable:
    a gene that was in the library and did not come up is evidence, and a gene
    that was never tested is not.
    """
    res = IngestResult()
    lic = license_of("biogrid_orcs")
    scope_syms = {s.upper() for s in ALL_SCOPE_GENES}
    meta_dir = raw_dir / "orcs"
    if not meta_dir.exists():
        return res

    for meta_path in sorted(meta_dir.glob("screen_*.json")):
        rec = json.loads(meta_path.read_text())
        if rec.get("http_status") != 200:
            continue
        res.avail("biogrid_orcs.screens")
        sid = rec["screen_id"]
        pmid = (rec.get("pmid") or "").strip() or None
        resolved = dates.get(pmid)
        if resolved is None:
            res.exclusions.append(
                Exclusion(
                    source="biogrid_orcs",
                    source_id=f"screen:{sid}",
                    reason="unresolvable_date",
                    detail=f"pmid={pmid or 'none'} not resolvable in Europe PMC",
                )
            )
            continue

        pheno_key = _clean_phenotype(rec)
        if pheno_key is None:
            res.exclusions.append(
                Exclusion(
                    source="biogrid_orcs",
                    source_id=f"screen:{sid}",
                    reason="out_of_scope",
                    detail=f"phenotype {rec.get('phenotype')!r} maps to no phenotype family",
                )
            )
            continue

        cell = ontology.resolve_cell(
            rec.get("cellosaurus_id"), rec.get("cell_line_name"), rec.get("cell_type_name")
        )
        if cell is None:
            res.exclusions.append(
                Exclusion(
                    source="biogrid_orcs",
                    source_id=f"screen:{sid}",
                    reason="unresolved_cell_line",
                    detail=(
                        f"cell line {rec.get('cell_line_name')!r} "
                        f"({rec.get('cellosaurus_id')}) not resolvable"
                    ),
                )
            )
            continue

        pert = _orcs_perturbation(rec)

        def prov(source_id: str, payload: object) -> Provenance:
            return Provenance(
                source_id=source_id,
                accession=f"BIOGRID-ORCS-SCREEN:{sid}",
                pmid=pmid,
                license=lic,
                time_scope=TimeScope.DATED,
                publication_date=resolved.resolved,
                publication_date_online=resolved.online,
                publication_date_issue=resolved.issue,
                ingest_hash=content_hash(payload),
            )

        screen_node_id = f"screen:{sid}"
        res.nodes.append(
            Node(
                id=screen_node_id,
                type=NodeType.SCREEN,
                label=rec.get("banner") or f"ORCS screen {sid}",
                attrs={
                    "screen_id": sid,
                    "title": rec.get("title"),
                    "phenotype_key": pheno_key,
                    "phenotype_raw": rec.get("phenotype"),
                    "screen_rationale": rec.get("screen_rationale"),
                    "library": rec.get("library_name"),
                    "library_source": rec.get("library_source"),
                    "library_size": rec.get("full_dataset_size_n"),
                    "n_hits": rec.get("number_of_hits_n"),
                    "perturbation_class": pert,
                    "enzyme": rec.get("enzyme"),
                    "format": rec.get("format"),
                    "analysis_method": rec.get("analysis_method"),
                    "significance_rule": rec.get("significance"),
                    "experimental_setup": rec.get("experimental_setup"),
                    "duration": rec.get("duration"),
                    "condition": rec.get("condition"),
                    "cell_accession": cell.accession,
                    "system_class": cell.system_class,
                },
                prov=prov(f"biogrid_orcs:screen:{sid}", rec),
            )
        )
        if pmid:
            res.edges.append(
                Edge(
                    id=f"edge:reports:{pmid}:{screen_node_id}",
                    type=EdgeType.REPORTS,
                    src=pub_id(pmid),
                    dst=screen_node_id,
                    prov=prov(f"biogrid_orcs:reports:{sid}", [pmid, sid]),
                )
            )

        hits_path = _find_hits_file(hits_dir, sid)
        if hits_path is None:
            res.exclusions.append(
                Exclusion(
                    source="biogrid_orcs",
                    source_id=f"screen:{sid}",
                    reason="malformed_record",
                    detail="screen metadata present but no hit table in the release",
                )
            )
            continue

        for row in _read_hits(hits_path):
            symbol = (row.get("OFFICIAL_SYMBOL") or "").strip()
            if scope_only and symbol.upper() not in scope_syms:
                continue
            res.avail("biogrid_orcs.scope_gene_rows")
            gene = ontology.resolve_gene(
                symbol, entrez=row.get("IDENTIFIER_ID") if row.get(
                    "IDENTIFIER_TYPE"
                ) == "ENTREZ_GENE" else None
            )
            if gene is None:
                res.exclusions.append(
                    Exclusion(
                        source="biogrid_orcs",
                        source_id=f"screen:{sid}:{symbol}",
                        reason="unresolved_symbol",
                        detail=ontology.resolution_failure(symbol),
                    )
                )
                continue

            gid = gene_id(gene.hgnc_id)
            res.edges.append(
                Edge(
                    id=f"edge:tested:{sid}:{gene.hgnc_id}",
                    type=EdgeType.SCREEN_TESTED,
                    src=screen_node_id,
                    dst=gid,
                    attrs={"library_size": rec.get("full_dataset_size_n")},
                    prov=prov(f"biogrid_orcs:tested:{sid}:{gene.hgnc_id}", [sid, gene.hgnc_id]),
                )
            )

            value = _numeric(row.get("SCORE.1"))
            hit_flag = (row.get("HIT") or "").strip().upper() == "YES"
            if value is None:
                # A tested gene with no numeric score is still evidence of having
                # been tested, which the edge above records. It is not a
                # measurement, and no value is invented for it.
                res.exclusions.append(
                    Exclusion(
                        source="biogrid_orcs",
                        source_id=f"screen:{sid}:{gene.hgnc_id}",
                        reason="no_numeric_value",
                        detail=f"SCORE.1={row.get('SCORE.1')!r} is not numeric",
                    )
                )
                continue

            mid = f"meas:orcs:{sid}:{gene.hgnc_id}"
            res.nodes.append(
                Node(
                    id=mid,
                    type=NodeType.MEASUREMENT,
                    label=f"{gene.symbol} in ORCS screen {sid}",
                    attrs={
                        "value": value,
                        "gene_id": gid,
                        "phenotype_id": pheno_id(pheno_key),
                        "assay": "orcs_screen_score",
                        "score_fields": {
                            k: _numeric(row.get(k))
                            for k in ("SCORE.1", "SCORE.2", "SCORE.3")
                            if _numeric(row.get(k)) is not None
                        },
                        "hit": hit_flag,
                        "symbol_as_reported": symbol,
                        "aliases_as_reported": (row.get("ALIASES") or "").split("|"),
                        "system_class": cell.system_class,
                        "cell_accession": cell.accession,
                        "perturbation_class": pert,
                        "screen_id": sid,
                        "significance_rule": rec.get("significance"),
                    },
                    prov=prov(f"biogrid_orcs:measurement:{sid}:{gene.hgnc_id}", [sid, symbol, value]),
                )
            )
            res.edges.append(
                Edge(
                    id=f"edge:measured_in:{mid}",
                    type=EdgeType.MEASURED_IN,
                    src=mid,
                    dst=cell_id(cell.accession),
                    prov=prov(f"biogrid_orcs:measured_in:{sid}:{gene.hgnc_id}", [mid, cell.accession]),
                )
            )
            res.edges.append(
                Edge(
                    id=f"edge:perturbs:{sid}:{gene.hgnc_id}",
                    type=EdgeType.PERTURBS,
                    src=perturbation_id(pert),
                    dst=gid,
                    prov=prov(f"biogrid_orcs:perturbs:{sid}:{gene.hgnc_id}", [pert, gene.hgnc_id]),
                )
            )
            if pmid:
                res.edges.append(
                    Edge(
                        id=f"edge:reports:{pmid}:{mid}",
                        type=EdgeType.REPORTS,
                        src=pub_id(pmid),
                        dst=mid,
                        prov=prov(f"biogrid_orcs:reports_meas:{sid}:{gene.hgnc_id}", [pmid, mid]),
                    )
                )
    return res


def _find_hits_file(hits_dir: Path, sid: int) -> Path | None:
    if not hits_dir.exists():
        return None
    matches = sorted(hits_dir.glob(f"BIOGRID-ORCS-SCREEN_{sid}-*.screen.tab.txt"))
    return matches[0] if matches else None


def _read_hits(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        return list(csv.DictReader(fh, fieldnames=header, delimiter="\t"))


# --------------------------------------------------------------------------
# cell contexts
# --------------------------------------------------------------------------

def ingest_cell_contexts(
    ontology: OntologyIndex, first_use: dict[str, date]
) -> IngestResult:
    """Cell context nodes, dated by the earliest evidence in the corpus that uses them.

    Cellosaurus does not carry a usable establishment date, so a cell line has no
    intrinsic date to place it in time. Dating a context by the earliest
    publication in this corpus that used it is defensible: the context enters the
    record when the field first reports work in it. A context whose first use
    cannot be dated is excluded, which is why this runs after the evidence
    ingesters rather than before them.
    """
    res = IngestResult()
    lic = license_of("cellosaurus")
    for accession, when in sorted(first_use.items()):
        res.avail("cellosaurus.cell_lines")
        rec = ontology.cells.get(accession)
        if rec is None:
            resolved = ontology.resolve_cell(accession, accession)
            if resolved is None:
                res.exclusions.append(
                    Exclusion(
                        source="cellosaurus",
                        source_id=accession,
                        reason="unresolved_cell_line",
                        detail="accession not in the Cellosaurus snapshot",
                    )
                )
                continue
            rec = resolved
        res.nodes.append(
            Node(
                id=cell_id(accession),
                type=NodeType.CELL_CONTEXT,
                label=rec.name,
                attrs={
                    "system_class": rec.system_class,
                    "accession": accession,
                    "category": rec.category,
                    "species": list(rec.species),
                    "diseases": list(rec.diseases),
                    "first_use_in_corpus": when.isoformat(),
                },
                prov=Provenance(
                    source_id=f"cellosaurus:{accession}",
                    accession=accession,
                    license=lic,
                    time_scope=TimeScope.REFERENCE,
                    effective_date=when,
                    ingest_hash=content_hash([accession, rec.system_class, str(when)]),
                ),
            )
        )
    return res


# --------------------------------------------------------------------------
# GWAS Catalog: human genetic support
# --------------------------------------------------------------------------

#: A human population is a cell context in the schema's sense: it is the system
#: a measurement was made in. It is the strongest system there is, because it is
#: the one the therapy has to work in.
HUMAN_POPULATION_ACCESSION = "population:human"

#: GWAS Catalog EFO traits mapped to this project's phenotype families.
GWAS_TRAIT_MAP: dict[str, str] = {
    "fetal hemoglobin measurement": "hbf_protein",
    "fetal hemoglobin levels": "hbf_protein",
    "f-cell distribution": "f_cell",
    "hbf": "hbf_protein",
}


def _gwas_phenotype(traits: list[str] | None, fallback: str | None) -> str | None:
    for trait in (traits or []) + ([fallback] if fallback else []):
        key = (trait or "").strip().lower()
        if key in GWAS_TRAIT_MAP:
            return GWAS_TRAIT_MAP[key]
    return None


def ingest_gwas(raw_dir: Path, ontology: OntologyIndex, dates: DateIndex) -> IngestResult:
    """Genetic associations to the HbF trait family.

    Each association is one `Measurement` whose value is the negative log10 of
    the reported p-value, with the effect size and the study's ancestry and
    sample size kept alongside. The gene is the author-reported gene at the
    locus, resolved through HGNC.

    A reported gene is an assignment made by the study's authors, not a proven
    causal gene. That uncertainty is recorded on the row as
    `gene_assignment = author_reported` and the weighting function does not
    treat it as if the causal gene were established.
    """
    res = IngestResult()
    lic = license_of("gwas_catalog")
    path = raw_dir / "gwas" / "associations.json"
    if not path.exists():
        return res

    studies_path = raw_dir / "gwas" / "studies.json"
    studies = {}
    if studies_path.exists():
        studies = {s["accessionId"]: s for s in json.loads(studies_path.read_text())}

    for i, assoc in enumerate(json.loads(path.read_text())):
        res.avail("gwas_catalog.associations")
        study = assoc.get("study") or {}
        acc = assoc.get("studyAccession") or study.get("accessionId")
        pmid = str(study.get("pubmedId") or "").strip() or None
        resolved = dates.get(pmid)
        if resolved is None:
            raw_date = (study.get("publicationDate") or "")[:10]
            try:
                parsed = date.fromisoformat(raw_date) if raw_date else None
            except ValueError:
                parsed = None
            if parsed is None:
                res.exclusions.append(
                    Exclusion(
                        source="gwas_catalog",
                        source_id=f"{acc}:{i}",
                        reason="unresolvable_date",
                        detail=f"pmid={pmid or 'none'}, publicationDate={raw_date or 'none'}",
                    )
                )
                continue
            # The catalog's own publication date is used when Europe PMC has no
            # record of the PMID. Recorded on the row so the provenance says
            # which rule produced the date.
            date_rule = "gwas_catalog.publicationDate"
            online = issue = None
        else:
            parsed = resolved.resolved
            online, issue = resolved.online, resolved.issue
            date_rule = resolved.rule

        pheno_key = _gwas_phenotype(assoc.get("efoTraits"), study.get("diseaseTrait"))
        if pheno_key is None:
            res.exclusions.append(
                Exclusion(
                    source="gwas_catalog",
                    source_id=f"{acc}:{i}",
                    reason="out_of_scope",
                    detail=f"traits {assoc.get('efoTraits')} map to no HbF phenotype family",
                )
            )
            continue

        pvalue = assoc.get("pvalue")
        if pvalue in (None, 0):
            mant, expo = assoc.get("pvalueMantissa"), assoc.get("pvalueExponent")
            pvalue = float(mant) * (10 ** int(expo)) if mant and expo is not None else None
        if not pvalue or pvalue <= 0:
            res.exclusions.append(
                Exclusion(
                    source="gwas_catalog",
                    source_id=f"{acc}:{i}",
                    reason="no_numeric_value",
                    detail=f"p-value not usable: {assoc.get('pvalue')!r}",
                )
            )
            continue
        neg_log_p = -math.log10(pvalue)

        reported = [g for lo in assoc.get("loci") or [] for g in lo.get("reportedGenes") or []]
        rsids = [r for lo in assoc.get("loci") or [] for r in lo.get("riskAlleles") or [] if r]
        if not reported:
            res.exclusions.append(
                Exclusion(
                    source="gwas_catalog",
                    source_id=f"{acc}:{i}",
                    reason="unresolved_symbol",
                    detail="association reports no gene at the locus",
                )
            )
            continue

        n_initial = sum(
            a.get("n") or 0 for a in study.get("ancestries") or [] if a.get("type") == "initial"
        )
        ancestries = sorted(
            {g for a in study.get("ancestries") or [] for g in a.get("groups") or [] if g}
        )

        for symbol in sorted(set(reported)):
            res.avail("gwas_catalog.association_gene_rows")
            gene = ontology.resolve_gene(symbol)
            if gene is None:
                res.exclusions.append(
                    Exclusion(
                        source="gwas_catalog",
                        source_id=f"{acc}:{i}:{symbol}",
                        reason="unresolved_symbol",
                        detail=ontology.resolution_failure(symbol),
                    )
                )
                continue
            gid = gene_id(gene.hgnc_id)
            mid = f"meas:gwas:{acc}:{gene.hgnc_id}:{i}"
            prov = Provenance(
                source_id=f"gwas_catalog:{acc}:{i}:{gene.hgnc_id}",
                accession=acc,
                pmid=pmid,
                license=lic,
                time_scope=TimeScope.DATED,
                publication_date=parsed,
                publication_date_online=online,
                publication_date_issue=issue,
                ingest_hash=content_hash([acc, i, gene.hgnc_id, pvalue]),
            )
            res.nodes.append(
                Node(
                    id=mid,
                    type=NodeType.MEASUREMENT,
                    label=f"{gene.symbol} associated with {pheno_key} ({acc})",
                    attrs={
                        "value": neg_log_p,
                        "value_meaning": "negative log10 of the reported association p-value",
                        "gene_id": gid,
                        "phenotype_id": pheno_id(pheno_key),
                        "assay": "gwas_association",
                        "p_value": pvalue,
                        "beta": assoc.get("betaNum"),
                        "beta_unit": assoc.get("betaUnit"),
                        "beta_direction": assoc.get("betaDirection"),
                        "odds_ratio": assoc.get("orPerCopyNum"),
                        "risk_alleles": rsids,
                        "system_class": "human_population",
                        "cell_accession": HUMAN_POPULATION_ACCESSION,
                        "perturbation_class": "genetic_variant",
                        "gene_assignment": "author_reported",
                        "sample_size_initial": n_initial or None,
                        "ancestries": ancestries,
                        "trait_reported": study.get("diseaseTrait"),
                        "efo_traits": assoc.get("efoTraits"),
                        "date_rule": date_rule,
                        "genome_wide_significant": pvalue < 5e-8,
                    },
                    prov=prov,
                )
            )
            res.edges.append(
                Edge(
                    id=f"edge:measured_in:{mid}",
                    type=EdgeType.MEASURED_IN,
                    src=mid,
                    dst=cell_id(HUMAN_POPULATION_ACCESSION),
                    prov=prov,
                )
            )
            res.edges.append(
                Edge(
                    id=f"edge:perturbs:gwas:{acc}:{gene.hgnc_id}:{i}",
                    type=EdgeType.PERTURBS,
                    src=perturbation_id("genetic_variant"),
                    dst=gid,
                    prov=prov,
                )
            )
            if pmid:
                res.edges.append(
                    Edge(
                        id=f"edge:reports:{pmid}:{mid}",
                        type=EdgeType.REPORTS,
                        src=pub_id(pmid),
                        dst=mid,
                        prov=prov,
                    )
                )
    return res


# --------------------------------------------------------------------------
# Open Targets: DepMap essentiality and target-disease evidence
# --------------------------------------------------------------------------

def ingest_depmap(
    raw_dir: Path, ontology: OntologyIndex, *, release_date: date
) -> IngestResult:
    """DepMap gene-effect values, one measurement per gene per cell line.

    These carry the DepMap release date, not a per-experiment date, because that
    is the only date the source supports. The consequence is deliberate and worth
    stating: dated at the release, these rows fall after every evaluation cutoff
    used here, so no slice can see them. They are ground truth for the
    adversary's pan-essentiality trap and for the grader, and pre-T essentiality
    evidence has to come from the dated screens in BioGRID ORCS instead.

    A gene effect of about -1 is the median of known common-essential genes, so
    that is the threshold recorded on each row.
    """
    res = IngestResult()
    lic = license_of("depmap")
    path = raw_dir / "opentargets" / "targets.json"
    if not path.exists():
        return res

    for symbol, target in json.loads(path.read_text()).items():
        if not target:
            continue
        gene = ontology.resolve_gene(symbol, ensembl=target.get("id"))
        if gene is None:
            res.exclusions.append(
                Exclusion(
                    source="depmap",
                    source_id=symbol,
                    reason="unresolved_symbol",
                    detail=ontology.resolution_failure(symbol),
                )
            )
            continue
        gid = gene_id(gene.hgnc_id)
        for tissue in target.get("depMapEssentiality") or []:
            tissue_name = tissue.get("tissueName") or "unspecified"
            for screen in tissue.get("screens") or []:
                res.avail("depmap.gene_effect_rows")
                effect = screen.get("geneEffect")
                if effect is None or not math.isfinite(float(effect)):
                    res.exclusions.append(
                        Exclusion(
                            source="depmap",
                            source_id=f"{symbol}:{screen.get('depmapId')}",
                            reason="no_numeric_value",
                            detail=f"geneEffect={effect!r}",
                        )
                    )
                    continue
                depmap_id = screen.get("depmapId") or "unknown"
                mid = f"meas:depmap:{gene.hgnc_id}:{depmap_id}"
                prov = Provenance(
                    source_id=f"depmap:{gene.hgnc_id}:{depmap_id}",
                    accession=depmap_id,
                    license=lic,
                    time_scope=TimeScope.DATED,
                    publication_date=release_date,
                    ingest_hash=content_hash([gene.hgnc_id, depmap_id, effect]),
                )
                res.nodes.append(
                    Node(
                        id=mid,
                        type=NodeType.MEASUREMENT,
                        label=f"{gene.symbol} gene effect in {screen.get('cellLineName')}",
                        attrs={
                            "value": float(effect),
                            "value_meaning": (
                                "DepMap Chronos gene effect; 0 is no effect and about -1 is "
                                "the median of known common-essential genes"
                            ),
                            "gene_id": gid,
                            "phenotype_id": pheno_id("cell_fitness"),
                            "assay": "depmap_gene_effect",
                            "cell_line_name": screen.get("cellLineName"),
                            "depmap_id": depmap_id,
                            "tissue": tissue_name,
                            "disease_from_source": screen.get("diseaseFromSource"),
                            "expression": screen.get("expression"),
                            "system_class": "human_cancer_line",
                            "cell_accession": f"depmap:{depmap_id}",
                            "perturbation_class": "knockout",
                            "essential_threshold": -1.0,
                            "below_essential_threshold": float(effect) <= -1.0,
                        },
                        prov=prov,
                    )
                )
    return res


def ingest_opentargets_evidence(
    raw_dir: Path, ontology: OntologyIndex, dates: DateIndex, *, release_date: date
) -> IngestResult:
    """Target-disease evidence rows for sickle cell disease and beta-thalassemia.

    Each row is a `Measurement` whose value is the Open Targets evidence score,
    tagged with the data type so the weighting function can tell a genetic
    association from a mouse model from a text-mined literature co-mention.
    Rows are dated by their own publication date where they have one, which is
    what lets genetic evidence enter a slice at the right time.
    """
    res = IngestResult()
    lic = license_of("opentargets")
    path = raw_dir / "opentargets" / "evidence.json"
    if not path.exists():
        return res

    #: Open Targets data types mapped to phenotype families. A target-disease
    #: association is not an HbF measurement, so these rows land on the disease
    #: phenotype rather than being passed off as globin readouts.
    for symbol, per_disease in json.loads(path.read_text()).items():
        gene = ontology.resolve_gene(symbol)
        if gene is None:
            res.exclusions.append(
                Exclusion(
                    source="opentargets",
                    source_id=symbol,
                    reason="unresolved_symbol",
                    detail=ontology.resolution_failure(symbol),
                )
            )
            continue
        gid = gene_id(gene.hgnc_id)
        for efo, disease in per_disease.items():
            rows = (disease.get("evidences") or {}).get("rows") or []
            for row in rows:
                res.avail("opentargets.evidence_rows")
                score = row.get("score")
                if score is None:
                    res.exclusions.append(
                        Exclusion(
                            source="opentargets",
                            source_id=str(row.get("id") or f"{symbol}:{efo}"),
                            reason="no_numeric_value",
                            detail="evidence row has no score",
                        )
                    )
                    continue
                pmids = [str(p) for p in (row.get("literature") or []) if str(p).isdigit()]
                pmid = pmids[0] if pmids else None
                resolved = dates.get(pmid)
                parsed = resolved.resolved if resolved else None
                date_rule = resolved.rule if resolved else None
                if parsed is None:
                    raw = (row.get("publicationDate") or "")[:10]
                    try:
                        parsed = date.fromisoformat(raw) if raw else None
                        date_rule = "opentargets.publicationDate"
                    except ValueError:
                        parsed = None
                if parsed is None and row.get("publicationYear"):
                    # A year alone cannot be placed against a year-end cutoff
                    # without inventing a month, so it is excluded rather than
                    # defaulted. See hindcast.ingest.dates.
                    res.exclusions.append(
                        Exclusion(
                            source="opentargets",
                            source_id=str(row.get("id")),
                            reason="unresolvable_date",
                            detail=(
                                f"only a publication year ({row.get('publicationYear')}) is "
                                f"available; a year cannot be placed against a year-end cutoff"
                            ),
                        )
                    )
                    continue
                if parsed is None:
                    parsed = release_date
                    date_rule = "opentargets.releaseDate"

                eid = str(row.get("id") or content_hash([symbol, efo, score]))
                mid = f"meas:ot:{gene.hgnc_id}:{eid}"
                prov = Provenance(
                    source_id=f"opentargets:{eid}",
                    accession=eid,
                    pmid=pmid,
                    license=lic,
                    time_scope=TimeScope.DATED,
                    publication_date=parsed,
                    ingest_hash=content_hash([eid, gene.hgnc_id, score]),
                )
                res.nodes.append(
                    Node(
                        id=mid,
                        type=NodeType.MEASUREMENT,
                        label=f"{gene.symbol} evidence for {disease.get('name')}",
                        attrs={
                            "value": float(score),
                            "value_meaning": "Open Targets evidence score, 0 to 1",
                            "gene_id": gid,
                            "phenotype_id": pheno_id("erythroid_differentiation"),
                            "assay": f"opentargets_{row.get('datatypeId') or 'unknown'}",
                            "datasource": row.get("datasourceId"),
                            "datatype": row.get("datatypeId"),
                            "disease_efo": efo,
                            "disease_name": disease.get("name"),
                            "variant_rsid": row.get("variantRsId"),
                            "p_value_mantissa": row.get("pValueMantissa"),
                            "p_value_exponent": row.get("pValueExponent"),
                            "beta": row.get("beta"),
                            "odds_ratio": row.get("oddsRatio"),
                            "confidence": row.get("confidence"),
                            "crispr_screen_library": row.get("crisprScreenLibrary"),
                            "cell_type": row.get("cellType"),
                            "system_class": _ot_system_class(row),
                            "cell_accession": HUMAN_POPULATION_ACCESSION
                            if row.get("datatypeId") == "genetic_association"
                            else "unspecified:opentargets",
                            "perturbation_class": _ot_perturbation(row),
                            "date_rule": date_rule,
                        },
                        prov=prov,
                    )
                )
                if pmid:
                    res.edges.append(
                        Edge(
                            id=f"edge:reports:{pmid}:{mid}",
                            type=EdgeType.REPORTS,
                            src=pub_id(pmid),
                            dst=mid,
                            prov=prov,
                        )
                    )
    return res


def _ot_system_class(row: dict) -> str:
    datatype = row.get("datatypeId") or ""
    if datatype in ("genetic_association", "genetic_literature", "clinical"):
        return "human_population"
    if datatype == "animal_model":
        return "mouse_model"
    return "cell_free_or_unspecified"


def _ot_perturbation(row: dict) -> str:
    datatype = row.get("datatypeId") or ""
    if datatype in ("genetic_association", "genetic_literature"):
        return "genetic_variant"
    if datatype == "animal_model":
        return "knockout"
    return "unspecified"


# --------------------------------------------------------------------------
# ClinicalTrials.gov: what has actually been built
# --------------------------------------------------------------------------

#: Intervention text patterns mapped to modality cost classes. Applied to the
#: trial's own intervention names, which is why the mapping can be this blunt.
TRIAL_MODALITY_PATTERNS: tuple[tuple[str, CostClass], ...] = (
    ("exagamglogene", CostClass.EX_VIVO_SINGLE_EDIT),
    ("casgevy", CostClass.EX_VIVO_SINGLE_EDIT),
    ("ctx001", CostClass.EX_VIVO_SINGLE_EDIT),
    ("lovotibeglogene", CostClass.EX_VIVO_SINGLE_EDIT),
    ("lyfgenia", CostClass.EX_VIVO_SINGLE_EDIT),
    ("lentiglobin", CostClass.EX_VIVO_SINGLE_EDIT),
    ("bb305", CostClass.EX_VIVO_SINGLE_EDIT),
    ("gene edit", CostClass.EX_VIVO_SINGLE_EDIT),
    ("crispr", CostClass.EX_VIVO_SINGLE_EDIT),
    ("zinc finger nuclease", CostClass.EX_VIVO_SINGLE_EDIT),
    ("base edit", CostClass.EX_VIVO_SINGLE_EDIT),
    ("gene therapy", CostClass.EX_VIVO_SINGLE_EDIT),
    ("gene transfer", CostClass.EX_VIVO_SINGLE_EDIT),
    ("hydroxyurea", CostClass.SMALL_MOLECULE),
    ("hydroxycarbamide", CostClass.SMALL_MOLECULE),
    ("decitabine", CostClass.SMALL_MOLECULE),
    ("azacitidine", CostClass.SMALL_MOLECULE),
    ("thalidomide", CostClass.SMALL_MOLECULE),
    ("pomalidomide", CostClass.SMALL_MOLECULE),
    ("panobinostat", CostClass.SMALL_MOLECULE),
    ("vorinostat", CostClass.SMALL_MOLECULE),
    ("metformin", CostClass.SMALL_MOLECULE),
    ("benserazide", CostClass.SMALL_MOLECULE),
    ("pyridostigmine", CostClass.SMALL_MOLECULE),
    ("voxelotor", CostClass.SMALL_MOLECULE),
    ("l-glutamine", CostClass.SMALL_MOLECULE),
)


def ingest_trials(raw_dir: Path) -> IngestResult:
    """Trial nodes, dated by first posting, with an inferred modality class."""
    res = IngestResult()
    lic = license_of("clinicaltrials_gov")
    path = raw_dir / "ctgov" / "studies.json"
    if not path.exists():
        return res

    for study in json.loads(path.read_text()):
        res.avail("clinicaltrials_gov.studies")
        proto = study.get("protocolSection") or {}
        ident = proto.get("identificationModule") or {}
        status = proto.get("statusModule") or {}
        design = proto.get("designModule") or {}
        arms = proto.get("armsInterventionsModule") or {}
        sponsor = (proto.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
        conditions = (proto.get("conditionsModule") or {}).get("conditions") or []

        nct = ident.get("nctId")
        if not nct:
            res.exclusions.append(
                Exclusion(
                    source="clinicaltrials_gov",
                    source_id="unknown",
                    reason="malformed_record",
                    detail="record has no NCT ID",
                )
            )
            continue

        posted = (status.get("studyFirstPostDateStruct") or {}).get("date") or ""
        started = (status.get("startDateStruct") or {}).get("date") or ""
        parsed = None
        for raw, _rule in ((posted, "ctgov.studyFirstPostDate"), (started, "ctgov.startDate")):
            if raw and len(raw) >= 10:
                try:
                    parsed = date.fromisoformat(raw[:10])
                    break
                except ValueError:
                    parsed = None
        if parsed is None:
            # A month-precision date cannot be placed against a year-end cutoff
            # without inventing a day, and a trial is not worth a guess.
            res.exclusions.append(
                Exclusion(
                    source="clinicaltrials_gov",
                    source_id=nct,
                    reason="unresolvable_date",
                    detail=f"first post {posted!r} and start {started!r} lack day precision",
                )
            )
            continue

        interventions = arms.get("interventions") or []
        text = " ".join(
            [
                ident.get("briefTitle") or "",
                ident.get("officialTitle") or "",
                *[i.get("name") or "" for i in interventions],
                *[i.get("type") or "" for i in interventions],
            ]
        ).lower()
        modality = None
        for pattern, cost_class in TRIAL_MODALITY_PATTERNS:
            if pattern in text:
                modality = cost_class
                break

        prov = Provenance(
            source_id=f"clinicaltrials_gov:{nct}",
            accession=nct,
            license=lic,
            time_scope=TimeScope.DATED,
            publication_date=parsed,
            ingest_hash=content_hash([nct, posted, started]),
        )
        res.nodes.append(
            Node(
                id=f"trial:{nct}",
                type=NodeType.TRIAL,
                label=(ident.get("briefTitle") or nct)[:300],
                attrs={
                    "nct_id": nct,
                    "status": status.get("overallStatus"),
                    "phases": design.get("phases") or [],
                    "study_type": design.get("studyType"),
                    "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
                    "conditions": conditions,
                    "interventions": [
                        {"type": i.get("type"), "name": i.get("name")} for i in interventions
                    ],
                    "lead_sponsor": sponsor.get("name"),
                    "sponsor_class": sponsor.get("class"),
                    "first_posted": posted or None,
                    "start_date": started or None,
                    "inferred_cost_class": str(modality) if modality else None,
                },
                prov=prov,
            )
        )
        if modality is not None:
            res.edges.append(
                Edge(
                    id=f"edge:implies_modality:{nct}",
                    type=EdgeType.IMPLIES_MODALITY,
                    src=f"trial:{nct}",
                    dst=modality_id(modality),
                    attrs={"basis": "intervention name in the trial record"},
                    prov=prov,
                )
            )
    return res


def human_population_context() -> Node:
    """The human population as a cell context. See `ingest_gwas`."""
    return Node(
        id=cell_id(HUMAN_POPULATION_ACCESSION),
        type=NodeType.CELL_CONTEXT,
        label="Human population (genetic association studies)",
        attrs={
            "system_class": "human_population",
            "accession": HUMAN_POPULATION_ACCESSION,
            "category": "Human population",
            "species": ["Homo sapiens"],
            "diseases": [],
            "note": (
                "The system a genetic association is measured in. The strongest "
                "system available, because it is the one a therapy has to work in."
            ),
        },
        prov=Provenance(
            source_id="vocab:cell:human_population",
            license=license_of("hindcast_vocabulary"),
            time_scope=TimeScope.VOCABULARY,
            ingest_hash=content_hash("vocab:cell:human_population"),
        ),
    )


def depmap_cell_contexts(measurements: list[Node], *, release_date: date) -> IngestResult:
    """Cell contexts for the DepMap lines, dated with the DepMap release."""
    res = IngestResult()
    lic = license_of("depmap")
    seen: dict[str, str] = {}
    for node in measurements:
        if node.attrs.get("assay") != "depmap_gene_effect":
            continue
        acc = node.attrs.get("cell_accession")
        if acc and acc not in seen:
            seen[acc] = node.attrs.get("cell_line_name") or acc
    for acc, name in sorted(seen.items()):
        res.nodes.append(
            Node(
                id=cell_id(acc),
                type=NodeType.CELL_CONTEXT,
                label=name,
                attrs={
                    "system_class": "human_cancer_line",
                    "accession": acc,
                    "category": "DepMap cancer cell line",
                    "species": ["Homo sapiens"],
                    "diseases": [],
                },
                prov=Provenance(
                    source_id=f"depmap:cell:{acc}",
                    accession=acc,
                    license=lic,
                    time_scope=TimeScope.REFERENCE,
                    effective_date=release_date,
                    ingest_hash=content_hash([acc, name]),
                ),
            )
        )
    return res


def unspecified_cell_context() -> Node:
    """A context for evidence whose system the source does not state."""
    return Node(
        id=cell_id("unspecified:opentargets"),
        type=NodeType.CELL_CONTEXT,
        label="System not stated by the source",
        attrs={
            "system_class": "cell_free_or_unspecified",
            "accession": "unspecified:opentargets",
            "category": "Unspecified",
            "species": [],
            "diseases": [],
            "note": (
                "Used where a source reports an association without saying what "
                "system it was measured in. The weighting function gives this the "
                "lowest system weight rather than assuming a system."
            ),
        },
        prov=Provenance(
            source_id="vocab:cell:unspecified",
            license=license_of("hindcast_vocabulary"),
            time_scope=TimeScope.VOCABULARY,
            ingest_hash=content_hash("vocab:cell:unspecified"),
        ),
    )
