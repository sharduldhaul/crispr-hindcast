"""Agent scaffolding: typed output and a full trajectory for every run.

Every agent logs what it was given, what it did, what it returned and how long
it took, to `trajectories/`. The logs are committed, because a scorecard whose
reasoning cannot be inspected is a claim rather than a result.

There is no language model anywhere in this system. That is a design decision,
not an omission, and it follows from hard rule 4: a clone of this repository in
2027 must reproduce the exact scorecard offline with no API keys and no network.
Every judgement an agent makes is a stated rule in a documented module, so the
trajectory records tool calls and record counts where an LLM-backed agent would
record prompts and token counts. `hindcast.agents.baseline` holds the harness
for the one comparison that does need a model, and reports that row as not run
unless cached responses are committed.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, Field

from hindcast import __version__

TRAJECTORY_DIR = Path(__file__).resolve().parents[3] / "trajectories"

#: Fixed seed. Nothing in this system samples, but anything that later does must
#: draw from here so replay stays exact.
SEED = 20171231


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    records_in: int = 0
    records_out: int = 0
    duration_ms: float = 0.0


class Trajectory(BaseModel):
    """The full record of one agent run."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    run_id: str
    started_at: str
    finished_at: str = ""
    duration_ms: float = 0.0
    inputs: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)

    def write(self, directory: Path | None = None) -> Path:
        target = (directory or TRAJECTORY_DIR) / self.run_id
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{self.agent}.json"
        path.write_text(json.dumps(self.model_dump(), indent=2, sort_keys=True, default=str))
        return path


class Agent:
    """Base class. Subclasses implement `run` and return a Pydantic model."""

    name: str = "agent"

    def __init__(self, run_id: str, *, trajectory_dir: Path | None = None) -> None:
        self.run_id = run_id
        self.trajectory_dir = trajectory_dir
        self.trajectory = Trajectory(
            agent=self.name,
            run_id=run_id,
            started_at=datetime.now(UTC).isoformat(),
            environment={
                "hindcast_version": __version__,
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "seed": SEED,
                "model": "none: all decisions are stated rules, see agents/base.py",
            },
        )
        self._t0 = time.perf_counter()

    @contextmanager
    def tool(self, name: str, **args: Any) -> Iterator[ToolCall]:
        """Record one tool call. The caller sets record counts and a summary."""
        call = ToolCall(name=name, args={k: _short(v) for k, v in args.items()})
        start = time.perf_counter()
        try:
            yield call
        finally:
            call.duration_ms = round((time.perf_counter() - start) * 1000, 3)
            self.trajectory.tool_calls.append(call)

    def note(self, text: str) -> None:
        self.trajectory.notes.append(text)

    def finish(self, output_summary: dict[str, Any], inputs: dict[str, Any] | None = None) -> Path:
        self.trajectory.finished_at = datetime.now(UTC).isoformat()
        self.trajectory.duration_ms = round((time.perf_counter() - self._t0) * 1000, 3)
        self.trajectory.output_summary = output_summary
        if inputs:
            self.trajectory.inputs = {k: _short(v) for k, v in inputs.items()}
        return self.trajectory.write(self.trajectory_dir)


def _short(value: Any, limit: int = 400) -> Any:
    """Keep trajectories readable without truncating anything load bearing."""
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 20:
            return [_short(v) for v in value[:20]] + [f"... {len(value) - 20} more"]
        return [_short(v) for v in value]
    if isinstance(value, dict):
        return {k: _short(v) for k, v in value.items()}
    text = str(value)
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars)"
