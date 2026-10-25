"""
Base-document acquisition for the corpus (feeds FR-3/OBJ-3).

Collects realistic base documents from two public sources and writes them as
clean PDFs into an output folder, with a provenance manifest:

  * SEC EDGAR  — financial filings (10-K/10-Q) and material-contract exhibits
                 (EX-10). CUAD is itself built from EDGAR EX-10 exhibits, so
                 these are the same class of contract.
  * CUAD       — the 510 contract PDFs, extracted from a locally-downloaded
                 CUAD bundle (download once from www.atticusprojectai.org/cuad).

NETWORK NOTE: the EDGAR path requires internet and SEC's User-Agent policy (a
real contact string + <=10 requests/sec). Run it on your own machine; the
project's cloud sandbox blocks sec.gov by egress policy. Nothing downloaded is
executed — documents are only read and re-rendered to text PDFs (NFR-4/NFR-6).

CLI (run from `code/`):
  python -m corpus.acquire cuad  --zip "C:\\path\\CUAD_v1.zip" --n 40 --out corpus/data/base
  python -m corpus.acquire edgar --email you@example.com --financial 20 --contracts 20 --out corpus/data/base
"""
from __future__ import annotations

import html as _html
import json
import re
import shutil
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pymupdf

EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# A small default roster of large, stable filers (CIKs) for the financial path.
DEFAULT_CIKS = [
    320193,   # Apple
    789019,   # Microsoft
    1018724,  # Amazon
    1652044,  # Alphabet
    1318605,  # Tesla
    104169,   # Walmart
    21344,    # Coca-Cola
    50863,    # Intel
    51143,    # IBM
    19617,    # JPMorgan Chase
    200406,   # Johnson & Johnson
    310158,   # Merck
]


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------
@dataclass
class Provenance:
    items: list[dict] = field(default_factory=list)

    def add(self, **kw):
        self.items.append(kw)

    def write(self, path: Path):
        path.write_text(json.dumps({"items": self.items}, indent=2, ensure_ascii=False),
                        encoding="utf-8")


# ---------------------------------------------------------------------------
# pure helpers (fully unit-testable, no network)
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANKS_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    """Crude, dependency-free HTML -> text for rendering base PDFs."""
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p\s*>", "\n\n", raw)
    raw = re.sub(r"(?i)</tr\s*>", "\n", raw)
    text = _TAG_RE.sub(" ", raw)
    text = _html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = _BLANKS_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def text_to_pdf(text: str, out: Path, title: str = "", max_pages: int = 40) -> Path:
    """Render plain text into a simple, clean multi-page PDF."""
    doc = pymupdf.open()
    width, height = 595, 842  # A4 points
    margin, font, leading = 54, 10.5, 14
    usable = width - 2 * margin
    approx_chars = max(20, int(usable / (font * 0.5)))

    def wrap(line: str) -> list[str]:
        words, out_lines, cur = line.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= approx_chars:
                cur = f"{cur} {w}".strip()
            else:
                out_lines.append(cur)
                cur = w
        if cur:
            out_lines.append(cur)
        return out_lines or [""]

    lines: list[str] = []
    if title:
        lines += wrap(title) + [""]
    for para in text.splitlines():
        lines += wrap(para) if para.strip() else [""]

    page = doc.new_page(width=width, height=height)
    y = margin
    for ln in lines:
        if y > height - margin:
            if doc.page_count >= max_pages:
                break
            page = doc.new_page(width=width, height=height)
            y = margin
        page.insert_text((margin, y), ln, fontsize=font, color=(0, 0, 0))
        y += leading
    doc.save(out)
    doc.close()
    return out


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:120]


def _pdf_text(src: Path) -> str:
    doc = pymupdf.open(src)
    try:
        return "\n".join(page.get_text() for page in doc).strip()
    finally:
        doc.close()


def pdf_to_docx(src_pdf: Path, out_docx: Path) -> Path:
    """Create a clean DOCX base document from a PDF's text (for DOCX vectors)."""
    from docx import Document  # python-docx

    text = _pdf_text(src_pdf)
    doc = Document()
    for line in text.splitlines():
        if line.strip():
            doc.add_paragraph(line.strip())
    if not doc.paragraphs:
        doc.add_paragraph("(empty document)")
    doc.save(out_docx)
    return out_docx


def convert_to_docx(in_dir: Path, n: int, out: Path, prov: Provenance) -> int:
    """Convert up to n base PDFs in in_dir into DOCX base documents."""
    out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(p for p in in_dir.glob("*.pdf"))
    made = 0
    for p in pdfs[:n]:
        dest = out / (p.stem + ".docx")
        try:
            pdf_to_docx(p, dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! convert failed {p.name}: {exc}")
            continue
        prov.add(source="converted", kind="docx_from_pdf", original=p.name, saved_as=dest.name)
        made += 1
        print(f"  + {dest.name}")
    return made


# ---------------------------------------------------------------------------
# CUAD (local bundle -> PDFs). Fully testable.
# ---------------------------------------------------------------------------
def acquire_cuad(source: str | Path, n: int, out: Path, prov: Provenance) -> int:
    """Extract up to n contract PDFs from a CUAD zip or an extracted folder."""
    out.mkdir(parents=True, exist_ok=True)
    src = Path(source)
    count = 0
    if src.is_dir():
        pdfs = sorted(p for p in src.rglob("*.pdf"))
        for p in pdfs[:n]:
            dest = out / f"cuad_{_safe_name(p.stem)}.pdf"
            shutil.copy2(p, dest)
            prov.add(source="cuad", original=str(p), saved_as=dest.name)
            count += 1
    elif zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith(".pdf")]
            for m in sorted(members)[:n]:
                dest = out / f"cuad_{_safe_name(Path(m).stem)}.pdf"
                with zf.open(m) as fh, dest.open("wb") as o:
                    shutil.copyfileobj(fh, o)
                prov.add(source="cuad", original=m, saved_as=dest.name)
                count += 1
    else:
        raise ValueError(f"CUAD source is neither a folder nor a zip: {src}")
    return count


# ---------------------------------------------------------------------------
# EDGAR (network; runs on the user's machine)
# ---------------------------------------------------------------------------
def _fetch(url: str, email: str, accept_json: bool = False, pause: float = 0.2) -> bytes:
    ua = f"Izaan Asad FYP Research {email}"
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json" if accept_json else "*/*",
    })
    time.sleep(pause)  # stay well under SEC's 10 req/sec
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            import gzip
            data = gzip.decompress(data)
    return data


def acquire_edgar_financial(ciks, n, email, out: Path, prov: Provenance) -> int:
    out.mkdir(parents=True, exist_ok=True)
    got = 0
    for cik in ciks:
        if got >= n:
            break
        try:
            sub = json.loads(_fetch(EDGAR_SUBMISSIONS.format(cik=cik), email, accept_json=True))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! submissions failed for CIK {cik}: {exc}")
            continue
        company = sub.get("name", str(cik))
        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        for i, form in enumerate(forms):
            if got >= n:
                break
            if form not in ("10-K", "10-Q"):
                continue
            acc = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            url = EDGAR_ARCHIVE.format(cik=cik, acc=acc, doc=doc)
            try:
                raw = _fetch(url, email).decode("utf-8", "ignore")
            except Exception as exc:  # noqa: BLE001
                print(f"  ! doc failed {url}: {exc}")
                continue
            text = html_to_text(raw)
            if len(text) < 500:
                continue
            dest = out / f"edgar_{form.replace('-', '')}_{cik}_{acc}.pdf"
            text_to_pdf(text, dest, title=f"{company} — {form} ({acc})")
            prov.add(source="edgar", kind="financial", cik=cik, company=company,
                     form=form, accession=acc, url=url, saved_as=dest.name, chars=len(text))
            got += 1
            print(f"  + {dest.name}  ({company}, {form})")
            break  # one per company keeps the set diverse
    return got


_EX10_RE = re.compile(r"ex[-_ ]?10", re.I)


def _find_ex10_in_index(cik: int, acc: str, email: str) -> list[str]:
    """Return file names in a filing that look like EX-10 material contracts."""
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
    try:
        idx = json.loads(_fetch(idx_url, email, accept_json=True))
    except Exception:  # noqa: BLE001
        return []
    names = []
    for item in idx.get("directory", {}).get("item", []):
        name = item.get("name", "")
        typ = item.get("type", "")
        if name.lower().endswith((".htm", ".html", ".txt")) and (
            _EX10_RE.search(name) or _EX10_RE.search(typ)
        ):
            names.append(name)
    return names


def acquire_edgar_contracts(ciks, n, email, out: Path, prov: Provenance,
                            max_filings_per_cik: int = 30) -> int:
    """Download EX-10 material-contract exhibits by scanning filing indexes."""
    out.mkdir(parents=True, exist_ok=True)
    got = 0
    for cik in ciks:
        if got >= n:
            break
        try:
            sub = json.loads(_fetch(EDGAR_SUBMISSIONS.format(cik=cik), email, accept_json=True))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! submissions failed for CIK {cik}: {exc}")
            continue
        recent = sub.get("filings", {}).get("recent", {})
        accessions = recent.get("accessionNumber", [])
        found_here = 0
        for i, acc_dash in enumerate(accessions[:max_filings_per_cik]):
            if got >= n or found_here >= 2:  # keep the set diverse across filers
                break
            acc = acc_dash.replace("-", "")
            for fname in _find_ex10_in_index(cik, acc, email):
                if got >= n or found_here >= 2:
                    break
                url = EDGAR_ARCHIVE.format(cik=cik, acc=acc, doc=fname)
                try:
                    raw = _fetch(url, email).decode("utf-8", "ignore")
                except Exception as exc:  # noqa: BLE001
                    print(f"  ! exhibit failed {url}: {exc}")
                    continue
                text = html_to_text(raw)
                if len(text) < 500:
                    continue
                dest = out / f"edgar_EX10_{cik}_{acc}_{_safe_name(Path(fname).stem)}.pdf"
                text_to_pdf(text, dest, title=f"Material contract (EX-10) — CIK {cik}")
                prov.add(source="edgar", kind="contract", cik=cik, form="EX-10",
                         accession=acc, url=url, saved_as=dest.name, chars=len(text))
                got += 1
                found_here += 1
                print(f"  + {dest.name}")
    return got


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="corpus.acquire")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cuad", help="extract contract PDFs from a local CUAD zip/folder")
    c.add_argument("--zip", dest="src", required=True, help="path to CUAD zip or extracted folder")
    c.add_argument("--n", type=int, default=40)
    c.add_argument("--out", default="corpus/data/base")

    e = sub.add_parser("edgar", help="download filings from SEC EDGAR (needs internet)")
    e.add_argument("--email", required=True, help="your contact email (SEC User-Agent policy)")
    e.add_argument("--financial", type=int, default=20)
    e.add_argument("--contracts", type=int, default=20)
    e.add_argument("--out", default="corpus/data/base")

    t = sub.add_parser("todocx", help="convert base PDFs into DOCX base docs (for V4-V6 coverage)")
    t.add_argument("--in", dest="in_dir", default="corpus/data/base", help="folder of base PDFs")
    t.add_argument("--n", type=int, default=15)
    t.add_argument("--out", default="corpus/data/base")

    args = ap.parse_args(argv)
    out = Path(args.out)
    prov = Provenance()

    if args.cmd == "cuad":
        n = acquire_cuad(args.src, args.n, out, prov)
        print(f"CUAD: extracted {n} PDFs -> {out}/")
    elif args.cmd == "todocx":
        print("Converting base PDFs to DOCX:")
        n = convert_to_docx(Path(args.in_dir), args.n, out, prov)
        print(f"todocx: created {n} DOCX base documents -> {out}/")
    else:
        print("EDGAR financial filings:")
        f = acquire_edgar_financial(DEFAULT_CIKS, args.financial, args.email, out, prov)
        print("EDGAR EX-10 contracts:")
        k = acquire_edgar_contracts(DEFAULT_CIKS, args.contracts, args.email, out, prov)
        print(f"EDGAR: {f} financial + {k} contracts -> {out}/")

    prov.write(out / "provenance.json")
    print(f"provenance written -> {out / 'provenance.json'}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
