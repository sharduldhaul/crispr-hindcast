"""Model calls, and the replay cache that makes them reproducible.

Contract. A `ModelRequest` goes in and a `ModelResponse` comes out, from the
cache when the request has been seen before and from the transport otherwise.
The cache key is the SHA-256 of the whole request (model ID, system prompt,
input steps, tools, output schema and parameters), so a response can only ever be
replayed for the exact request that produced it. Editing a prompt changes the
key and the old response is simply never found.

What this module must never do:

*   Call the network without a transport. Callers pass one only when the user
    asked for a live run and a key is set; with no transport a cache miss is
    reported as `None` and the row is recorded as not run.
*   Touch the API key. The SDK reads it from the environment. It is never
    read, logged or stored here, and transport errors are reduced to the
    exception class and status code before they are raised.
*   Repair a response. What the model returned is cached and replayed as it
    was received. Deciding whether it is valid belongs to the caller.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CACHE_DIR = Path(__file__).resolve().parents[3] / "eval" / "model_cache"

#: The model every committed row was run with. Written into each result. A
#: different model is a different row, never a silent replacement.
DEFAULT_MODEL_ID = "gemini-3.8-flash"

#: Output budget per call, thinking included. About twice what the first live
#: request used, so thinking cannot crowd out the answer; a response that still
#: hits the limit is recorded as a failure. See METHODOLOGY.md.
MAX_OUTPUT_TOKENS = 32000

#: Thinking level, set explicitly so a change in the provider's default
#: cannot change a result. See METHODOLOGY.md.
THINKING_LEVEL = "medium"

#: Wall-clock limit for one live call, in seconds. Transport only, so it is
#: not part of the cache key: a call that exceeds it raises and is re-run.
#: Without it a connection the server has dropped waits forever.
REQUEST_TIMEOUT_SECONDS = 1800

#: Paid-tier list price in USD per million tokens, as (input, output), on the
#: day the rows were run. Thinking tokens are priced as output. A run on the
#: free tier is billed nothing; the cost recorded is what the same tokens cost
#: at list price. A model with no entry cannot be run, so a cost is never guessed.
PRICES_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
}

#: Step types, as the Interactions API names them.
STEP_USER_INPUT = "user_input"
STEP_FUNCTION_CALL = "function_call"
STEP_FUNCTION_RESULT = "function_result"
STEP_MODEL_OUTPUT = "model_output"

#: The status of an interaction that ended normally. Any other status on a
#: response with no tool call left to answer is recorded as a failure.
STATUS_COMPLETED = "completed"


class ModelRequest(BaseModel):
    """Everything that determines a response. Hashed whole to form the cache key."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    system: str
    input: list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    output_schema: dict[str, Any]
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    thinking_level: str = THINKING_LEVEL

    def cache_key(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ModelResponse(BaseModel):
    """One response as received: the model's steps, its status and token usage.

    `output_tokens` includes thinking tokens, which are priced as output.
    """

    model_config = ConfigDict(extra="forbid")

    served_model_id: str
    steps: list[dict[str, Any]]
    status: str
    input_tokens: int
    output_tokens: int

    def function_calls(self) -> list[dict[str, Any]]:
        """The tool calls the model made in this response, in order."""
        return [s for s in self.steps if s.get("type") == STEP_FUNCTION_CALL]

    def text(self) -> str:
        """The text the model output, joined in order, or an empty string if there is none."""
        return "".join(
            str(block.get("text", ""))
            for step in self.steps
            if step.get("type") == STEP_MODEL_OUTPUT
            for block in step.get("content") or []
            if block.get("type") == "text"
        )


class CacheEntry(BaseModel):
    """One committed file in `eval/model_cache/`."""

    model_config = ConfigDict(extra="forbid")

    cache_key: str
    request: ModelRequest
    response: ModelResponse


#: A function that performs one live call. Tests pass a fake.
Transport = Callable[[ModelRequest], ModelResponse]


class ModelTransportError(RuntimeError):
    """The call did not produce a response. Nothing is cached and nothing is scored."""


class ReplayCache:
    """Responses on disk, one file per request, named by the request's hash."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or CACHE_DIR

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, request: ModelRequest) -> ModelResponse | None:
        key = request.cache_key()
        path = self._path(key)
        if not path.exists():
            return None
        entry = CacheEntry.model_validate_json(path.read_text())
        if entry.cache_key != key or entry.request.cache_key() != key:
            raise ValueError(f"cache file {path.name} does not hold the request it is named for")
        return entry.response

    def put(self, request: ModelRequest, response: ModelResponse) -> Path:
        key = request.cache_key()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        entry = CacheEntry(cache_key=key, request=request, response=response)
        path.write_text(json.dumps(entry.model_dump(), indent=2, sort_keys=True) + "\n")
        return path


def cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """List-price cost of the given usage. Raises for a model with no price."""
    if model_id not in PRICES_USD_PER_MILLION_TOKENS:
        raise KeyError(
            f"no price recorded for model {model_id!r}; add it to "
            f"PRICES_USD_PER_MILLION_TOKENS before running it"
        )
    input_price, output_price = PRICES_USD_PER_MILLION_TOKENS[model_id]
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 6)


def gemini_transport(request: ModelRequest) -> ModelResponse:
    """One live call through the Gemini Interactions API. Needs the `llm` extra and a key.

    The call is stateless: nothing is stored by the provider, and the whole
    history is in `request.input`. The SDK retries connection errors, 408, 409,
    429 and 5xx with backoff, which is transport only: an invalid answer is
    never retried.
    """
    # Imported here so the offline path, which never calls this, does not need
    # the `llm` extra installed.
    from google import genai

    # The SDK exports no public name for the errors its interactions client
    # raises, so the dependency is pinned to the minor version this path is from.
    from google.genai._gaos.lib.compat_errors import APIError

    body: dict[str, Any] = {
        "model": request.model_id,
        "input": request.input,
        "system_instruction": request.system,
        "store": False,
        "generation_config": {
            "thinking_level": request.thinking_level,
            "max_output_tokens": request.max_output_tokens,
        },
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": request.output_schema,
        },
    }
    if request.tools:
        body["tools"] = request.tools
    # Held in a name for the whole call: an unreferenced client is collected,
    # and closes its HTTP connection, before the request is sent.
    client = genai.Client()
    try:
        interaction = client.interactions.create(**body, timeout=REQUEST_TIMEOUT_SECONDS)
    except APIError as exc:
        # Class and status only. The SDK's message can echo request details,
        # and nothing from the request belongs in a log.
        status = getattr(exc, "status_code", None)
        detail = f" (HTTP {status})" if status is not None else ""
        raise ModelTransportError(f"{type(exc).__name__}{detail}") from None

    usage = interaction.usage
    if usage is None or usage.total_input_tokens is None or usage.total_output_tokens is None:
        raise ModelTransportError("the response reported no token usage")
    return ModelResponse(
        served_model_id=str(interaction.model),
        steps=[step.model_dump(mode="json") for step in interaction.steps or []],
        status=str(interaction.status),
        input_tokens=usage.total_input_tokens,
        output_tokens=usage.total_output_tokens + (usage.total_thought_tokens or 0),
    )
