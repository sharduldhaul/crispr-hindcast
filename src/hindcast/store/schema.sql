-- One node table, one edge table. See SCHEMA.md for why.
-- Every row carries the same provenance columns in the same place, so the time
-- slice is one predicate applied once rather than one predicate per table.

PRAGMA journal_mode = DELETE;   -- reproducible single-file output, no -wal residue
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS node (
    id                      TEXT PRIMARY KEY,
    type                    TEXT NOT NULL,
    label                   TEXT NOT NULL,
    attrs                   TEXT NOT NULL DEFAULT '{}',

    -- provenance, not nullable where the rule says so
    source_id               TEXT NOT NULL,
    license                 TEXT NOT NULL,
    time_scope              TEXT NOT NULL,
    effective_date          TEXT NOT NULL,      -- ISO date; the slice filters this
    accession               TEXT,
    pmid                    TEXT,
    publication_date        TEXT,
    publication_date_online TEXT,
    publication_date_issue  TEXT,
    ingest_hash             TEXT,

    CHECK (length(license) > 0),
    CHECK (length(source_id) > 0),
    CHECK (time_scope IN ('DATED', 'REFERENCE', 'VOCABULARY')),
    CHECK (effective_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    CHECK (type IN ('Gene', 'Perturbation', 'Screen', 'CellContext', 'Phenotype',
                    'Measurement', 'Publication', 'Claim', 'Modality', 'Trial'))
);

CREATE TABLE IF NOT EXISTS edge (
    id                      TEXT PRIMARY KEY,
    type                    TEXT NOT NULL,
    src                     TEXT NOT NULL REFERENCES node(id),
    dst                     TEXT NOT NULL REFERENCES node(id),
    attrs                   TEXT NOT NULL DEFAULT '{}',

    source_id               TEXT NOT NULL,
    license                 TEXT NOT NULL,
    time_scope              TEXT NOT NULL,
    effective_date          TEXT NOT NULL,
    accession               TEXT,
    pmid                    TEXT,
    publication_date        TEXT,
    publication_date_online TEXT,
    publication_date_issue  TEXT,
    ingest_hash             TEXT,

    CHECK (length(license) > 0),
    CHECK (length(source_id) > 0),
    CHECK (time_scope IN ('DATED', 'REFERENCE', 'VOCABULARY')),
    CHECK (effective_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    CHECK (type IN ('SCREEN_TESTED', 'PERTURBS', 'MEASURED_IN', 'REPORTS',
                    'SUPPORTS', 'CONTRADICTS', 'SUPERSEDES', 'IMPLIES_MODALITY',
                    'ACTS_THROUGH'))
);

-- Records that were not loaded, and why. Reported in the scorecard's ingestion row.
CREATE TABLE IF NOT EXISTS exclusion (
    source    TEXT NOT NULL,
    source_id TEXT NOT NULL,
    reason    TEXT NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (source, source_id, reason)
);

-- Immutable audit log written by the belief reviser. Append only; there is no
-- UPDATE path in the code and the triggers below make that a property of the
-- database rather than a habit of the caller.
CREATE TABLE IF NOT EXISTS belief_revision (
    seq              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    claim_id         TEXT NOT NULL,
    evidence_id      TEXT,
    evidence_date    TEXT,
    prior_confidence REAL NOT NULL,
    posterior_confidence REAL NOT NULL,
    prior_log_odds   REAL NOT NULL,
    posterior_log_odds REAL NOT NULL,
    weight_applied   REAL NOT NULL,
    direction        TEXT NOT NULL,
    rationale        TEXT NOT NULL DEFAULT ''
);

CREATE TRIGGER IF NOT EXISTS belief_revision_no_update
BEFORE UPDATE ON belief_revision
BEGIN
    SELECT RAISE(ABORT, 'belief_revision is append only');
END;

CREATE TRIGGER IF NOT EXISTS belief_revision_no_delete
BEFORE DELETE ON belief_revision
BEGIN
    SELECT RAISE(ABORT, 'belief_revision is append only');
END;

-- What a slice contained when it was built. Written into the slice database
-- itself so a slice file is self-describing.
CREATE TABLE IF NOT EXISTS slice_manifest (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS node_type_date ON node(type, effective_date);
CREATE INDEX IF NOT EXISTS node_date      ON node(effective_date);
CREATE INDEX IF NOT EXISTS node_pmid      ON node(pmid);
CREATE INDEX IF NOT EXISTS edge_src       ON edge(src, type);
CREATE INDEX IF NOT EXISTS edge_dst       ON edge(dst, type);
CREATE INDEX IF NOT EXISTS edge_date      ON edge(effective_date);
CREATE INDEX IF NOT EXISTS revision_claim ON belief_revision(claim_id, seq);
