# Model cache

Every response the language-model forecaster (`hindcast.llm`) has received, one
file per request. `hindcast run-all` and `hindcast llm` replay from here, so a
clone reproduces the model rows offline with no API key.

A file is named `<cache_key>.json`, where the key is the SHA-256 of the whole
request: model ID, system prompt, messages, tools, output schema and parameters.
A response can only replay for the exact request that produced it. Editing a
prompt changes the key, and the old response is never found again.

```json
{
  "cache_key": "the SHA-256 of the request below",
  "request": {"model_id": "...", "system": "...", "messages": [], "...": "..."},
  "response": {
    "served_model_id": "the model the API reports having served",
    "content": [{"type": "text", "text": "the answer, as received"}],
    "stop_reason": "end_turn",
    "input_tokens": 0,
    "output_tokens": 0
  }
}
```

Responses are stored as received. One that is refused, cut off or does not match
the answer schema is kept and replays as a failure; it is never repaired.

With no file for a request, the row is reported as not run. To populate the
cache, install the `llm` extra, set `ANTHROPIC_API_KEY` and run:

```bash
hindcast llm --cutoff 2017-12-31 --retrieval none --live
```

The key is read from the environment by the SDK and is never written here.
