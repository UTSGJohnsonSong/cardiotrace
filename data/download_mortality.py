"""
NHANES Public-Use Linked Mortality File (LMF) downloader for CardioTrace.

WHY THIS FILE EXISTS
--------------------
The core NHANES survey is cross-sectional: the CVD questions (MCQ160B-F) ask
whether a doctor *ever told you* you had the condition, while the risk markers
are measured at the same visit. That makes "prediction" the wrong word — the
exposure does not precede the outcome, so estimates are open to reverse
causation (e.g. statin use after a heart attack lowers measured cholesterol).

NCHS links NHANES participants to the National Death Index, which turns the
same cohort into a genuine prospective study: baseline exposures at the exam,
CVD death observed over follow-up. That is what this downloader fetches.

DATA SOURCE
-----------
Public-use LMF, 2019 release (mortality follow-up through 2019-12-31):

    https://ftp.cdc.gov/pub/HEALTH_STATISTICS/NCHS/datalinkage/
        linked_mortality/NHANES_{YYYY}_{YYYY}_MORT_2019_PUBLIC.dat

Covers the ten NHANES cycles 1999-2000 .. 2017-2018. There is NO linkage for
2021-2022 — that cycle is too recent. This is a hard scope boundary: the
survival analysis cohort is 1999-2018, while the COVID comparison uses
2021-2022. They are deliberately different samples answering different
questions; do not silently merge them.

FILE FORMAT
-----------
Fixed-width ASCII, no header. Column positions below were verified empirically
against NHANES_1999_2000_MORT_2019_PUBLIC.dat rather than transcribed from the
codebook PDF (CDC blocks automated access to it):

    cols (1-indexed)  variable       notes
    1-6               SEQN           zero-padded; 5 digits in early cycles
    15                ELIGSTAT       1=eligible, 2=under 18, 3=ineligible
    16                MORTSTAT       0=assumed alive, 1=assumed deceased, .=ineligible
    17-19             UCOD_LEADING   leading-cause group, 001-010; blank if alive
    20                DIABETES       diabetes listed anywhere on death certificate
    21                HYPERTEN       hypertension listed anywhere on death certificate
    43-45             PERMTH_INT     person-months from INTERVIEW to death/censor
    46-48             PERMTH_EXM     person-months from MEC EXAM to death/censor

Records are 46-48 bytes because trailing blanks are stripped; short lines parse
to NaN for the missing tail, which is correct (those fields are blank anyway).

REPRODUCIBILITY
---------------
CDC revises public-use files in place without changing the filename. Every
download is recorded in MANIFEST.json with a SHA-256 digest, byte count and
the server's Last-Modified header, so a later run can prove it is reading the
same bytes. Verify with `--verify`.

Usage:
    python data/download_mortality.py                # download all cycles
    python data/download_mortality.py --dry-run      # probe availability only
    python data/download_mortality.py --verify       # re-hash local files vs manifest
"""

import argparse
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE = (
    "https://ftp.cdc.gov/pub/HEALTH_STATISTICS/NCHS/datalinkage/linked_mortality"
)
RELEASE = "2019"  # mortality follow-up through 2019-12-31
MORT_DIR = Path(__file__).parent / "raw_mortality"
MANIFEST = MORT_DIR / "MANIFEST.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "CardioTrace-Downloader/2.0 (research project)"
    )
}

# NHANES cycles with mortality linkage. 2021-2022 is intentionally absent —
# NCHS has not released linkage for it (see module docstring).
CYCLES: dict[str, str] = {
    "1999-2000": "1999_2000",
    "2001-2002": "2001_2002",
    "2003-2004": "2003_2004",
    "2005-2006": "2005_2006",
    "2007-2008": "2007_2008",
    "2009-2010": "2009_2010",
    "2011-2012": "2011_2012",
    "2013-2014": "2013_2014",
    "2015-2016": "2015_2016",
    "2017-2018": "2017_2018",
}

# Fixed-width layout, 0-indexed half-open, for pandas.read_fwf.
COLSPECS = [(0, 6), (14, 15), (15, 16), (16, 19), (19, 20), (20, 21), (42, 45), (45, 48)]
COLNAMES = [
    "seqn", "eligstat", "mortstat", "ucod_leading",
    "diabetes_on_dc", "hypertension_on_dc", "permth_int", "permth_exm",
]


def cycle_url(cycle: str) -> str:
    return f"{BASE}/NHANES_{CYCLES[cycle]}_MORT_{RELEASE}_PUBLIC.dat"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(cycle: str, retries: int = 4, backoff: float = 2.0) -> dict | None:
    """Stream one cycle's LMF to disk. Returns its manifest entry, or None."""
    url = cycle_url(cycle)
    dest = MORT_DIR / f"NHANES_{CYCLES[cycle]}_MORT_{RELEASE}_PUBLIC.dat"

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 15):
                        f.write(chunk)
                tmp.replace(dest)
                entry = {
                    "cycle": cycle,
                    "file": dest.name,
                    "url": url,
                    "bytes": dest.stat().st_size,
                    "sha256": sha256_of(dest),
                    "server_last_modified": r.headers.get("Last-Modified"),
                    "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                log.info(f"OK    {cycle}  {entry['bytes'] / 1024:.0f} KB  {entry['sha256'][:12]}…")
                return entry
            if r.status_code == 404:
                log.warning(f"n/a   {cycle}: no linkage published (HTTP 404)")
                return None
            log.warning(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            log.warning(f"GET error (attempt {attempt + 1}): {e}")
        time.sleep(backoff ** attempt)

    log.error(f"FAILED after {retries} attempts: {url}")
    return None


def verify() -> bool:
    """Re-hash local files against the manifest. Returns True if all match."""
    if not MANIFEST.exists():
        log.error(f"No manifest at {MANIFEST}. Run the downloader first.")
        return False

    entries = json.loads(MANIFEST.read_text())["files"]
    ok = True
    for e in entries:
        path = MORT_DIR / e["file"]
        if not path.exists():
            log.error(f"MISSING   {e['file']}")
            ok = False
            continue
        actual = sha256_of(path)
        if actual != e["sha256"]:
            log.error(f"MISMATCH  {e['file']}\n  manifest={e['sha256']}\n  actual  ={actual}")
            ok = False
        else:
            log.info(f"OK        {e['file']}")
    log.info("All files match the manifest." if ok else "VERIFICATION FAILED.")
    return ok


def run(dry_run: bool = False) -> list[dict]:
    if dry_run:
        for cycle in CYCLES:
            url = cycle_url(cycle)
            r = requests.head(url, headers=HEADERS, timeout=30, allow_redirects=True)
            size = r.headers.get("Content-Length", "?")
            print(f"  {cycle}  HTTP {r.status_code}  {size} bytes  {url}")
        return []

    entries = [e for c in CYCLES if (e := download_one(c)) is not None]

    MORT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "release": RELEASE,
        "follow_up_through": "2019-12-31",
        "source": BASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    }, indent=2))
    log.info(f"{len(entries)}/{len(CYCLES)} cycles downloaded. Manifest → {MANIFEST}")
    return entries


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Download NHANES public-use Linked Mortality Files")
    ap.add_argument("--dry-run", action="store_true", help="Probe availability without downloading")
    ap.add_argument("--verify", action="store_true", help="Re-hash local files against MANIFEST.json")
    args = ap.parse_args()

    if args.verify:
        raise SystemExit(0 if verify() else 1)
    run(dry_run=args.dry_run)
