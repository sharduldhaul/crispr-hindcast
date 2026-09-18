"""The axiom validator, and the adversary's trap construction.

The validator is the gate hard rule 1 depends on, so its rejections are tested
explicitly rather than exercised incidentally.
"""

from __future__ import annotations

from datetime import date

import pytest

from hindcast.agents.axioms import (
    Axiom,
    AxiomExtractor,
    AxiomSet,
    AxiomValidationError,
    validate_axiom,
)
from hindcast.store import Store

CUTOFF = date(2018, 1, 1)


def base_axiom(**kw) -> Axiom:
    args = dict(
        id="axiom:test",
        kind="functional_hbf",
        statement="TESTGENE loss raises HbF.",
        subject_gene_ids=["gene:HGNC:1"],
        phenotype_id="pheno:hbf_protein",
        direction="increases",
        supporting_record_ids=["meas:1"],
        confidence=0.4,
    )
    args.update(kw)
    return Axiom(**args)


def test_validator_rejects_an_axiom_with_no_supporting_record():
    with pytest.raises(AxiomValidationError) as exc:
        validate_axiom(base_axiom(supporting_record_ids=[]))
    assert "no supporting record" in str(exc.value)


def test_validator_rejects_an_empty_statement():
    with pytest.raises(AxiomValidationError):
        validate_axiom(base_axiom(statement="   "))


def test_validator_rejects_a_direction_without_a_phenotype():
    with pytest.raises(AxiomValidationError) as exc:
        validate_axiom(base_axiom(phenotype_id=None))
    assert "cannot be checked" in str(exc.value)


def test_validator_rejects_confidence_outside_the_unit_interval():
    with pytest.raises(AxiomValidationError):
        validate_axiom(base_axiom(confidence=1.4))
    with pytest.raises(AxiomValidationError):
        validate_axiom(base_axiom(confidence=-0.1))


def test_validator_rejects_an_axiom_with_no_subject_gene():
    with pytest.raises(AxiomValidationError):
        validate_axiom(base_axiom(subject_gene_ids=[]))


def test_validator_accepts_a_corpus_level_axiom_with_no_gene():
    validate_axiom(base_axiom(kind="corpus_level", subject_gene_ids=[]))


def test_an_unknown_direction_is_rejected_by_the_model():
    with pytest.raises(Exception):
        base_axiom(direction="sideways")


def test_axioms_are_applicable_not_prose():
    """`applies_to` is what makes an axiom executable."""
    axiom = base_axiom(scope_conditions={"system_classes": ["primary_human_hspc"]})
    assert axiom.applies_to(gene_id="gene:HGNC:1", system_class="primary_human_hspc")
    assert not axiom.applies_to(gene_id="gene:HGNC:1", system_class="mouse_line")
    assert not axiom.applies_to(gene_id="gene:HGNC:999")


def test_extractor_rejections_are_recorded_not_silent(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as sl:
        result = AxiomExtractor("test-reject").run(sl)
    assert isinstance(result, AxiomSet)
    for axiom in result.axioms:
        validate_axiom(axiom)
    assert isinstance(result.rejected, list)


def test_extractor_only_sees_pre_cutoff_records(toy_store: Store):
    """Every record an axiom names must be inside the slice."""
    with toy_store.open_slice(CUTOFF) as sl:
        result = AxiomExtractor("test-scope").run(sl)
        for axiom in result.axioms:
            for record_id in axiom.supporting_record_ids:
                assert sl.node(record_id) is not None, (
                    f"axiom {axiom.id} names {record_id}, which is not in the slice"
                )


def test_extractor_weights_every_measurement_it_saw(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as sl:
        result = AxiomExtractor("test-weights").run(sl)
        measured = {n.id for n in sl.nodes("Measurement")}
    assert set(result.weights) == measured


def test_trap_answers_are_only_the_three_allowed_values():
    from hindcast.agents.adversary import Trap

    with pytest.raises(Exception):
        Trap(
            id="t",
            kind="pan_essential",
            gene_symbol="X",
            question="?",
            correct_answer="maybe",
            rationale="r",
        )


def test_a_trap_quoting_numbers_must_name_records(toy_store: Store):
    from hindcast.agents.adversary import Trap, TrapSet
    from hindcast.provenance import check_traps

    trap_set = TrapSet(
        cutoff="2018-01-01",
        traps=[
            Trap(
                id="trap:bad",
                kind="pan_essential",
                gene_symbol="X",
                question="?",
                correct_answer="reject",
                rationale="r",
                evidence_record_ids=[],
                supporting_numbers={"fraction_essential": 0.9},
            )
        ],
    )
    report = check_traps(trap_set, toy_store)
    assert report.untraceable == 1
