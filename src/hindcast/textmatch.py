"""Deciding whether a title names a gene.

This module exists because two different parts of the system have to answer the
same question, and they have to answer it the same way. The rule book asks it to
date a discovery. The literature evidence route asks it to decide whether a
publication counts as support for a gene. If the two used different rules, the
answer key and the evidence would be measuring different things.

Why titles and not the query match. The Europe PMC fetch searches full text, so
a record comes back tagged with every scope gene whose name or alias appears
anywhere in the article. For EIF2AK1, whose HGNC aliases include the
three-letter "HCR", that tagging returned thirty pre-2018 records in the HbF
tier, of which roughly three were about the gene. The rest were a Bacillus
strain, a porcine virus, a dairy cattle reporting guideline, and a run of
conference abstract collections. Counting those as evidence would have made
EIF2AK1 reportable for reasons that have nothing to do with the biology, which
is exactly the kind of support the ingestion is supposed to refuse.

Why not abstracts. Their licenses vary and the redistribution rule forbids
committing them, so the snapshot does not carry them and a rule that needed them
would not be replayable offline.

The rule is blunt in a known direction: it undercounts. A paper that studies a
gene without naming it in the title does not count. That loses real evidence and
it is reported in LIMITATIONS.md. It was chosen over the alternative because the
alternative miscounts in an unknown direction, and an undercount that the
refusal path can see is safer than an overcount it cannot.
"""

from __future__ import annotations

import re

#: Greek letters spelled out. Titles write "Mi2beta" and "Mi2b" and "gamma-globin"
#: and the Greek-letter forms interchangeably, and a matcher that does not fold
#: them is matching typography rather than content.
GREEK: dict[str, str] = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "ζ": "zeta", "θ": "theta", "κ": "kappa",
    "λ": "lambda", "μ": "mu",
    "Α": "alpha", "Β": "beta", "Γ": "gamma", "Δ": "delta",
    "Ε": "epsilon",
}

#: Phrases that negate the gene name that follows them. A title reading
#: "Disruption of the MBD2-NuRD complex but not MBD3-NuRD induces high fetal
#: hemoglobin" asserts a role for MBD2 and denies one for MBD3.
NEGATION_BEFORE = re.compile(
    r"(but\s+not|rather\s+than|independent(?:ly)?\s+of|excluding|without|not)\s*$",
    re.I,
)

#: How far back to look for a negating phrase. Long enough to catch "but not"
#: with a hyphenated complex name after it, short enough that a negation about
#: a different clause earlier in the title does not reach.
NEGATION_WINDOW = 24

#: Shortest alias that may stand in for a gene name. Below this, a three-letter
#: alias is more likely to be an unrelated abbreviation than the gene. The
#: approved HGNC symbol is always kept regardless of length, because it is the
#: name the field agreed on.
MIN_ALIAS_LENGTH = 4

#: Short aliases kept anyway, because this field writes titles with them and
#: dropping them would lose the article that identified the gene. Each entry is
#: here for a named article, not as a general allowance:
#:
#:   ZBTB7A / LRF  - the 2016 report that LRF and BCL11A independently repress
#:                   fetal hemoglobin names the protein only as LRF. Without
#:                   this entry the rule cannot date ZBTB7A at all.
#:   EIF2AK1 / HRI - the 2018 report names the kinase as HRI. The alias that
#:                   caused the full-text noise was HCR, which is not here.
#:
#: This list is short on purpose. A symbol added to it should come with the
#: title that forced it.
SHORT_ALIASES: dict[str, tuple[str, ...]] = {
    "ZBTB7A": ("LRF",),
    "EIF2AK1": ("HRI",),
}


def fold(text: str) -> str:
    """Normalise Greek letters to their spelled-out names."""
    for greek, latin in GREEK.items():
        text = text.replace(greek, latin)
    return text


def usable_terms(symbol: str, terms: list[str]) -> list[str]:
    """The subset of a gene's names that may be matched against a title.

    Keeps the approved symbol unconditionally and drops short aliases, for the
    reason recorded on MIN_ALIAS_LENGTH.
    """
    keep = {symbol, *SHORT_ALIASES.get(symbol, ())}
    for term in terms:
        if term == symbol:
            continue
        if len(term) >= MIN_ALIAS_LENGTH:
            keep.add(term)
    return sorted(keep)


#: Where a name may be broken by a hyphen or a space. Titles write the same
#: protein as "Mi-2beta" and "Mi2beta", and the same kinase as "eIF2alpha
#: kinase" and "eIF-2 alpha kinase". Splitting a name into alphanumeric runs and
#: allowing separators between them treats those as one name. Without this the
#: matcher missed the 1994 article that first described erythroid expression of
#: the EIF2AK1 product, because the title hyphenates "eIF-2".
_SEPARATOR = r"[-\s]*"

#: A run of letters or a run of digits. Names are split on the boundary between
#: them as well as on punctuation, because "Mi2beta" carries no separator at all
#: where the title may put one.
_TOKEN = re.compile(r"[A-Za-z]+|[0-9]+")


def term_pattern(term: str) -> str | None:
    """A regex matching this name, tolerant of hyphenation and spacing.

    The lookarounds are the part that matters: they stop a short symbol being
    matched inside a longer word.
    """
    tokens = _TOKEN.findall(fold(term))
    if not tokens:
        return None
    body = _SEPARATOR.join(re.escape(token) for token in tokens)
    return rf"(?<![0-9A-Za-z]){body}(?![0-9A-Za-z])"


def names_gene(title: str, terms: list[str]) -> bool:
    """Whether the title positively names this gene.

    Four things this has to get right. Word boundaries, so a short symbol is not
    matched inside an unrelated word. Greek letter folding, so "Mi2beta" and the
    Greek-letter spelling are the same name. Separator tolerance, so a
    hyphenated spelling is the same name. And negation, so a title that names a
    gene only to exclude it does not count as naming it.
    """
    folded_title = fold(title)
    for term in terms:
        pattern = term_pattern(term)
        if pattern is None:
            continue
        for match in re.finditer(pattern, folded_title, re.I):
            preceding = folded_title[max(0, match.start() - NEGATION_WINDOW) : match.start()]
            if NEGATION_BEFORE.search(preceding.rstrip()):
                continue
            return True
    return False


def title_named_genes(title: str, terms_by_gene: dict[str, list[str]]) -> list[str]:
    """Every scope gene the title names, sorted for determinism."""
    if not title:
        return []
    return sorted(
        symbol
        for symbol, terms in terms_by_gene.items()
        if names_gene(title, usable_terms(symbol, terms))
    )
