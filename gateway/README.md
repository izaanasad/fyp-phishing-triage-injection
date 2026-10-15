# gateway/

The sanitisation gateway (project contribution). Screens attachments before the agent reads them.
Primary mechanism: render-vs-extract (rasterise + OCR, diff against extracted text layer) + encoding normalisation, metadata stripping, structural tagging.
Bypassable, to measure the undefended baseline. Owner: Izaan (A4) / Momina (B4, service).
