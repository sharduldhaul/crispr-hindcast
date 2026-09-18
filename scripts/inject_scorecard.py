"""Inject the generated scorecard into the README between its markers.

The README leads with the scorecard, and the scorecard is generated from
committed results. Keeping it injected rather than hand-copied means the table
in the README cannot drift from the table in eval/results.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- SCORECARD:START -->"
END = "<!-- SCORECARD:END -->"


def main() -> None:
    scorecard = (ROOT / "eval" / "scorecard.md").read_text().strip()
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text()
    if START not in readme or END not in readme:
        raise SystemExit(f"README is missing the {START} / {END} markers")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    readme_path.write_text(f"{head}{START}\n\n{scorecard}\n\n{END}{tail}")
    print(f"injected {len(scorecard.splitlines())} lines into README.md")


if __name__ == "__main__":
    main()
