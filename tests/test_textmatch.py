"""The title matcher, and the noise it exists to keep out.

Every case here is a record that actually appeared in the corpus or the rule
book run, not an invented example.
"""

from __future__ import annotations

from hindcast.textmatch import SHORT_ALIASES, names_gene, title_named_genes, usable_terms

EIF2AK1_TERMS = [
    "EIF2AK1",
    "HCR",
    "KIAA1369",
    "hHRI",
    "heme-regulated inhibitor",
    "heme-regulated eIF2alpha kinase",
]


def test_short_alias_is_dropped() -> None:
    """HCR is three letters and matches unrelated abbreviations."""
    terms = usable_terms("EIF2AK1", EIF2AK1_TERMS)
    assert "HCR" not in terms
    assert "EIF2AK1" in terms
    assert "KIAA1369" in terms


def test_allowlisted_short_alias_is_kept() -> None:
    """LRF is three letters but it is how the 2016 report names ZBTB7A."""
    assert "LRF" in usable_terms("ZBTB7A", ["ZBTB7A"])
    assert "HRI" in usable_terms("EIF2AK1", EIF2AK1_TERMS)
    # The allowlist stays small; every entry is deliberate.
    assert set(SHORT_ALIASES) == {"ZBTB7A", "EIF2AK1"}


def test_full_text_noise_is_rejected() -> None:
    """Titles the full-text search returned for EIF2AK1 that are not about it.

    These are real records from the pre-2018 HbF tier. Counting them as
    evidence put EIF2AK1's publication support at 30 when it is 2.
    """
    noise = [
        "Isolation and characterization of a Bacillus amyloliquefaciens strain "
        "with zearalenone removal ability",
        "Invited review: Recommendations for reporting intervention studies on "
        "reproductive performance in dairy cattle",
        "The 30-amino-acid deletion in the Nsp2 of highly pathogenic porcine "
        "reproductive and respiratory syndrome virus",
        "Homozygous hemoglobin C disease; report of a case.",
    ]
    for title in noise:
        assert title_named_genes(title, {"EIF2AK1": EIF2AK1_TERMS}) == [], title


def test_genuine_records_are_kept() -> None:
    assert title_named_genes(
        "Erythroid expression of the heme-regulated eIF-2 alpha kinase.",
        {"EIF2AK1": EIF2AK1_TERMS},
    ) == ["EIF2AK1"]


def test_hyphenation_and_spacing_are_folded() -> None:
    """"eIF-2 alpha" and "eIF2alpha" are the same name."""
    assert names_gene(
        "Erythroid expression of the heme-regulated eIF-2 alpha kinase.",
        ["heme-regulated eIF2alpha kinase"],
    )
    assert names_gene("The HBG-1 promoter region", ["HBG1"])
    assert names_gene("HBG 1 and HBG 2 expression", ["HBG2"])


def test_greek_letters_are_folded() -> None:
    """Without this the rule missed both CHD4 papers and dated it to 2019."""
    assert names_gene(
        "Mi2β (CHD4) represses fetal hemoglobin", ["Mi-2beta"]
    )
    assert names_gene("γ-globin silencing", ["gamma-globin"])


def test_negation_excludes_the_gene_it_denies() -> None:
    """The MBD2 paper asserts a role for MBD2 and rules one out for MBD3."""
    title = (
        "Disruption of the MBD2-NuRD complex but not MBD3-NuRD induces "
        "high fetal hemoglobin"
    )
    assert names_gene(title, ["MBD2"])
    assert not names_gene(title, ["MBD3"])


def test_word_boundaries_hold() -> None:
    assert not names_gene("CHD4L is a different protein", ["CHD4"])
    assert not names_gene("xHBG1y", ["HBG1"])
    assert names_gene("CHD4 represses", ["CHD4"])


def test_empty_title_names_nothing() -> None:
    assert title_named_genes("", {"EIF2AK1": EIF2AK1_TERMS}) == []
