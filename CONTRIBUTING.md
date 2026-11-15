# Contributing

How code in this repository is written and reviewed. It applies to every
change, including changes written with an AI assistant.

## The hard rules

The rest of this document serves these six rules. A change that weakens one is
not merged, whatever else it improves.

| # | Rule | Enforced by |
| --- | --- | --- |
| 1 | Every number in an output traces to a source row: a `Measurement` ID, or, for a model's claim, the node IDs it cites. | `src/hindcast/provenance.py`, `tests/test_provenance_and_license.py` |
| 2 | No evidence dated on or after the cutoff reaches reasoning. The slice database enforces this, not the calling code. | `tests/test_slice_leak.py` |
| 3 | Refusal is a scored outcome, and the refusal path is built before the answer path. | `tests/test_refusal.py` |
| 4 | A clone reproduces every result offline, byte for byte, with no API keys. Model responses are replayed from `eval/model_cache/`. | `tests/test_determinism.py`, `tests/test_redistribution.py` |
| 5 | The demo path never calls a live third-party API. | `src/hindcast/snapshot.py` (by design; no test yet) |
| 6 | Every row carries its source's license, and no article text or abstracts are committed. | `tests/test_provenance_and_license.py`, `tests/test_redistribution.py` |

**Frozen policy.** Thresholds and coefficients in `eval/rulebook/` were frozen
before the first evaluation run. Never change them to improve a result. A
policy change is a new frozen version with its own tag, reported beside the old
one.

## Before you push

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
cd web && npm run typecheck && npm run build
```

CI runs the same commands (#14).

## Python

- Python 3.12. Every module starts with `from __future__ import annotations`, and
  every public function has full type hints.
- Data that crosses a boundary (a file, a database row, a model response, CLI
  output) is a pydantic model with `ConfigDict(extra="forbid")`. Plain dicts are
  for values that stay inside one function.
- Fixed vocabularies are `StrEnum`s, not strings scattered through the code.
- A module docstring states the module's contract: what goes in, what comes out,
  and what it must never do. `agents/grader.py` is the model to follow.
- A constant that encodes a judgement (a threshold, a weight) lives at module
  level with a `#:` comment, and METHODOLOGY.md gives the reason for its value.
- Fail loudly. No bare `except`, and no fallback that silently changes a result.
  A record may be excluded only with a recorded reason.
- Results are deterministic: sort before writing, fix every seed, and keep
  timestamps in trajectories, never in results.
- Use the standard library first. A new runtime dependency needs a stated
  reason; model and retrieval dependencies go in the `llm` extra.
- Write for the current need. No base class with a single subclass, no option
  nobody sets, no wrapper that only renames.

## Language-model code

The model is a component under test, so its code follows rules the rest of the
pipeline gets for free.

- Prompts are module constants. The replay cache keys on a hash of the model ID,
  prompt, context and parameters, so editing a prompt can never replay an old
  response.
- The full model ID is pinned and written into every result.
- Responses parse into pydantic schemas. An invalid response is recorded as a
  failure, never repaired. Retries are for transport errors only, and bounded.
- The model receives only what the slice connection returns. It never sees the
  rule book, the answer key or the traps.
- Every call goes through the replay cache. A live call requires `--live` and
  `GEMINI_API_KEY`.
- Keys come from the environment and never appear in logs, trajectories or
  results.
- Each run records input tokens, output tokens and cost.
- Grading is deterministic. If an LLM judge is ever added, its scores are
  reported separately and checked against hand labels first.

## Data models

A result file is read by people deciding whether to trust it. Design for that
reader.

- Name fields in plain words, with units where they apply: `confidence`
  (0 to 1), `publication_date`, `cost_usd`. Not `conf`, `pd` or `c`.
- One meaning per field. Never let `null` carry a meaning: use an explicit
  status such as `"not_run"` or `"refused"`.
- Every record carries its ID and its provenance, so any number leads to its
  source row in one step.
- Result files describe themselves: cutoff, condition, model ID, prompt hash,
  and the version of the metric definitions.
- The pydantic model is the source of truth. `web/lib/types.ts` mirrors only
  the fields the interface reads and changes in the same commit. A change to a
  node or edge type updates SCHEMA.md in the same commit.
- When a schema changes, regenerate the committed results in the same change.
  Never hand-edit files in `eval/results/` or `trajectories/`.

## Web app

- The Next.js release in `web/` differs from most training data. Read the guide
  in `web/node_modules/next/dist/docs/` before using an API, and heed its
  deprecation notices.
- Components are server components unless they need interaction. File reads
  happen only in `lib/repo.ts`, which is `server-only`.
- No `any`. Types come from `lib/types.ts`.
- Colors come only from the tokens in `globals.css`. A new data color is
  validated as a set with the existing ones, as that file's header describes.
- Every view works at 375px width and with the keyboard alone. Wide tables
  scroll inside `.table-wrap`.
- Don't add a dependency for something a few lines can do.

## Writing: interface copy and docs

- Say each thing once. A heading names the thing, and the text under it adds
  only what the heading does not say. No "This table shows…".
- Prefer labels to sentences: "Short by 0.01", not "This gene fell short of the
  threshold by 0.01".
- Define a term once, in the docs or a tooltip, and then use it unchanged. Don't
  alternate synonyms such as refusal and abstention.
- Give every rate its denominator or interval: "0.20 (1 of 5)".
- Be plain and specific. No "powerful", "seamless" or "cutting-edge". Report
  weak results as plainly as strong ones.
- Each fact lives in one file, and other files link to it. Numbers in the docs
  are generated by `scripts/render_scorecard.py`, never typed.

## Comments

- A comment explains why. The code already says what.
- Match the comment density of the surrounding code.
- No commented-out code, and no TODO without an issue number.

## Tests

- Every hard rule has a test that tries to break it. A new retrieval path, tool
  or cache extends `tests/test_slice_leak.py`.
- Name tests as sentences that state the behavior, such as
  `test_a_claim_at_the_prior_is_refused`.
- Tests run offline, with no network and no API key. Model code is tested with
  a fake client.
- Tests never write to committed directories; `tests/conftest.py` redirects
  trajectories.
- A bug fix comes with a test that fails without the fix.

## Commits and pull requests

- One logical change per commit. Write the subject in the imperative, in
  sentence case, with no trailing period, in 72 characters or fewer.
- Reference the issue in the body: `Closes #N`.
- Commit regenerated results separately from the code that changed them, and
  only from a full `hindcast run-all`.
- Keep pull requests small enough to review in one sitting. The description
  says what changed, why, and how it was verified, with the commands that were
  run.

## Scope

The plan is the pinned roadmap issue and its milestone. Work one issue at a
time. A new idea goes to the next milestone unless it fixes a P0 acceptance
criterion.
