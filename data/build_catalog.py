"""
Stage 0 — enumerate EVERY NHANES public data file, before deciding what to keep.

WHY THIS EXISTS
---------------
`legacy-invalid/data/download.py` hardcoded 17 module names (TCHOL, GLU, BIOPRO, ...) and
HEAD-probes them in every cycle, treating a 404 as "that panel wasn't run this
cycle". That assumption is false. CDC renamed the laboratory modules partway
through the series: the 1999-2004 cycles publish the same assays under LAB##
names.

    concept                     2005+        1999-2000
    total cholesterol / HDL     TCHOL, HDL   LAB13
    LDL / triglycerides         TRIGLY       LAB13AM
    glycohemoglobin             GHB          LAB10
    fasting glucose             GLU          LAB10AM
    standard biochemistry       BIOPRO       LAB18
    C-reactive protein          CRP          LAB11
    urine albumin/creatinine    ALB_CR       LAB16

The probes for TCHOL/GLU/... 404 in 1999-2004, so those cycles silently entered
the warehouse with NO laboratory data at all — 15,332 adults (24.4% of the
analysis sample) whose cholesterol, HbA1c, glucose, CRP and creatinine were
then median-imputed downstream. Fabricated values, in the published figures.

The fix is not "download everything". It is: enumerate everything (cheap —
metadata only), then exclude by written rules (auditable). This script does the
enumeration. It answers, with evidence, the question a reviewer will ask:
"how do you know you didn't miss anything?"

WHAT IT PRODUCES
----------------
    data/catalog/nhanes_file_catalog.csv   one row per (cycle, component, file)
    data/catalog/coverage_by_concept.csv   concept x cycle -> module name actually used

Source of truth is CDC's own per-cycle file listing, which carries the real
download URL for each file:

    https://wwwn.cdc.gov/nchs/nhanes/search/datapage.aspx
        ?Component={component}&CycleBeginYear={year}

Usage:
    python data/build_catalog.py                    # build both CSVs
    python data/build_catalog.py --component Laboratory
"""

import argparse
import csv
import html
import logging
import re
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

LISTING = "https://wwwn.cdc.gov/nchs/nhanes/search/datapage.aspx"
FILE_HOST = "https://wwwn.cdc.gov"
CATALOG_DIR = Path(__file__).parent / "catalog"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    )
}

# Cycle label -> CycleBeginYear query parameter (same cycles as download.py).
CYCLES = {
    "1999-2000": 1999, "2001-2002": 2001, "2003-2004": 2003,
    "2005-2006": 2005, "2007-2008": 2007, "2009-2010": 2009,
    "2011-2012": 2011, "2013-2014": 2013, "2015-2016": 2015,
    "2017-2018": 2017, "2021-2022": 2021,
}

# All six components are enumerated. LimitedAccess is catalogued and flagged,
# not downloaded — it requires an NCHS Research Data Center application. It is
# listed here so the exclusion is on the record rather than invisible.
COMPONENTS = [
    "Demographics", "Dietary", "Examination",
    "Laboratory", "Questionnaire", "LimitedAccess",
]

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td.*?>(.*?)</td>", re.S)
HREF_RE = re.compile(r'href="([^"]+)"')
SIZE_RE = re.compile(r"\[[A-Z]+ - ([\d.]+)\s*([KMG]B)\]")

# Concepts CardioTrace needs, matched case-insensitively against the CDC file
# label. Used only to build the coverage report — the catalog itself is complete
# and unfiltered.
CONCEPTS = {
    "cholesterol_total_hdl": r"cholesterol.*(total|hdl)|total.*cholesterol",
    "cholesterol_ldl_trig":  r"(ldl|triglycerid)",
    "glycohemoglobin":       r"glycohemoglobin|glycated h",
    "fasting_glucose":       r"fasting glucose|plasma fasting",
    "biochemistry":          r"biochemistry",
    "crp":                   r"c-reactive",
    "urine_albumin_creat":   r"albumin.*creatinine",
    "blood_pressure":        r"^blood pressure",
    "body_measures":         r"body measures",
    "demographics":          r"demographic",
    "medical_conditions":    r"medical conditions",
    "prescription_meds":     r"prescription medic",
    "health_insurance":      r"health insurance",
    "alcohol":               r"alcohol use",
    "smoking":               r"smoking.*cigarette use|smoking - cigarette",
    "physical_activity":     r"^physical activity$",
    "diabetes":              r"^diabetes$",
    "sleep":                 r"sleep disorder",
    "cardiovascular_health": r"cardiovascular health",
    "diet_total_nutrients":  r"total nutrient intakes",
}


def parse_listing(page: str, cycle: str, component: str) -> list[dict]:
    """Parse one datapage.aspx table into catalog rows."""
    out = []
    for raw in ROW_RE.findall(page):
        cells = CELL_RE.findall(raw)
        if len(cells) < 4:
            continue

        def text(c: str) -> str:
            return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c))).strip()

        label = text(cells[0])
        doc_href = HREF_RE.search(cells[1])
        data_href = HREF_RE.search(cells[2])
        published = text(cells[3])

        # Limited-access rows have no downloadable data file.
        data_url = FILE_HOST + data_href.group(1) if data_href else ""
        module = Path(data_url).stem.upper() if data_url else ""

        size_m = SIZE_RE.search(cells[2])
        size_kb = ""
        if size_m:
            v, unit = float(size_m.group(1)), size_m.group(2)
            size_kb = round(v * {"KB": 1, "MB": 1024, "GB": 1024 ** 2}[unit], 1)

        out.append({
            "cycle": cycle,
            "component": component,
            "file_label": label,
            "module": module,
            "data_url": data_url,
            "doc_url": FILE_HOST + doc_href.group(1) if doc_href else "",
            "size_kb": size_kb,
            "date_published": published,
            "downloadable": bool(data_url),
        })
    return out


def fetch(component: str, cycle: str, begin_year: int) -> list[dict]:
    url = f"{LISTING}?Component={component}&CycleBeginYear={begin_year}"
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    rows = parse_listing(r.text, cycle, component)
    log.info(f"{cycle}  {component:14s}  {len(rows):3d} files")
    return rows


def module_stem(module: str) -> str:
    """Strip the biennial cycle suffix: DEMO_J -> DEMO, LAB13AM -> LAB13AM.

    Every cycle after 1999-2000 appends a single-letter suffix (_B .. _L) to the
    module name. That suffix is the cycle marker, not a different instrument, so
    it must be removed before asking whether a concept was RENAMED across the
    series. Without this, DEMO/DEMO_B/DEMO_C look like three different modules
    and every concept is falsely reported as drifting.
    """
    return re.sub(r"_[A-L]$", "", module)


def coverage_report(rows: list[dict]) -> list[dict]:
    """For each concept, which module carries it in each cycle, and whether the
    name drifts. A drifting concept is one a hardcoded module list would drop."""
    out = []
    for concept, pattern in CONCEPTS.items():
        rx = re.compile(pattern, re.I)
        rec = {"concept": concept}
        stems: set[str] = set()
        for cycle in CYCLES:
            hits = sorted({
                r["module"] for r in rows
                if r["cycle"] == cycle and r["module"] and rx.search(r["file_label"])
            })
            rec[cycle] = "|".join(hits)
            stems |= {module_stem(h) for h in hits}
        rec["n_cycles_covered"] = sum(1 for c in CYCLES if rec[c])
        rec["distinct_module_stems"] = "|".join(sorted(stems))
        rec["name_drifts"] = len(stems) > 1
        out.append(rec)
    return out


def load_catalog() -> list[dict]:
    """Read the catalog CSV written by a previous run (no network access)."""
    path = CATALOG_DIR / "nhanes_file_catalog.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_coverage(rows: list[dict]) -> list[dict]:
    cov = coverage_report(rows)
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path = CATALOG_DIR / "coverage_by_concept.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cov[0].keys()))
        w.writeheader()
        w.writerows(cov)
    log.info(f"coverage report -> {path}")

    drifted = [c for c in cov if c["name_drifts"]]
    if drifted:
        log.warning(
            f"{len(drifted)} concept(s) change module name across cycles — a "
            "hardcoded module list silently drops those cycles:"
        )
        for c in drifted:
            log.warning(f"    {c['concept']:24s} {c['distinct_module_stems']}")
    gaps = [c for c in cov if c["n_cycles_covered"] < len(CYCLES)]
    for c in gaps:
        missing = [cy for cy in CYCLES if not c[cy]]
        log.info(f"    {c['concept']:24s} absent in {len(missing)} cycle(s): {', '.join(missing)}")
    return cov


def run(components: list[str] | None = None) -> list[dict]:
    comps = components or COMPONENTS
    rows: list[dict] = []
    for cycle, year in CYCLES.items():
        for comp in comps:
            try:
                rows += fetch(comp, cycle, year)
            except requests.RequestException as e:
                log.warning(f"{cycle} {comp}: {e}")
            time.sleep(0.3)  # be polite to CDC servers

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    cat_path = CATALOG_DIR / "nhanes_file_catalog.csv"
    with open(cat_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    log.info(f"{len(rows)} files catalogued -> {cat_path}")

    write_coverage(rows)
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Enumerate all NHANES public files")
    ap.add_argument("--component", action="append", choices=COMPONENTS,
                    help="Limit to one or more components (default: all)")
    ap.add_argument("--coverage-only", action="store_true",
                    help="Rebuild the coverage report from the cached catalog CSV")
    args = ap.parse_args()

    if args.coverage_only:
        write_coverage(load_catalog())
    else:
        run(components=args.component)
