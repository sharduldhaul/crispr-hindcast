"""Frozen scope: the genes and phenotype families this benchmark covers.

This file is project vocabulary, not evidence. It is committed and tagged before
the first evaluation run, so it predates every slice. See SCHEMA.md on
`time_scope = VOCABULARY`.

The gene list is the one stated in the project brief. It is deliberately not
expanded to include post-T discoveries: EIF2AK1 is in the list because the
question "does this gene affect HbF" must be *askable* at every slice, including
slices where the answer is not yet known. A gene being in scope says nothing
about whether pre-T evidence supports it, and the slice controls what evidence
about it is visible.
"""

from __future__ import annotations

import re
from datetime import date

#: Core scope genes, as stated in the project brief.
SCOPE_GENES: tuple[str, ...] = (
    "HBG1",
    "HBG2",
    "HBB",
    "BCL11A",
    "ZBTB7A",
    "CHD4",
    "MBD2",
    "GATAD2A",
    "MTA2",
    "ZNF410",
    "KDM1A",
    "DNMT1",
    "NFIX",
    "HIC2",
    "EIF2AK1",
    "KLF1",
)

#: Genes that round out the NuRD complex, the LRF/BCL11A axis and the known
#: HbF regulators that the scope genes act with. Added because the pre-T test
#: set is otherwise too thin for ranking metrics, which the brief permits.
#: Every one of these was already an HbF-associated gene in the literature
#: before the earliest slice, so their presence encodes nothing about post-T
#: findings.
EXTENDED_SCOPE_GENES: tuple[str, ...] = (
    "HDAC1",
    "HDAC2",
    "RBBP4",
    "RBBP7",
    "CHD3",
    "MTA1",
    "MTA3",
    "GATAD2B",
    "MBD3",
    "GATA1",
    "TAL1",
    "SOX6",
    "KLF3",
    "ZBTB33",
    "MYB",
    "HBS1L",
    "HBE1",
    "HBD",
    "LIN28B",
    "IGF2BP1",
    "NR2C1",
    "NR2C2",
    "SIRT1",
    "ATF4",
    "EIF2AK3",
    "EIF2AK2",
    "EIF2AK4",
    "EIF2S1",
    "HBA1",
    "HBA2",
    "PRMT5",
    "KMT5A",
    "EHMT1",
    "EHMT2",
    "DNMT3A",
    "DNMT3B",
    "TET2",
    "ASH1L",
    "FOXO3",
    "NFE2",
    "ZNF143",
    "CTCF",
    "VHL",
    "EPAS1",
    "SMAD1",
    "SMAD5",
    "ATF2",
    "MAPK1",
    "MAP3K7",
    "PGRMC1",
)

ALL_SCOPE_GENES: tuple[str, ...] = SCOPE_GENES + EXTENDED_SCOPE_GENES

#: Phenotype families. `directness` is the readout-directness term used by the
#: method signature. See METHODOLOGY.md for the coefficients.
PHENOTYPE_FAMILIES: dict[str, dict[str, str]] = {
    "hbf_protein": {
        "family": "HBF",
        "label": "HbF protein level",
        "directness": "direct_protein",
        "note": "HbF measured as protein, by HPLC or equivalent.",
    },
    "f_cell": {
        "family": "HBF",
        "label": "F-cell percentage",
        "directness": "direct_protein",
        "note": "Percentage of erythroid cells staining positive for HbF.",
    },
    "hbg_mrna": {
        "family": "HBF",
        "label": "HBG1/HBG2 transcript level",
        "directness": "transcript",
        "note": "Gamma-globin mRNA, a step removed from the protein that matters.",
    },
    "hbg_reporter": {
        "family": "HBF",
        "label": "HBG reporter or sorted-population readout",
        "directness": "proxy",
        "note": "Reporter constructs and sorted HbF-high populations. A proxy.",
    },
    "erythroid_differentiation": {
        "family": "ERYTHROID",
        "label": "Erythroid differentiation or maturation",
        "directness": "proxy",
        "note": "Differentiation state. Related to HbF but not a measure of it.",
    },
    "cell_fitness": {
        "family": "FITNESS",
        "label": "Cell proliferation or viability",
        "directness": "proxy",
        "note": (
            "Growth and survival. Not an HbF readout at all, but load bearing "
            "for the cost lens: a gene whose loss kills the cell is not a target."
        ),
    },
    "globin_switching": {
        "family": "HBF",
        "label": "Globin switching or HBB/HBG ratio",
        "directness": "transcript",
        "note": "Ratio readouts of the fetal-to-adult switch.",
    },
}

#: Terms that mark a screen or study as measuring the HbF phenotype family.
HBF_PHENOTYPE_TERMS: tuple[str, ...] = (
    "fetal hemoglobin",
    "fetal haemoglobin",
    "hbf",
    "f-cell",
    "f cell",
    "gamma-globin",
    "gamma globin",
    "hbg1",
    "hbg2",
    "globin switching",
    "hemoglobin f",
)

ERYTHROID_TERMS: tuple[str, ...] = (
    "erythroid",
    "erythropoiesis",
    "erythrocyte",
    "hudep",
    "hspc",
    "cd34",
    "hematopoietic stem",
    "haematopoietic stem",
    "haemoglobin",
    "hemoglobin",
    "globin",
)

#: Evaluation slices. The primary run and the two secondary runs.
PRIMARY_SLICE = date(2017, 12, 31)
SECONDARY_SLICES = (date(2014, 12, 31), date(2020, 12, 31))
ALL_SLICES = (SECONDARY_SLICES[0], PRIMARY_SLICE, SECONDARY_SLICES[1])


def _term_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Match terms on word boundaries.

    Substring matching is wrong here and was wrong in an earlier version of this
    file: "f cell" matched inside "of cell proliferation" and pulled several
    hundred unrelated proliferation screens into the HbF phenotype family. Short
    terms like "hbf" and "f-cell" need boundaries or the scope filter silently
    becomes a keyword smear.
    """
    alts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![0-9a-z])(?:" + "|".join(alts) + r")(?![0-9a-z])")


_HBF_RE = _term_pattern(HBF_PHENOTYPE_TERMS)
_ERY_RE = _term_pattern(ERYTHROID_TERMS)


def is_hbf_phenotype(*texts: str | None) -> bool:
    return bool(_HBF_RE.search(" ".join(t.lower() for t in texts if t)))


def is_erythroid_context(*texts: str | None) -> bool:
    return bool(_ERY_RE.search(" ".join(t.lower() for t in texts if t)))

#: Informal and historical names that are not HGNC aliases but appear constantly
#: in the literature and in screen annotations. Project vocabulary, frozen with
#: the rest of this file.
#:
#: The adversary restates queries using these names to test whether the system's
#: performance depends on surface strings. That test is only meaningful if the
#: mapping is available to the system under test as well, so it lives here
#: rather than inside the adversary. Every entry below was standard usage well
#: before the earliest slice, so none of it encodes a post-T finding.
INFORMAL_NAMES: dict[str, tuple[str, ...]] = {
    "gamma-globin": ("HBG1", "HBG2"),
    "gamma globin": ("HBG1", "HBG2"),
    "g-gamma-globin": ("HBG2",),
    "a-gamma-globin": ("HBG1",),
    "hbg": ("HBG1", "HBG2"),
    "fetal globin": ("HBG1", "HBG2"),
    "beta-globin": ("HBB",),
    "beta globin": ("HBB",),
    "delta-globin": ("HBD",),
    "epsilon-globin": ("HBE1",),
    "alpha-globin": ("HBA1", "HBA2"),
    "heme-regulated inhibitor": ("EIF2AK1",),
    "heme-regulated eif2alpha kinase": ("EIF2AK1",),
    "hri": ("EIF2AK1",),
    "lrf": ("ZBTB7A",),
    "pokemon": ("ZBTB7A",),
    "leukemia/lymphoma related factor": ("ZBTB7A",),
    "ctip1": ("BCL11A",),
    "lsd1": ("KDM1A",),
    "aof2": ("KDM1A",),
    "mi-2beta": ("CHD4",),
    "mi2b": ("CHD4",),
    "nurd": ("CHD4", "MBD2", "GATAD2A", "MTA2", "HDAC1", "HDAC2", "RBBP4"),
    "p66alpha": ("GATAD2A",),
    "p66beta": ("GATAD2B",),
    "tr2": ("NR2C1",),
    "tr4": ("NR2C2",),
    "dnmt": ("DNMT1",),
    "setd8": ("KMT5A",),
    "pr-set7": ("KMT5A",),
    "eklf": ("KLF1",),
    "hbs1l-myb": ("HBS1L", "MYB"),
}


def resolve_informal(name: str) -> tuple[str, ...]:
    """Map an informal or historical name to HGNC symbols. Empty if unknown."""
    return INFORMAL_NAMES.get(name.strip().lower(), ())
