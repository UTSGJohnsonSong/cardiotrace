"""
Catalog-driven NHANES downloader. Replaces data/download.py, now at legacy-invalid/data/download.py.

WHY
---
The old downloader hardcoded 17 module names and probed them in every cycle,
treating a 404 as "that panel wasn't run this cycle". CDC renamed the lab
modules twice (LAB13 -> L13 -> TCHOL+HDL, LAB10 -> L10 -> GHB, ...), so the
probes 404'd for 1999-2004 and three cycles entered the warehouse with no
laboratory data at all: 15,332 adults, 24.4% of the analysis sample, whose
lipids/glucose/HbA1c were then median-imputed downstream.

This version drives off the Stage 0 selection ledger, which carries the real
download URL CDC publishes for every file. Two rules follow from that failure:

  1. Never guess a filename. The URL comes from CDC's own listing.
  2. Never skip silently. If the ledger says a file exists and we cannot fetch
     it, that is an error and the run exits non-zero. A missing file must never
     again be indistinguishable from a panel that was not collected.

Files land in data/raw/{cycle}/ with the same naming the existing ETL expects,
so src/etl.py keeps working. Downloads are resumable: existing files are
skipped, and every file's SHA-256 goes into the manifest so a later run can
prove it read the same bytes CDC served.

Prerequisites:
    python data/build_catalog.py            # enumerate all 1,821 public files
    python data/apply_selection_rules.py    # apply the R0-R5 rule ladder

Usage:
    python data/download_from_catalog.py              # fetch everything kept
    python data/download_from_catalog.py --dry-run    # list what would be fetched
    python data/download_from_catalog.py --verify     # re-hash local files
"""

import argparse
import csv
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
LEDGER = ROOT / "catalog" / "selection_ledger.csv"
RAW_DIR = ROOT / "raw"
MANIFEST = RAW_DIR / "MANIFEST.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "CardioTrace-Downloader/3.0 (research project)"
    )
}


def kept_files() -> list[dict]:
    with open(LEDGER, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["disposition"] == "keep"]
    if not rows:
        raise SystemExit(f"No kept rows in {LEDGER}. Run apply_selection_rules.py first.")
    return rows


def dest_for(row: dict) -> Path:
    """data/raw/{cycle}/{MODULE}.XPT — matches what src/etl.py already globs."""
    return RAW_DIR / row["cycle"] / (Path(row["data_url"]).stem.upper() + ".XPT")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, retries: int = 4, backoff: float = 2.0) -> bool:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
                tmp.replace(dest)
                return True
            log.warning(f"HTTP {r.status_code}  {url}")
        except requests.RequestException as e:
            log.warning(f"GET error (attempt {attempt + 1}): {type(e).__name__}: {e}")
        time.sleep(backoff ** attempt)
    return False


def run(dry_run: bool = False) -> None:
    rows = kept_files()
    log.info(f"{len(rows)} files marked keep in the selection ledger")

    if dry_run:
        for r in sorted(rows, key=lambda x: (x["cycle"], x["module"])):
            d = dest_for(r)
            state = "have" if d.exists() else "FETCH"
            print(f"  {state:5s} {r['cycle']}  {r['module']:12s} {r['rule']}")
        return

    entries, failures = [], []
    new = skipped = 0

    for r in sorted(rows, key=lambda x: (x["cycle"], x["module"])):
        dest = dest_for(r)
        if dest.exists():
            skipped += 1
        else:
            if not fetch(r["data_url"], dest):
                # The ledger came from CDC's own file listing, so this URL was
                # published. Failing to fetch it is a real error, not a missing
                # panel — surface it instead of continuing with a hole.
                failures.append((r["cycle"], r["module"], r["data_url"]))
                continue
            new += 1
            log.info(f"OK    {r['cycle']}  {r['module']:12s} {dest.stat().st_size / 1024:>8.0f} KB")

        entries.append({
            "cycle": r["cycle"], "module": r["module"], "concept": r["rule"],
            "file": str(dest.relative_to(RAW_DIR)).replace("\\", "/"),
            "url": r["data_url"], "bytes": dest.stat().st_size,
            "sha256": sha256_of(dest),
        })

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_ledger": str(LEDGER.relative_to(ROOT.parent)).replace("\\", "/"),
        "n_files": len(entries),
        "files": entries,
    }, indent=2))

    log.info(f"\nnew={new}  already_present={skipped}  failed={len(failures)}")
    log.info(f"manifest -> {MANIFEST}")

    by_cycle = defaultdict(int)
    for e in entries:
        by_cycle[e["cycle"]] += 1
    log.info("\nfiles per cycle:")
    for c in sorted(by_cycle):
        log.info(f"  {c}  {by_cycle[c]:3d}")

    if failures:
        log.error(f"\n{len(failures)} FILE(S) IN THE LEDGER COULD NOT BE FETCHED:")
        for cyc, mod, url in failures:
            log.error(f"  {cyc}  {mod}  {url}")
        raise SystemExit(1)


def verify() -> bool:
    if not MANIFEST.exists():
        log.error(f"No manifest at {MANIFEST}. Run the downloader first.")
        return False
    ok = True
    for e in json.loads(MANIFEST.read_text())["files"]:
        p = RAW_DIR / e["file"]
        if not p.exists():
            log.error(f"MISSING   {e['file']}")
            ok = False
        elif sha256_of(p) != e["sha256"]:
            log.error(f"MISMATCH  {e['file']}")
            ok = False
    log.info("All files match the manifest." if ok else "VERIFICATION FAILED.")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Download the NHANES files kept by the rule ladder")
    ap.add_argument("--dry-run", action="store_true", help="List what would be fetched")
    ap.add_argument("--verify", action="store_true", help="Re-hash local files against the manifest")
    args = ap.parse_args()

    if args.verify:
        raise SystemExit(0 if verify() else 1)
    run(dry_run=args.dry_run)
