"""Hard rules 1 and 6: every row traceable, every row licensed.

These run against whatever graph is built, including the committed snapshot, so
they fail if a future contributor adds a source without recording its license or
creates a node without a source record.
"""

from __future__ import annotations

from datetime import date

import pytest

from hindcast.ingest.licenses import SOURCES
from hindcast.models import Node, NodeType, Provenance
from hindcast.store import Store


def test_every_node_and_edge_carries_a_license(toy_store: Store):
    for table in ("node", "edge"):
        rows = toy_store.sql(
            f"SELECT count(*) FROM {table} WHERE license IS NULL OR trim(license) = ''"
        )
        assert rows[0][0] == 0, f"{table} rows exist with no license"


def test_every_node_carries_a_source_id(toy_store: Store):
    rows = toy_store.sql(
        "SELECT count(*) FROM node WHERE source_id IS NULL OR trim(source_id) = ''"
    )
    assert rows[0][0] == 0


def test_every_measurement_has_a_value_and_a_gene(toy_store: Store):
    for node in toy_store.nodes(NodeType.MEASUREMENT):
        assert node.attrs.get("value") is not None, f"{node.id} has no value"
        assert node.attrs.get("gene_id"), f"{node.id} names no gene"
        assert node.attrs.get("assay"), f"{node.id} names no assay"


def test_a_row_cannot_be_created_without_a_license():
    """The model rejects it, so the database never sees it."""
    with pytest.raises(Exception):
        Provenance(source_id="x", license="", publication_date=date(2015, 1, 1))


def test_license_registry_refuses_an_unrecorded_source():
    from hindcast.ingest.licenses import license_of

    with pytest.raises(KeyError):
        license_of("some_source_nobody_recorded")


def test_every_registered_source_states_redistributability():
    for key, spec in SOURCES.items():
        assert spec.license, f"{key} has no license string"
        assert spec.institution, f"{key} names no institution"
        if spec.attribution_required:
            assert spec.attribution, f"{key} requires attribution but states none"


def test_provenance_chain_reaches_a_publication(toy_store: Store):
    chain = toy_store.provenance_chain("meas:pre")
    kinds = {row["type"] for row in chain}
    assert "Publication" in kinds
    pub = next(r for r in chain if r["type"] == "Publication")
    assert pub["pmid"] == "23522779"
    assert pub["license"]


def test_forecast_item_without_records_is_reported_as_untraceable(toy_store: Store):
    from hindcast.agents.forecast import Forecast, ForecastItem
    from hindcast.provenance import check_forecast

    forecast = Forecast(
        cutoff="2018-01-01",
        items=[
            ForecastItem(
                rank_by_confidence=1,
                rank_by_cost_impact=1,
                gene_symbol="MADEUP",
                gene_id="gene:X",
                claim_id="claim:X",
                confidence=0.9,
                implied_modality="SMALL_MOLECULE",
                modality_rationale="",
                cost_weight=10.0,
                cost_impact=9.0,
                evidence_count=0,
                max_supporting_weight=0.0,
                supporting_record_ids=[],
            )
        ],
    )
    report = check_forecast(forecast, toy_store)
    assert report.untraceable == 1
    assert "no record ID" in report.findings[0].detail


def test_forecast_naming_a_missing_record_is_untraceable(toy_store: Store):
    from hindcast.agents.forecast import Forecast, ForecastItem
    from hindcast.provenance import check_forecast

    forecast = Forecast(
        cutoff="2018-01-01",
        items=[
            ForecastItem(
                rank_by_confidence=1,
                rank_by_cost_impact=1,
                gene_symbol="BCL11A",
                gene_id="gene:HGNC:13221",
                claim_id="claim:1",
                confidence=0.8,
                implied_modality="EX_VIVO_SINGLE_EDIT",
                modality_rationale="",
                cost_weight=1.0,
                cost_impact=0.8,
                evidence_count=1,
                max_supporting_weight=1.0,
                supporting_record_ids=["meas:does-not-exist"],
            )
        ],
    )
    report = check_forecast(forecast, toy_store)
    assert report.untraceable == 1
    assert "not in the store" in report.findings[0].detail
