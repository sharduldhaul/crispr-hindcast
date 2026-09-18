"""Extract the BioGRID ORCS per-screen hit tables from the bulk release.

The release is a single tar.gz of one file per screen. It is downloaded once to
data/raw/ and expanded here into data/raw/orcs_screens/, both gitignored. The
committed snapshot holds only the normalized rows for genes in scope.

Usage: python scripts/extract_orcs_hits.py [path-to-release.tar.gz]
"""

from __future__ import annotations

import hashlib
import sys
import tarfile
from pathlib import Path

from _fetchlib import RAW, client

URL = (
    "https://downloads.thebiogrid.org/Download/BioGRID-ORCS/Latest-Release/"
    "BIOGRID-ORCS-ALL-homo_sapiens-LATEST.screens.tar.gz"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW / "biogrid_orcs_release.tar.gz"
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL}")
        # The server does not honour range requests, so a partial transfer has
        # to be retried from the start. The gzip check below is what proves the
        # download completed.
        with client(timeout=1800.0) as c, archive.open("wb") as fh:
            with c.stream("GET", URL) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
    out = RAW / "orcs_screens"
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name.endswith(".screen.tab.txt")]
        tf.extractall(out, members=members, filter="data")
    print(f"archive sha256={sha256(archive)}")
    print(f"extracted {len(list(out.glob('*.screen.tab.txt')))} screen tables to {out}")


if __name__ == "__main__":
    main()
