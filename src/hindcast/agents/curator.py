"""CURATOR: normalize raw records into the graph.

Contract. In: the raw source payloads and the ontology releases. Out: typed
nodes and edges, plus an exclusion for every record that could not be
normalized, and a count of what was available. The target is zero spurious
records, so anything that cannot be resolved is excluded with a reason rather
than repaired by guesswork.

The curator writes no prose into the store. Every string it sets is either a
source's own field, an identifier, or a term from the frozen vocabulary.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.base import Agent
from hindcast.ingest import sources as src
from hindcast.ingest.dates import DateIndex
from hindcast.ingest.ontology import OntologyIndex
from hindcast.models import Exclusion, Node
from hindcast.store import Store

#: The DepMap release the Open Targets snapshot carries, used to date those rows.
#: Stated here rather than inferred, and recorded in DATA_SOURCES.md.
DEPMAP_RELEASE_DATE = date(2024, 11, 15)

#: The Open Targets release the snapshot was taken from.
OPENTARGETS_RELEASE_DATE = date(2025, 6, 17)


class IngestionReport(BaseModel):
    """The ingestion row of the scorecard."""

    model_config = ConfigDict(extra="forbid")

    nodes_loaded: int
    edges_loaded: int
    records_available: int
    excluded: int
    exclusions_by_reason: dict[str, int] = Field(default_factory=dict)
    exclusions_by_source: dict[str, int] = Field(default_factory=dict)
    nodes_by_type: dict[str, int] = Field(default_factory=dict)
    edges_by_type: dict[str, int] = Field(default_factory=dict)
    available_by_source: dict[str, int] = Field(default_factory=dict)
    nodes_by_source: dict[str, int] = Field(default_factory=dict)
    spurious: int = 0
    spurious_detail: list[str] = Field(default_factory=list)

    @property
    def ingestion_rate(self) -> float:
        return self.nodes_loaded / self.records_available if self.records_available else 0.0


class Curator(Agent):
    name = "curator"

    def __init__(
        self,
        run_id: str,
        raw_dir: Path,
        *,
        trajectory_dir: Path | None = None,
    ) -> None:
        super().__init__(run_id, trajectory_dir=trajectory_dir)
        self.raw_dir = Path(raw_dir)
        self.ontology = OntologyIndex(
            hgnc_path=self.raw_dir / "hgnc" / "hgnc_complete_set.tsv",
            cellosaurus_path=self.raw_dir / "cellosaurus" / "cell_lines.json",
        )

    def run(self, store: Store) -> IngestionReport:
        """Normalize and write to the store."""
        result = self.normalize()
        with self.tool("write_store") as call:
            n = store.add_nodes(result.nodes)
            e = store.add_edges(result.edges)
            store.add_exclusions(result.exclusions)
            call.records_out = n + e
            call.result_summary = f"{n} nodes and {e} edges written"
        report = _build_report(result)
        self.finish(
            report.model_dump(),
            inputs={
                "raw_dir": str(self.raw_dir),
                "depmap_release": DEPMAP_RELEASE_DATE.isoformat(),
                "opentargets_release": OPENTARGETS_RELEASE_DATE.isoformat(),
            },
        )
        return report

    def normalize(self) -> src.IngestResult:
        """Normalize the raw payloads into typed nodes and edges, without writing.

        Separate from `run` so the snapshot builder can serialize the result and
        the offline build can load it back without the raw payloads present.
        """
        result = src.IngestResult()

        with self.tool("load_vocabulary") as call:
            vocab = src.vocabulary_nodes()
            call.records_out = len(vocab.nodes)
            call.result_summary = f"{len(vocab.nodes)} frozen vocabulary nodes"
            result.extend(vocab)

        with self.tool("load_hgnc", path="data/raw/hgnc/hgnc_complete_set.tsv") as call:
            genes = src.ingest_hgnc(self.ontology)
            call.records_in = genes.available
            call.records_out = len(genes.nodes)
            call.result_summary = (
                f"{len(genes.nodes)} gene reference nodes, "
                f"{len(genes.exclusions)} excluded for missing approval date"
            )
            result.extend(genes)

        with self.tool("derive_complex_membership", source="hgnc") as call:
            complexes = src.complex_membership_edges(self.ontology)
            call.records_in = complexes.available
            call.records_out = len(complexes.edges)
            call.result_summary = (
                f"{len(complexes.edges)} ACTS_THROUGH edges from "
                f"{complexes.available} shared-complex gene pairs"
            )
            result.extend(complexes)

        with self.tool("resolve_dates", source="europepmc") as call:
            dates = DateIndex.from_raw(self.raw_dir)
            call.records_out = len(dates)
            call.result_summary = f"{len(dates)} PMIDs with a resolvable publication date"

        with self.tool("load_publications") as call:
            pubs = src.ingest_publications(self.raw_dir, dates)
            call.records_in = pubs.available
            call.records_out = len(pubs.nodes)
            call.result_summary = f"{len(pubs.nodes)} publication nodes"
            result.extend(pubs)

        with self.tool("load_biogrid_orcs") as call:
            orcs = src.ingest_orcs(
                self.raw_dir,
                self.raw_dir / "orcs_screens",
                self.ontology,
                dates,
            )
            call.records_in = orcs.available
            call.records_out = len(orcs.nodes)
            call.result_summary = (
                f"{len(orcs.nodes)} screen and measurement nodes, "
                f"{len(orcs.edges)} edges, {len(orcs.exclusions)} exclusions"
            )
            result.extend(orcs)

        with self.tool("load_gwas_catalog") as call:
            gwas = src.ingest_gwas(self.raw_dir, self.ontology, dates)
            call.records_in = gwas.available
            call.records_out = len(gwas.nodes)
            call.result_summary = f"{len(gwas.nodes)} association measurements"
            result.extend(gwas)

        with self.tool("load_depmap", release=DEPMAP_RELEASE_DATE.isoformat()) as call:
            depmap = src.ingest_depmap(
                self.raw_dir, self.ontology, release_date=DEPMAP_RELEASE_DATE
            )
            call.records_in = depmap.available
            call.records_out = len(depmap.nodes)
            call.result_summary = f"{len(depmap.nodes)} gene-effect measurements"
            result.extend(depmap)

        with self.tool("load_opentargets_evidence") as call:
            ot = src.ingest_opentargets_evidence(
                self.raw_dir, self.ontology, dates, release_date=OPENTARGETS_RELEASE_DATE
            )
            call.records_in = ot.available
            call.records_out = len(ot.nodes)
            call.result_summary = f"{len(ot.nodes)} target-disease evidence measurements"
            result.extend(ot)

        with self.tool("load_trials") as call:
            trials = src.ingest_trials(self.raw_dir)
            call.records_in = trials.available
            call.records_out = len(trials.nodes)
            call.result_summary = f"{len(trials.nodes)} trial nodes"
            result.extend(trials)

        with self.tool("load_cell_contexts") as call:
            first_use = _first_use_dates(result.nodes)
            cells = src.ingest_cell_contexts(self.ontology, first_use)
            cells.nodes.append(src.human_population_context())
            cells.nodes.append(src.unspecified_cell_context())
            cells.extend(
                src.depmap_cell_contexts(result.nodes, release_date=DEPMAP_RELEASE_DATE)
            )
            call.records_in = len(first_use)
            call.records_out = len(cells.nodes)
            call.result_summary = f"{len(cells.nodes)} cell context nodes"
            result.extend(cells)

        # Edges whose endpoints were never created point at nothing. They are
        # dropped here and counted, because a dangling edge in the full store
        # would fail the foreign key check at slice time and mask its own cause.
        with self.tool("check_referential_integrity") as call:
            node_ids = {n.id for n in result.nodes}
            keep, dropped = [], []
            for edge in result.edges:
                if edge.src in node_ids and edge.dst in node_ids:
                    keep.append(edge)
                else:
                    missing = [e for e in (edge.src, edge.dst) if e not in node_ids]
                    dropped.append(f"{edge.id} -> missing {missing}")
            result.edges = keep
            call.records_in = len(keep) + len(dropped)
            call.records_out = len(keep)
            call.result_summary = f"{len(dropped)} edges dropped for missing endpoints"
            for detail in dropped[:50]:
                result.exclusions.append(
                    Exclusion(
                        source="graph",
                        source_id=detail.split(" ")[0],
                        reason="malformed_record",
                        detail=detail,
                    )
                )

        return result


def _first_use_dates(nodes: list[Node]) -> dict[str, date]:
    """Earliest dated evidence per cell accession. See `ingest_cell_contexts`."""
    out: dict[str, date] = {}
    for node in nodes:
        acc = node.attrs.get("cell_accession")
        when = node.prov.effective_date
        if not acc or when is None:
            continue
        if acc.startswith(("depmap:", "population:", "unspecified:")):
            continue
        if acc not in out or when < out[acc]:
            out[acc] = when
    return out


def _build_report(result: src.IngestResult) -> IngestionReport:
    by_reason: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for x in result.exclusions:
        by_reason[x.reason] = by_reason.get(x.reason, 0) + 1
        by_source[x.source] = by_source.get(x.source, 0) + 1
    by_type: dict[str, int] = {}
    for n in result.nodes:
        by_type[str(n.type)] = by_type.get(str(n.type), 0) + 1
    edge_type: dict[str, int] = {}
    for e in result.edges:
        edge_type[str(e.type)] = edge_type.get(str(e.type), 0) + 1

    # A spurious record is one the curator created that no source record backs.
    # Every measurement must carry a source_id and a value, and every node must
    # carry a license. The check is run rather than asserted.
    spurious: list[str] = []
    for n in result.nodes:
        if not n.prov.source_id or not n.prov.license:
            spurious.append(f"{n.id}: missing provenance")
        if str(n.type) == "Measurement" and n.attrs.get("value") is None:
            spurious.append(f"{n.id}: measurement with no value")

    nodes_by_source: dict[str, int] = {}
    for n in result.nodes:
        key = n.prov.source_id.split(":")[0]
        nodes_by_source[key] = nodes_by_source.get(key, 0) + 1

    return IngestionReport(
        nodes_loaded=len(result.nodes),
        edges_loaded=len(result.edges),
        records_available=result.available,
        excluded=len(result.exclusions),
        exclusions_by_reason=dict(sorted(by_reason.items())),
        exclusions_by_source=dict(sorted(by_source.items())),
        nodes_by_type=dict(sorted(by_type.items())),
        available_by_source=dict(sorted(result.available_by_source.items())),
        nodes_by_source=dict(sorted(nodes_by_source.items())),
        edges_by_type=dict(sorted(edge_type.items())),
        spurious=len(spurious),
        spurious_detail=spurious[:20],
    )
