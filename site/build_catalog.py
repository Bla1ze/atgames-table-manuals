#!/usr/bin/env python3
"""Bring site/public up to date with the PDFs at the repo root.

For every PDF: render its cover (page 1) to public/covers/<slug>.webp if it is
missing, and give it an entry in public/manuals.json if it has none. A new
entry gets a title from the PDF's first line (or its file name), a group
guessed from the name, and an empty description, which the page shows as
"Description coming soon" until one is written by hand. Entries whose PDF is
gone are removed. Hand-written titles and descriptions are never touched.

Needs pdftoppm/pdftotext/pdfinfo (poppler) and cwebp. Run from anywhere:
    python3 site/build_catalog.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PUBLIC = REPO / "site" / "public"
CATALOG = PUBLIC / "manuals.json"
COVERS = PUBLIC / "covers"


def slug_for(pdf_name):
    stem = Path(pdf_name).stem
    # One file was uploaded with its title prefixed to the real name.
    stem = re.sub(r"^.*? - (?=[a-z0-9-]+$)", "", stem)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
    return re.sub(r"-?user-manual$", "", stem)


def run(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def render_cover(pdf, slug):
    out = COVERS / f"{slug}.webp"
    if out.exists():
        return False
    COVERS.mkdir(parents=True, exist_ok=True)
    tmp = COVERS / f"_{slug}"
    run("pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-scale-to", "640", "-jpeg", str(pdf), str(tmp))
    run("cwebp", "-quiet", "-q", "78", f"{tmp}.jpg", "-o", str(out))
    Path(f"{tmp}.jpg").unlink()
    return True


def guess_title(pdf):
    try:
        first = next((l.strip() for l in run("pdftotext", "-l", "1", str(pdf), "-").splitlines() if l.strip()), "")
    except subprocess.CalledProcessError:
        first = ""
    title = re.sub(r"\s*(table\s+)?user\s+manual.*$", "", first, flags=re.I).strip(" -:")
    if 3 <= len(title) <= 60:
        return title if not title.isupper() else title.title().replace("Em+", "EM+")
    words = slug_for(pdf.name).replace("zaccaria-", "").split("-")
    return " ".join(w.upper() if w == "em" else w.capitalize() for w in words)


def guess_group(name):
    n = name.lower()
    if "zaccaria" in n:
        return "Zaccaria"
    if "pack" in n or "volume" in n or "natural-history" in n:
        return "Pack"
    return "Original"


def pdf_info(pdf):
    pages = int(re.search(r"^Pages:\s+(\d+)", run("pdfinfo", str(pdf)), re.M).group(1))
    return pages, pdf.stat().st_size


def main():
    catalog = json.loads(CATALOG.read_text()) if CATALOG.exists() else []
    by_file = {m["file"]: m for m in catalog}
    pdfs = sorted(REPO.glob("*.pdf"))
    added, covers = [], 0

    for pdf in pdfs:
        slug = slug_for(pdf.name)
        covers += render_cover(pdf, slug)
        pages, size = pdf_info(pdf)
        entry = by_file.get(pdf.name)
        if entry is None:
            title = guess_title(pdf)
            entry = {"slug": slug, "title": title, "group": guess_group(pdf.name),
                     "kind": "EM+" if title.endswith("EM+") else "Deluxe" if "Deluxe" in title else None,
                     "description": "", "file": pdf.name, "cover": f"covers/{slug}.webp"}
            added.append(title)
        entry["pages"], entry["bytes"] = pages, size   # the PDF may have been replaced
        by_file[pdf.name] = entry

    present = {p.name for p in pdfs}
    removed = [m["title"] for f, m in by_file.items() if f not in present]
    for m in list(by_file.values()):
        if m["file"] not in present:
            cover = PUBLIC / m["cover"]
            if cover.exists():
                cover.unlink()
    result = sorted((m for f, m in by_file.items() if f in present), key=lambda m: m["title"].lower())
    CATALOG.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")

    print(f"{len(result)} manuals; {covers} new covers; added: {added or 'none'}; removed: {removed or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
