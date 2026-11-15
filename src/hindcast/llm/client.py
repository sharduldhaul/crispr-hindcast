"""Model calls, and the replay cache that makes them reproducible.

Contract. A `ModelRequest` goes in and a `ModelResponse` comes out, from the
cache when the request has been seen before and from the transport otherwise.
The cache key is the SHA-256 of the whole request (model ID, system prompt,
messages, tools, output schema and parameters), so a response can only ever be
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
DEFAULT_MODEL_ID = "claude-opus-5-5"

#: Output budget per call, thinking included. Large enough that a full answer
#: over the candidate list cannot be cut off; a response that still hits the
#: limit is recorded as a failure.
MAX_OUTPUT_TOKENS = 16000

#: Reasoning effort, set explicitly so a change in the provider's default
#: cannot change a result. See METHODOLOGY.md.
EFFORT = "medium"

#: SDK retries on connection errors, 408, 409, 429 and 5xx. Transport only: an
#: invalid answer is never retried.
MAX_TRANSPORT_RETRIES = 2

#: List price in USD per million tokens, as (input, output). A model with no
#: entry cannot be run, so a cost is never guessed.
PRICES_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
}


class ModelRequest(BaseModel):
    """Everything that determines a response. Hashed whole to form the cache key."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    output_schema: dict[str, Any]
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    effort: str = EFFORT

    def cache_key(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ModelResponse(BaseModel):
    """One response as received: content blocks, stop reason and token usage."""

    model_config = ConfigDict(extra="forbid")

    served_model_id: str
    content: list[dict[str, Any]]
    stop_reason: str
    input_tokens: int
    output_tokens: int

    def text(self) -> str:
        """The text of the first text block, or an empty string if there is none."""
        return next((str(b.get("text", "")) for b in self.content if b.get("type") == "text"), "")


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


def anthropic_transport(request: ModelRequest) -> ModelResponse:
    """One live call through the Anthropic SDK. Needs the `llm` extra and a key."""
    # Imported here so the offline path, which never calls this, does not need
    # the `llm` extra installed.
    import anthropic

    client = anthropic.Anthropic(max_retries=MAX_TRANSPORT_RETRIES)
    kwargs: dict[str, Any] = {
        "model": request.model_id,
        "max_tokens": request.max_output_tokens,
        "system": request.system,
        "messages": request.messages,
        "output_config": {
            "effort": request.effort,
            "format": {"type": "json_schema", "schema": request.output_schema},
        },
    }
    if request.tools:
        kwargs["tools"] = request.tools
    try:
        message = client.messages.create(**kwargs)
    except anthropic.APIStatusError as exc:
        # Class and status only. The SDK's message can echo request details,
        # and nothing from the request belongs in a log.
        raise ModelTransportError(f"{type(exc).__name__} (HTTP {exc.status_code})") from None
    except anthropic.APIConnectionError as exc:
        raise ModelTransportError(type(exc).__name__) from None

    return ModelResponse(
        served_model_id=message.model,
        content=message.to_dict()["content"],
        stop_reason=str(message.stop_reason),
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )
