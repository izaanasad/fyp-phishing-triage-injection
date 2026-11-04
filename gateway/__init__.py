"""
Sanitisation gateway for the document-borne prompt-injection test rig (OBJ-5).

The core contribution: a render-vs-extract gateway that screens an attachment
before the LLM triage agent reads it, forwarding only what a human reading the
rendered document would read.

    from gateway import Gateway
    gw = Gateway()
    result = gw.sanitise("corpus/data/run1/poisoned/lure_00__V1__O1.pdf")
    clean_text = result.sanitised_text        # feed THIS to the agent
    print(result.summary())

Requirements covered: FR-6 (render-vs-extract), FR-7 (encoding normalisation),
FR-8 (metadata / non-body channel stripping).
"""
from .gateway import Gateway
from .records import GatewayResult, DroppedSpan
from . import normalize, render_diff

__all__ = ["Gateway", "GatewayResult", "DroppedSpan", "normalize", "render_diff"]
