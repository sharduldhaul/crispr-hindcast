# Trajectories

One directory per evaluation run, named `<cutoff>_<ablation>`, holding one JSON
file per agent. Each file records what the agent was given, every tool call it
made with record counts and timings, what it returned, and the environment it
ran in.

These are committed because a scorecard whose reasoning cannot be inspected is a
claim rather than a result. If a number in the scorecard looks wrong, the
trajectory shows which tool call produced it and over how many records.

The rule-based runs have no prompts and no token counts, because that system
contains no language model: every judgement is a stated rule in a documented
module, and `hindcast.agents.base` explains the choice. The `llm-*` runs record
the model ID, the prompt hash, each replayed or live call by its cache key, and
the tokens and cost of the run. The responses themselves are in
`eval/model_cache/`.
