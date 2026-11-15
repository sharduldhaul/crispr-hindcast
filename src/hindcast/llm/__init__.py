"""The language-model evaluation track.

The rule-based system in `hindcast.agents` contains no language model. This
package holds a separate forecaster that does, evaluated on the same slices
by the same grader. Every model call is replayed from `eval/model_cache/`, so
a clone reproduces these rows offline like every other row.
"""
