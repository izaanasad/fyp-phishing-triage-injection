"""
Evaluation harness for the document-borne prompt-injection test rig (FR-5).

Runs the corpus through the triage agent, grades each poisoned variant against
its ground truth and matched clean baseline, and aggregates the five metrics.

    from harness import run
    metrics = run("corpus/data/run1", "harness/out", agent, sample=60)
"""
from .runner import run, grade_and_aggregate, load_corpus, sample_variants
from .grading import grade
from .metrics import aggregate, format_summary

__all__ = [
    "run", "grade_and_aggregate", "load_corpus", "sample_variants",
    "grade", "aggregate", "format_summary",
]
