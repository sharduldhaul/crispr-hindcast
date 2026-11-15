"""Draw the results chart from eval/results/ as an Excalidraw scene.

Contract. The committed result files go in; `diagrams/results.excalidraw` comes
out: precision at 5 for the four forecasters at each cutoff, with the 95%
interval as a whisker and, under each panel, how many of the model's claims
were recalled and how many were grounded. Every figure drawn is read from a
result file, and the scene is byte-identical on every run.

It must never draw a forecaster that did not run: a missing row stops the
script instead of leaving a gap that reads as a zero.

The image in the README is rendered from the scene with the command in
ARCHITECTURE.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from render_scorecard import ROOT, load, load_llm

OUT = ROOT / "diagrams" / "results.excalidraw"

INK = "#1e1e1e"
MUTED = "#868e96"
# (stroke, fill), the colour code every diagram in diagrams/ shares.
VIOLET = ("#6741d9", "#d0bfff")
ORANGE = ("#e8590c", "#ffd8a8")
GREEN = "#2f9e44"
RED = "#e03131"

#: One bar per forecaster: short label, colours and fill style. The three model
#: bars share the model's orange and differ by fill, lightest for no evidence.
BARS = (
    ("rule-based", "rule-based\nsystem", VIOLET, "solid"),
    ("none", "model\nalone", ORANGE, "hachure"),
    ("text", "model +\ntext", ORANGE, "cross-hatch"),
    ("graph", "model +\ngraph tools", ORANGE, "solid"),
)

PANEL_WIDTH = 310
PANEL_GAP = 20
LEFT = 64
TOP = 118  # y of P@5 = 1.0
HEIGHT = 240  # pixels from 0.0 to 1.0
BAR_WIDTH = 56
BAR_GAP = 14


class Scene:
    """Excalidraw elements at fixed coordinates, with ids and seeds from a counter."""

    def __init__(self) -> None:
        self.elements: list[dict[str, Any]] = []

    def _add(self, kind: str, x: float, y: float, w: float, h: float, **fields: Any) -> None:
        n = len(self.elements) + 1
        element: dict[str, Any] = {
            "id": f"r{n}",
            "type": kind,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "angle": 0,
            "strokeColor": INK,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 1,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "index": f"a{n:04d}",
            "roundness": None,
            "seed": 1000 + n * 7919,
            "version": 1,
            "versionNonce": n,
            "isDeleted": False,
            "boundElements": None,
            "updated": 1,
            "created": 1,
            "link": None,
            "locked": False,
        }
        element.update(fields)
        self.elements.append(element)

    def text(
        self,
        x: float,
        y: float,
        w: float,
        content: str,
        size: int = 16,
        color: str = INK,
        align: str = "center",
    ) -> None:
        self._add(
            "text",
            x,
            y,
            w,
            len(content.split("\n")) * size * 1.25,
            strokeColor=color,
            strokeWidth=1,
            text=content,
            originalText=content,
            fontSize=size,
            fontFamily=5,
            textAlign=align,
            verticalAlign="top",
            containerId=None,
            autoResize=False,
            lineHeight=1.25,
        )

    def rect(
        self, x: float, y: float, w: float, h: float, colors: tuple[str, str], fill: str = "solid"
    ) -> None:
        self._add(
            "rectangle",
            x,
            y,
            w,
            h,
            strokeColor=colors[0],
            backgroundColor=colors[1],
            fillStyle=fill,
        )

    def line(
        self,
        points: list[tuple[float, float]],
        color: str = INK,
        width: int = 2,
        dashed: bool = False,
    ) -> None:
        x0, y0 = points[0]
        relative = [[x - x0, y - y0] for x, y in points]
        self._add(
            "line",
            x0,
            y0,
            max(p[0] for p in relative) - min(p[0] for p in relative),
            max(p[1] for p in relative) - min(p[1] for p in relative),
            strokeColor=color,
            strokeWidth=width,
            strokeStyle="dashed" if dashed else "solid",
            roughness=0,
            points=relative,
            startBinding=None,
            endBinding=None,
            startArrowhead=None,
            endArrowhead=None,
            polygon=False,
        )

    def save(self, path: Path) -> None:
        scene = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://github.com/sharduldhaul/crispr-hindcast",
            "elements": self.elements,
            "appState": {
                "viewBackgroundColor": "#ffffff",
                "exportBackground": True,
                "gridSize": None,
            },
            "files": {},
        }
        path.write_text(json.dumps(scene, indent=1) + "\n")


def height_of(value: float) -> float:
    """The y coordinate of a P@5 value."""
    return TOP + HEIGHT * (1 - value)


def cards_by_cutoff(results: list[dict], llm: list[dict]) -> dict[str, dict[str, dict]]:
    """Per cutoff, the row for each bar. Raises if a model row did not run."""
    cutoffs = sorted({r["cutoff"] for r in llm})
    rule_based = {r["cutoff"]: r for r in results if r["ablation"] == "full system"}
    rows: dict[str, dict[str, dict]] = {c: {"rule-based": rule_based[c]} for c in cutoffs}
    for row in llm:
        condition = row["run"]["condition"]
        if row["run"]["status"] != "ran":
            raise SystemExit(f"{row['cutoff']} {condition}: not run, so the chart cannot be drawn")
        rows[row["cutoff"]][condition] = row
    return rows


def draw(rows: dict[str, dict[str, dict]]) -> Scene:
    scene = Scene()
    width = LEFT + len(rows) * PANEL_WIDTH + (len(rows) - 1) * PANEL_GAP
    scene.text(0, 0, width, "Precision at 5: how many of the top 5 forecasts came true", 20)
    scene.text(
        0,
        30,
        width,
        "Bar: share of the 5 highest-confidence claims. Whisker: 95% interval.",
        14,
        MUTED,
    )
    for tick in (0.0, 0.5, 1.0):
        scene.text(0, height_of(tick) - 10, LEFT - 12, f"{tick:.1f}", 14, MUTED, "right")
        scene.line(
            [(LEFT - 6, height_of(tick)), (width, height_of(tick))],
            MUTED,
            1,
            dashed=tick > 0,
        )

    for i, (cutoff, by_bar) in enumerate(rows.items()):
        left = LEFT + i * (PANEL_WIDTH + PANEL_GAP)
        scene.text(left, 70, PANEL_WIDTH, f"Evidence before {cutoff}", 17)
        inset = (PANEL_WIDTH - len(BARS) * BAR_WIDTH - (len(BARS) - 1) * BAR_GAP) / 2
        for j, (key, label, colors, fill) in enumerate(BARS):
            ranking = by_bar[key]["scorecard"]["ranking_by_confidence"]
            value = ranking["precision_at_5"]
            interval = ranking["precision_at_5_interval"]
            x = left + inset + j * (BAR_WIDTH + BAR_GAP)
            # A zero still gets a sliver, so the forecaster reads as present.
            top = min(height_of(value), height_of(0) - 3)
            scene.rect(x, top, BAR_WIDTH, height_of(0) - top, colors, fill)
            mid = x + BAR_WIDTH / 2
            if interval["upper"] > interval["lower"]:
                low, high = height_of(interval["lower"]), height_of(interval["upper"])
                scene.line([(mid, low), (mid, high)], INK, 2)
                scene.line([(mid - 8, high), (mid + 8, high)], INK, 2)
                scene.line([(mid - 8, low), (mid + 8, low)], INK, 2)
            scene.text(x - 8, height_of(0) + 8, BAR_WIDTH + 16, f"{value:.2f}", 18, colors[0])
            scene.text(x - 10, height_of(0) + 34, BAR_WIDTH + 20, label, 13, MUTED)

        note = height_of(0) + 84
        recalled = by_bar["none"]["memorization"]["recalled_rate"]
        grounded = by_bar["graph"]["grounding"]["grounded_claim_rate"]
        scene.line([(left + 14, note + 3), (left + 26, note + 15)], RED, 3)
        scene.line([(left + 26, note + 3), (left + 14, note + 15)], RED, 3)
        scene.text(
            left + 36,
            note,
            PANEL_WIDTH - 36,
            f"model alone: {recalled['numerator']} of {recalled['denominator']} claims recalled",
            14,
            RED,
            "left",
        )
        scene.line(
            [(left + 12, note + 34), (left + 18, note + 40), (left + 29, note + 27)], GREEN, 3
        )
        scene.text(
            left + 36,
            note + 24,
            PANEL_WIDTH - 36,
            f"graph tools: {grounded['numerator']} of {grounded['denominator']} claims grounded",
            14,
            GREEN,
            "left",
        )
    return scene


def main() -> int:
    draw(cards_by_cutoff(load(), load_llm())).save(OUT)
    print(f"written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
