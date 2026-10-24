"""
Corpus generator for the document-borne prompt-injection test rig (FR-4).

Produces matched clean/poisoned document variants across the locked V1-V8
taxonomy and the O1-O3 attacker objectives, validating every poisoned variant
against rules R1 (survives extraction) and R2 (invisible when rendered) using
the extraction pipeline, and recording machine-checkable ground truth.

    from corpus import generate
    report = generate("base.docx", out_dir="data/run1")
    print(report.n_accepted, "accepted,", report.n_rejected, "rejected")
"""
from .generator import (
    GenerationReport,
    GroundTruth,
    applicable_vectors,
    generate,
    generate_many,
)
from . import payloads

__all__ = [
    "generate",
    "generate_many",
    "GenerationReport",
    "GroundTruth",
    "applicable_vectors",
    "payloads",
]
