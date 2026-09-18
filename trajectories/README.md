# Trajectories

One directory per evaluation run, named `<cutoff>_<ablation>`, holding one JSON
file per agent. Each file records what the agent was given, every tool call it
made with record counts and timings, what it returned, and the environment it
ran in.

These are committed because a scorecard whose reasoning cannot be inspected is a
claim rather than a result. If a number in the scorecard looks wrong, the
trajectory shows which tool call produced it and over how many records.

There are no prompts and no token counts, because there is no language model in
this system. Every judgement is a stated rule in a documented module, so the
trajectories record tool calls and record counts where an LLM-backed pipeline
would record prompts and tokens. `hindcast.agents.base` explains that choice and
`eval/model_cache/` holds the one comparison that would need a model.
