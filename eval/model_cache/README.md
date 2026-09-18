# Model cache

The ablation row comparing the full system against a general model with no graph
needs a language model. This repository contains no API keys and makes no
network calls on the demo path, because hard rule 4 requires a clone to
reproduce the exact scorecard offline.

So that row is replayed from this directory rather than called live. A cache
file is named `<model>_<cutoff>_<prompt-hash-prefix>.json` and holds:

```json
{
  "model": "the exact pinned model version used",
  "cutoff": "2017-12-31",
  "prompt_sha256": "the full hash of the prompt that was sent",
  "ranking": [
    {"gene": "SYMBOL", "confidence": 0.42, "statement": "one line from the model"}
  ]
}
```

The prompt is committed in `hindcast.agents.baseline.BASELINE_PROMPT` and the
cache key is its SHA-256, so a cached response cannot silently correspond to a
different prompt.

With no file here, the scorecard reports that row as not run. It does not
estimate it. `scripts/populate_model_cache.py` populates the cache for anyone
who has a key, and once committed the row replays offline like everything else.
