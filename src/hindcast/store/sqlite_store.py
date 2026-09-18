"""The graph store, and the time slice enforced at the data layer.

Hard rule 2 says no evidence after T, enforced at the data layer rather than by
prompt instruction. The enforcement here does not filter post-T rows out of
queries. It builds a separate database file containing only the rows visible at
T, then hands out a connection that is read-only and cannot reach any other
database. Post-T rows are absent from every database the connection can see.

Three things hold that shut:

1.  Materialization. `Store.open_slice(T)` creates a fresh database and copies
    in only rows whose `effective_date` is strictly before T. Edges whose
    endpoints did not survive the copy are dropped, so no edge can point at a
    hidden node.
2.  Read-only connection. The slice is reopened over a `file:...?mode=ro` URI,
    so the operating system handle itself refuses writes.
3.  An authorizer that denies `ATTACH`. Without this, a caller inside the slice
    could attach the full database and read everything. With it, the only
    reachable schema is the slice's own. The authorizer also denies every write
    action and every read of a table outside the slice schema.

`tests/test_slice_leak.py` attempts each of these routes and asserts failure.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from hindcast.models import Edge, Exclusion, Node, NodeType, Provenance, TimeScope

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

PROV_COLUMNS = (
    "source_id",
    "license",
    "time_scope",
    "effective_date",
    "accession",
    "pmid",
    "publication_date",
    "publication_date_online",
    "publication_date_issue",
    "ingest_hash",
)

NODE_COLUMNS = ("id", "type", "label", "attrs", *PROV_COLUMNS)
EDGE_COLUMNS = ("id", "type", "src", "dst", "attrs", *PROV_COLUMNS)

#: Tables a slice connection may read. Anything else is denied by the authorizer.
#: `json_each` and `json_tree` are SQLite's built-in table-valued functions, not
#: stored tables. They hold no rows of their own, only the JSON handed to them
#: from a column the authorizer already permitted, so allowing them opens no
#: route to data outside the slice. Alias lookup needs them.
SLICE_READABLE = frozenset(
    {
        "node",
        "edge",
        "slice_manifest",
        "sqlite_master",
        "sqlite_sequence",
        "json_each",
        "json_tree",
    }
)

# sqlite3 authorizer action codes. The stdlib exposes only a few as constants,
# so the ones this module needs are named here.
SQLITE_OK = 0
SQLITE_DENY = 1
SQLITE_SELECT = 21
SQLITE_READ = 20
SQLITE_FUNCTION = 31
SQLITE_RECURSIVE = 33
SQLITE_ATTACH = 24
SQLITE_DETACH = 25
SQLITE_PRAGMA = 19

#: Actions a read-only slice connection legitimately needs.
SLICE_ALLOWED_ACTIONS = frozenset({SQLITE_SELECT, SQLITE_FUNCTION, SQLITE_RECURSIVE})


class SliceLeakError(RuntimeError):
    """Raised when something tries to reach outside a slice."""


class ReadOnlyViolation(RuntimeError):
    """Raised when something tries to write through a slice connection."""


def _iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _row_to_node(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"],
        type=NodeType(row["type"]),
        label=row["label"],
        attrs=json.loads(row["attrs"]),
        prov=_row_to_prov(row),
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        type=row["type"],
        src=row["src"],
        dst=row["dst"],
        attrs=json.loads(row["attrs"]),
        prov=_row_to_prov(row),
    )


def _row_to_prov(row: sqlite3.Row) -> Provenance:
    def d(key: str) -> date | None:
        raw = row[key]
        return date.fromisoformat(raw) if raw else None

    return Provenance(
        source_id=row["source_id"],
        license=row["license"],
        time_scope=TimeScope(row["time_scope"]),
        effective_date=d("effective_date"),
        accession=row["accession"],
        pmid=row["pmid"],
        publication_date=d("publication_date"),
        publication_date_online=d("publication_date_online"),
        publication_date_issue=d("publication_date_issue"),
        ingest_hash=row["ingest_hash"],
    )


@dataclass(frozen=True)
class SliceCounts:
    nodes: int
    edges: int
    dropped_dangling_edges: int


class _Readable:
    """Query surface shared by the full store and a slice.

    Every read path in the project goes through these methods, so a slice and
    the full store are interchangeable to the agents. That is deliberate: an
    agent cannot tell which it holds, and cannot ask for more than this.
    """

    conn: sqlite3.Connection

    # -- nodes ------------------------------------------------------------

    def node(self, node_id: str) -> Node | None:
        row = self.conn.execute("SELECT * FROM node WHERE id = ?", (node_id,)).fetchone()
        return _row_to_node(row) if row else None

    def nodes(
        self,
        type: NodeType | str | None = None,
        *,
        pmid: str | None = None,
        limit: int | None = None,
    ) -> list[Node]:
        sql = "SELECT * FROM node WHERE 1=1"
        args: list[Any] = []
        if type is not None:
            sql += " AND type = ?"
            args.append(str(type))
        if pmid is not None:
            sql += " AND pmid = ?"
            args.append(pmid)
        sql += " ORDER BY effective_date, id"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_node(r) for r in self.conn.execute(sql, args)]

    def measurements_for_gene(self, gene_id: str) -> list[Node]:
        sql = """
            SELECT * FROM node
             WHERE type = 'Measurement'
               AND json_extract(attrs, '$.gene_id') = ?
             ORDER BY effective_date, id
        """
        return [_row_to_node(r) for r in self.conn.execute(sql, (gene_id,))]

    def gene_by_symbol(self, symbol: str) -> Node | None:
        """Resolve a current approved symbol, or an unambiguous alias.

        Alias lookup is what makes the adversary's older-symbol attacks a test
        of the graph and not of string matching. The precedence is what makes it
        correct, and it is worth spelling out because getting it wrong was not
        obvious from the outside.

        An approved symbol always wins over another gene's alias. HGNC lists
        "hBG1" among the aliases of ACSBG1, so a lookup of "HBG1" matches both
        HBG1, where it is the approved symbol, and ACSBG1, where it is an alias.
        An earlier version selected between them with `ORDER BY id LIMIT 1`,
        which compares "gene:HGNC:29567" against "gene:HGNC:4831" as strings and
        therefore returned ACSBG1. Every publication naming gamma globin was
        credited to an acyl-CoA synthetase, which put ACSBG1 at the top of the
        forecast with 509 supporting publications and a confidence of 0.955.

        An alias that several genes share and none of them owns as its approved
        symbol resolves to nothing. Refusing an ambiguous name is the same
        policy the curator applies to ingestion: flag it rather than guess.
        """
        exact = self.conn.execute(
            """
            SELECT * FROM node
             WHERE type = 'Gene'
               AND upper(json_extract(attrs, '$.symbol')) = upper(?)
             ORDER BY id LIMIT 1
            """,
            (symbol,),
        ).fetchone()
        if exact is not None:
            return _row_to_node(exact)

        by_alias = self.conn.execute(
            """
            SELECT * FROM node
             WHERE type = 'Gene'
               AND EXISTS (SELECT 1 FROM json_each(node.attrs, '$.aliases')
                            WHERE upper(json_each.value) = upper(?))
             ORDER BY id LIMIT 2
            """,
            (symbol,),
        ).fetchall()
        if len(by_alias) != 1:
            return None
        return _row_to_node(by_alias[0])

    # -- edges ------------------------------------------------------------

    def edges(
        self,
        *,
        src: str | None = None,
        dst: str | None = None,
        type: str | None = None,
    ) -> list[Edge]:
        sql = "SELECT * FROM edge WHERE 1=1"
        args: list[Any] = []
        for col, val in (("src", src), ("dst", dst), ("type", type)):
            if val is not None:
                sql += f" AND {col} = ?"
                args.append(str(val))
        sql += " ORDER BY effective_date, id"
        return [_row_to_edge(r) for r in self.conn.execute(sql, args)]

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[Node]:
        sql = """
            SELECT n.* FROM node n
              JOIN edge e ON e.dst = n.id
             WHERE e.src = ?
        """
        args: list[Any] = [node_id]
        if edge_type:
            sql += " AND e.type = ?"
            args.append(edge_type)
        sql += " ORDER BY n.effective_date, n.id"
        return [_row_to_node(r) for r in self.conn.execute(sql, args)]

    def acts_through_chain(self, gene_id: str, max_depth: int = 4) -> list[tuple[str, str, int]]:
        """Walk ACTS_THROUGH with a recursive CTE. Depth-limited and cycle-safe."""
        sql = """
            WITH RECURSIVE chain(src, dst, depth, path) AS (
                SELECT src, dst, 1, src || '>' || dst
                  FROM edge WHERE type = 'ACTS_THROUGH' AND src = ?
                UNION ALL
                SELECT e.src, e.dst, c.depth + 1, c.path || '>' || e.dst
                  FROM edge e JOIN chain c ON e.src = c.dst
                 WHERE e.type = 'ACTS_THROUGH'
                   AND c.depth < ?
                   AND instr(c.path, e.dst) = 0
            )
            SELECT src, dst, depth FROM chain ORDER BY depth, src, dst
        """
        return [(r[0], r[1], r[2]) for r in self.conn.execute(sql, (gene_id, max_depth))]

    def provenance_chain(self, node_id: str) -> list[dict[str, Any]]:
        """Every publication reachable from a node, with accession and PMID.

        This is what the frontend's provenance ribbons render and what hard rule 1
        is checked against: a number with no row here cannot be quoted.
        """
        sql = """
            WITH RECURSIVE up(id, depth) AS (
                SELECT ?, 0
                UNION
                SELECT e.src, up.depth + 1 FROM edge e JOIN up ON e.dst = up.id
                 WHERE up.depth < 4
                UNION
                SELECT e.dst, up.depth + 1 FROM edge e JOIN up ON e.src = up.id
                 WHERE up.depth < 4 AND e.type IN ('REPORTS', 'MEASURED_IN')
            )
            SELECT DISTINCT n.id, n.type, n.label, n.accession, n.pmid,
                   n.publication_date, n.license, up.depth
              FROM up JOIN node n ON n.id = up.id
             WHERE n.type IN ('Publication', 'Screen', 'Measurement', 'Trial')
             ORDER BY up.depth, n.id
        """
        cols = ("id", "type", "label", "accession", "pmid", "publication_date", "license", "depth")
        return [dict(zip(cols, r, strict=True)) for r in self.conn.execute(sql, (node_id,))]

    def count(self, table: str = "node") -> int:
        if table not in {"node", "edge", "exclusion", "belief_revision"}:
            raise ValueError(f"not a countable table: {table}")
        return int(self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])

    def max_effective_date(self) -> str | None:
        row = self.conn.execute(
            "SELECT max(effective_date) FROM (SELECT effective_date FROM node "
            "UNION ALL SELECT effective_date FROM edge)"
        ).fetchone()
        return row[0] if row else None

    def sql(self, query: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        """Escape hatch for reporting queries. On a slice this is still bounded by
        the authorizer, so it cannot reach past the slice."""
        return list(self.conn.execute(query, tuple(args)))


class Store(_Readable):
    """Read-write access to the full graph. Held by the loader and the grader.

    Agents that forecast are never given one of these. They are given the result
    of `open_slice`.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_PATH.read_text())

    # -- writing ----------------------------------------------------------

    def add_nodes(self, nodes: Iterable[Node]) -> int:
        rows = [
            (
                n.id,
                str(n.type),
                n.label,
                json.dumps(n.attrs, sort_keys=True, default=str),
                n.prov.source_id,
                n.prov.license,
                str(n.prov.time_scope),
                _iso(n.prov.effective_date),
                n.prov.accession,
                n.prov.pmid,
                _iso(n.prov.publication_date),
                _iso(n.prov.publication_date_online),
                _iso(n.prov.publication_date_issue),
                n.prov.ingest_hash,
            )
            for n in nodes
        ]
        placeholders = ",".join("?" * len(NODE_COLUMNS))
        with self.conn:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO node ({','.join(NODE_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )
        return len(rows)

    def add_edges(self, edges: Iterable[Edge]) -> int:
        rows = [
            (
                e.id,
                str(e.type),
                e.src,
                e.dst,
                json.dumps(e.attrs, sort_keys=True, default=str),
                e.prov.source_id,
                e.prov.license,
                str(e.prov.time_scope),
                _iso(e.prov.effective_date),
                e.prov.accession,
                e.prov.pmid,
                _iso(e.prov.publication_date),
                _iso(e.prov.publication_date_online),
                _iso(e.prov.publication_date_issue),
                e.prov.ingest_hash,
            )
            for e in edges
        ]
        placeholders = ",".join("?" * len(EDGE_COLUMNS))
        with self.conn:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO edge ({','.join(EDGE_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )
        return len(rows)

    def add_exclusions(self, exclusions: Iterable[Exclusion]) -> int:
        rows = [(x.source, x.source_id, x.reason, x.detail) for x in exclusions]
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO exclusion (source, source_id, reason, detail) "
                "VALUES (?,?,?,?)",
                rows,
            )
        return len(rows)

    def log_revision(self, **fields: Any) -> None:
        cols = (
            "run_id",
            "claim_id",
            "evidence_id",
            "evidence_date",
            "prior_confidence",
            "posterior_confidence",
            "prior_log_odds",
            "posterior_log_odds",
            "weight_applied",
            "direction",
            "rationale",
        )
        values = [fields.get(c) for c in cols]
        with self.conn:
            self.conn.execute(
                f"INSERT INTO belief_revision ({','.join(cols)}) "
                f"VALUES ({','.join('?' * len(cols))})",
                values,
            )

    def revisions(self, claim_id: str | None = None, run_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM belief_revision WHERE 1=1"
        args: list[Any] = []
        if claim_id:
            sql += " AND claim_id = ?"
            args.append(claim_id)
        if run_id:
            sql += " AND run_id = ?"
            args.append(run_id)
        sql += " ORDER BY seq"
        return [dict(r) for r in self.conn.execute(sql, args)]

    def exclusions(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM exclusion ORDER BY source, source_id")]

    # -- slicing ----------------------------------------------------------

    def open_slice(self, cutoff: date | str, *, work_dir: Path | str | None = None) -> SliceStore:
        """Materialize and open the evidence visible strictly before `cutoff`.

        The returned object cannot reach this store. See the module docstring.
        """
        cutoff_iso = _iso(cutoff)
        assert cutoff_iso is not None
        work = Path(work_dir) if work_dir else self.path.parent / "slices"
        work.mkdir(parents=True, exist_ok=True)
        slice_path = work / f"slice_{cutoff_iso}.db"
        if slice_path.exists():
            slice_path.unlink()

        counts = self._materialize(slice_path, cutoff_iso)
        return SliceStore(slice_path, cutoff_iso, counts)

    def _materialize(self, slice_path: Path, cutoff_iso: str) -> SliceCounts:
        """Copy pre-cutoff rows into a fresh database, then drop dangling edges.

        Done from a connection on the new file that attaches the full store, so
        the attach happens before any restriction is applied and is detached
        before the slice is handed out.
        """
        con = sqlite3.connect(slice_path)
        try:
            con.executescript(SCHEMA_PATH.read_text())
            # Foreign keys are deferred for the copy only. An edge dated before
            # the cutoff can point at a node dated after it, so the copy would
            # otherwise abort on the very rows this step exists to drop. The
            # constraint is re-checked below, after the drop, and a violation
            # there is fatal.
            con.execute("PRAGMA foreign_keys = OFF")
            con.execute("ATTACH DATABASE ? AS full", (str(self.path),))
            with con:
                con.execute(
                    f"INSERT INTO node ({','.join(NODE_COLUMNS)}) "
                    f"SELECT {','.join(NODE_COLUMNS)} FROM full.node WHERE effective_date < ?",
                    (cutoff_iso,),
                )
                con.execute(
                    f"INSERT INTO edge ({','.join(EDGE_COLUMNS)}) "
                    f"SELECT {','.join(EDGE_COLUMNS)} FROM full.edge WHERE effective_date < ?",
                    (cutoff_iso,),
                )
            con.execute("DETACH DATABASE full")

            # An edge that survived the cutoff may still point at a node that did
            # not. Left in place it would leak the existence of a hidden node.
            with con:
                cur = con.execute(
                    "DELETE FROM edge WHERE src NOT IN (SELECT id FROM node) "
                    "OR dst NOT IN (SELECT id FROM node)"
                )
                dangling = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

            # With the dangling edges gone, referential integrity must hold. This
            # is the check that makes "no edge points at a hidden node" a
            # property of the file rather than a claim about the code above.
            con.execute("PRAGMA foreign_keys = ON")
            violations = con.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise SliceLeakError(
                    f"slice at {cutoff_iso} left {len(violations)} edge(s) pointing at "
                    f"rows outside the slice"
                )

            n = int(con.execute("SELECT count(*) FROM node").fetchone()[0])
            e = int(con.execute("SELECT count(*) FROM edge").fetchone()[0])
            with con:
                con.executemany(
                    "INSERT OR REPLACE INTO slice_manifest (key, value) VALUES (?,?)",
                    [
                        ("cutoff", cutoff_iso),
                        ("nodes", str(n)),
                        ("edges", str(e)),
                        ("dropped_dangling_edges", str(dangling)),
                        ("source_db", self.path.name),
                    ],
                )
            con.execute("VACUUM")
            return SliceCounts(nodes=n, edges=e, dropped_dangling_edges=dangling)
        finally:
            con.close()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class SliceStore(_Readable):
    """The evidence visible strictly before a cutoff date, and nothing else.

    Read-only, cannot attach another database, and contains no post-cutoff rows
    to filter in the first place.
    """

    def __init__(self, path: Path, cutoff: str, counts: SliceCounts) -> None:
        self.path = Path(path)
        self.cutoff = cutoff
        self.counts = counts
        uri = f"file:{self.path}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.set_authorizer(self._authorizer)

    @staticmethod
    def _authorizer(
        action: int, arg1: str | None, arg2: str | None, dbname: str | None, source: str | None
    ) -> int:
        """Deny everything a read of the slice does not need.

        Reads of the slice's own tables are allowed. Attach and detach are
        denied outright, which is what stops a caller reaching the full store.
        Every write action falls through to deny.
        """
        if action == SQLITE_READ:
            return SQLITE_OK if (arg1 or "") in SLICE_READABLE else SQLITE_DENY
        if action in SLICE_ALLOWED_ACTIONS:
            return SQLITE_OK
        return SQLITE_DENY

    def manifest(self) -> dict[str, str]:
        return {r[0]: r[1] for r in self.conn.execute("SELECT key, value FROM slice_manifest")}

    def assert_no_leak(self) -> None:
        """Self-check: nothing in this slice is dated at or after the cutoff."""
        latest = self.max_effective_date()
        if latest is not None and latest >= self.cutoff:
            raise SliceLeakError(
                f"slice cutoff {self.cutoff} contains a row dated {latest}"
            )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> SliceStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"SliceStore(cutoff={self.cutoff}, nodes={self.counts.nodes}, "
            f"edges={self.counts.edges})"
        )
