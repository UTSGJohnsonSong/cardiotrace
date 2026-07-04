"""
NHANES downloader for CardioTrace.

NHANES public-use files live at fully deterministic URLs. After CDC's 2024 site
migration the pattern is:

    https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{BEGIN_YEAR}/DataFiles/{MODULE}{SUFFIX}.xpt

where BEGIN_YEAR is the first year of the cycle (e.g. 2017 for 2017-2018) and
every biennial cycle has a one-letter suffix (1999-2000 = none, 2001-2002 = _B,
... 2017-2018 = _J, 2021-2022 = _L). Rather than scrape fragile HTML, this
downloader builds each candidate URL, HEAD-probes whether it exists, and
downloads it if so. Missing modules in a given cycle simply 404 and are skipped
— that is expected (not every lab panel runs every cycle).

Cycle selection — we use the 11 NON-OVERLAPPING biennial cycles only:

    1999-2000 ... 2017-2018   (ten standard 2-year cycles)
    2021-2022                 (released as "August 2021-August 2023", suffix _L)

We deliberately DO NOT download the special 2017-2020 "pre-pandemic" combined
file (P_ prefix). That file pools 2017-2018 with the partial 2019-2020 wave, so
including it alongside 2017-2018 would double-count participants and corrupt
pooled prevalence estimates. The 2019-2020 wave was never released on its own
(COVID halted fieldwork), which is why there is a real gap before 2021-2022 —
that gap is exactly what makes the pre/post-COVID comparison clean.

Usage:
    python data/download.py                          # all cycles, all modules
    python data/download.py --modules DEMO MCQ BMX   # specific modules
    python data/download.py --cycles 2017-2018       # specific cycle(s)
    python data/download.py --dry-run                # probe only, no download
"""

import argparse
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

BASE    = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public"
RAW_DIR = Path(__file__).parent / "raw"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "CardioTrace-Downloader/2.0 (research project)"
    )
}

# Non-overlapping biennial cycles → (URL begin-year segment, file suffix).
CYCLES: dict[str, tuple[str, str]] = {
    "1999-2000": ("1999", ""),
    "2001-2002": ("2001", "_B"),
    "2003-2004": ("2003", "_C"),
    "2005-2006": ("2005", "_D"),
    "2007-2008": ("2007", "_E"),
    "2009-2010": ("2009", "_F"),
    "2011-2012": ("2011", "_G"),
    "2013-2014": ("2013", "_H"),
    "2015-2016": ("2015", "_I"),
    "2017-2018": ("2017", "_J"),
    "2021-2022": ("2021", "_L"),
}

# Modules we ingest. Naming is stable across cycles except where noted; modules
# that don't exist in a cycle 404 and are skipped. We probe both manual (BPX)
# and oscillometric (BPXO) blood pressure, and both CRP and HSCRP, because CDC
# switched instruments/panels partway through the series.
TARGET_MODULES = [
    "DEMO", "MCQ", "BPQ", "BPX", "BPXO", "BMX", "DIQ", "SMQ", "PAQ",
    "TCHOL", "HDL", "TRIGLY", "GHB", "GLU", "BIOPRO", "CRP", "HSCRP",
]


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def head_exists(url: str, retries: int = 3, backoff: float = 2.0) -> bool:
    """Return True if the URL resolves to a real file (HTTP 200)."""
    for attempt in range(retries):
        try:
            r = requests.head(url, headers=HEADERS, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                return True
            if r.status_code == 404:
                return False
            log.debug(f"HTTP {r.status_code} (HEAD) for {url}")
        except requests.RequestException as e:
            log.debug(f"HEAD error (attempt {attempt + 1}): {e}")
        time.sleep(backoff ** attempt)
    return False


def download(url: str, dest: Path, retries: int = 4, backoff: float = 2.0) -> bool:
    """Stream a file to disk. Returns True on success."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            if r.status_code == 200:
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".part")
                size = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 15):
                        f.write(chunk)
                        size += len(chunk)
                tmp.replace(dest)
                log.info(f"OK    {dest.parent.name}/{dest.name}  ({size / 1024:.0f} KB)")
                return True
            if r.status_code == 404:
                return False
            log.warning(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            log.warning(f"GET error (attempt {attempt + 1}): {e}")
        time.sleep(backoff ** attempt)
    log.error(f"FAILED after {retries} attempts: {url}")
    return False


# ── Core ─────────────────────────────────────────────────────────────────────

def candidate_url(module: str, cycle: str) -> str:
    begin_year, suffix = CYCLES[cycle]
    return f"{BASE}/{begin_year}/DataFiles/{module}{suffix}.xpt"


def run(
    modules: list[str] | None = None,
    cycles: list[str] | None = None,
    dry_run: bool = False,
):
    want_modules = [m.upper() for m in modules] if modules else TARGET_MODULES
    want_cycles = cycles if cycles else list(CYCLES.keys())

    unknown = [c for c in want_cycles if c not in CYCLES]
    if unknown:
        log.warning(f"Unknown cycle(s) ignored: {unknown}. Valid: {list(CYCLES)}")
        want_cycles = [c for c in want_cycles if c in CYCLES]

    stats = {"downloaded": 0, "skipped_exists": 0, "not_available": 0, "failed": 0}

    for cycle in want_cycles:
        cycle_dir = RAW_DIR / cycle
        for module in want_modules:
            url = candidate_url(module, cycle)
            _, suffix = CYCLES[cycle]
            dest = cycle_dir / f"{module}{suffix}.XPT"

            if dest.exists():
                log.debug(f"SKIP  {cycle}/{dest.name} (already downloaded)")
                stats["skipped_exists"] += 1
                continue

            if not head_exists(url):
                log.debug(f"n/a   {cycle}/{module} (not published this cycle)")
                stats["not_available"] += 1
                continue

            if dry_run:
                print(f"  WOULD DOWNLOAD  {module:8s}  {url}")
                continue

            ok = download(url, dest)
            stats["downloaded" if ok else "failed"] += 1
            time.sleep(0.2)  # be polite to CDC servers

    log.info("=" * 48)
    for k, v in stats.items():
        log.info(f"{k:18s}: {v}")
    return stats


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download NHANES XPT files for CardioTrace")
    parser.add_argument("--modules", nargs="+", help="Module codes (default: all target modules)")
    parser.add_argument("--cycles", nargs="+", help="Cycle labels e.g. 2017-2018 (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Probe availability without downloading")
    args = parser.parse_args()

    run(modules=args.modules, cycles=args.cycles, dry_run=args.dry_run)
