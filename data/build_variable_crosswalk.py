"""
Stage 2 — build a per-cycle VARIABLE crosswalk, verified against the files.

WHY
---
Fixing the filename drift (LAB13 -> L13 -> TCHOL+HDL) was only half the bug.
The variable names inside those files drift too, and the staging layer hardcodes
one name per analyte. Downloading LAB13 does nothing if stg_risk_factors.sql
still only reads `lbdhdd`.

Four drifts found by scanning the actual files:

    HDL cholesterol   LBDHDL (1999-2002) -> LBXHDD (2003-2004) -> LBDHDD (2005+)
    serum creatinine  LBXSCR everywhere EXCEPT 2001-2002, which uses LBDSCR
    triglycerides     LBXTR (mg/dL) through 2017-2018; 2021-2022 publishes only
                      LBDTRSI (mmol/L) -> needs x88.57 to stay on one scale
    LDL cholesterol   three equations appear in recent cycles (Friedewald,
                      Martin-Hopkins, NIH-2). Only Friedewald spans the series.

The triglyceride entry is why this file scopes candidates to specific source
modules. `LBXSTR` also exists — in the biochemistry panel, as "Triglycerides,
refrig serum", a NON-FASTING measurement. Matching on variable name alone would
have silently mixed fasting lipid-panel values with non-fasting biochemistry
values in one column.

Output: data/catalog/variable_crosswalk.csv
    analyte, cycle, source_module, variable, unit, to_canonical

The ETL/staging layer reads this instead of hardcoding names.

Usage:
    python data/build_variable_crosswalk.py
"""

import csv
import logging
import os
import re
from pathlib import Path

import pyreadstat

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "catalog" / "variable_crosswalk.csv"

# analyte -> (canonical unit, [(module stem prefix, variable, unit, factor)])
# Candidates are ordered; the first one present in a cycle wins. Scoping the
# search to a module stem is what keeps the fasting lipid panel separate from
# the non-fasting biochemistry panel.
ANALYTES: dict[str, tuple[str, list[tuple[str, str, str, float]]]] = {
    "total_cholesterol": ("mg/dL", [
        ("LAB13", "LBXTC", "mg/dL", 1.0), ("L13", "LBXTC", "mg/dL", 1.0),
        ("TCHOL", "LBXTC", "mg/dL", 1.0),
    ]),
    "hdl_cholesterol": ("mg/dL", [
        ("LAB13", "LBDHDL", "mg/dL", 1.0),   # 1999-2000
        ("L13", "LBDHDL", "mg/dL", 1.0),     # 2001-2002
        ("L13", "LBXHDD", "mg/dL", 1.0),     # 2003-2004 — third spelling
        ("HDL", "LBDHDD", "mg/dL", 1.0),     # 2005+
    ]),
    "ldl_cholesterol": ("mg/dL", [
        # Friedewald only: the sole equation published in every cycle.
        ("LAB13AM", "LBDLDL", "mg/dL", 1.0), ("L13AM", "LBDLDL", "mg/dL", 1.0),
        ("TRIGLY", "LBDLDL", "mg/dL", 1.0),
    ]),
    "triglycerides": ("mg/dL", [
        ("LAB13AM", "LBXTR", "mg/dL", 1.0), ("L13AM", "LBXTR", "mg/dL", 1.0),
        ("TRIGLY", "LBXTR", "mg/dL", 1.0),
        # 2021-2022 dropped the mg/dL column; convert from SI.
        ("TRIGLY", "LBDTRSI", "mmol/L", 88.57),
    ]),
    "hba1c": ("%", [
        ("LAB10", "LBXGH", "%", 1.0), ("L10", "LBXGH", "%", 1.0),
        ("GHB", "LBXGH", "%", 1.0),
    ]),
    "fasting_glucose": ("mg/dL", [
        ("LAB10AM", "LBXGLU", "mg/dL", 1.0), ("L10AM", "LBXGLU", "mg/dL", 1.0),
        ("GLU", "LBXGLU", "mg/dL", 1.0),
    ]),
    "creatinine": ("mg/dL", [
        ("LAB18", "LBXSCR", "mg/dL", 1.0),
        ("L40", "LBXSCR", "mg/dL", 1.0),
        ("L40", "LBDSCR", "mg/dL", 1.0),     # 2001-2002 only
        ("BIOPRO", "LBXSCR", "mg/dL", 1.0),
    ]),
    "uric_acid": ("mg/dL", [
        ("LAB18", "LBXSUA", "mg/dL", 1.0), ("L40", "LBXSUA", "mg/dL", 1.0),
        ("BIOPRO", "LBXSUA", "mg/dL", 1.0),
    ]),
    "urine_albumin": ("ug/mL", [
        ("LAB16", "URXUMA", "ug/mL", 1.0), ("L16", "URXUMA", "ug/mL", 1.0),
        ("ALB_CR", "URXUMA", "ug/mL", 1.0),
    ]),
    "urine_creatinine": ("mg/dL", [
        ("LAB16", "URXUCR", "mg/dL", 1.0), ("L16", "URXUCR", "mg/dL", 1.0),
        ("ALB_CR", "URXUCR", "mg/dL", 1.0),
    ]),
}

EXPECTED_CYCLES = 11


def stem(module: str) -> str:
    return re.sub(r"_[A-L]$", "", module)


def scan() -> dict[str, dict[str, set[str]]]:
    """cycle -> {module stem: set of variable names present}"""
    found: dict[str, dict[str, set[str]]] = {}
    for cyc in sorted(d for d in os.listdir(RAW_DIR) if (RAW_DIR / d).is_dir()):
        found[cyc] = {}
        for fn in sorted(os.listdir(RAW_DIR / cyc)):
            if not fn.endswith(".XPT"):
                continue
            try:
                _, meta = pyreadstat.read_xport(
                    str(RAW_DIR / cyc / fn), encoding="LATIN1", metadataonly=True)
            except Exception as e:
                log.warning(f"  unreadable: {cyc}/{fn}: {type(e).__name__}")
                continue
            found[cyc][stem(Path(fn).stem.upper())] = {v.upper() for v in meta.column_names}
    return found


def main() -> None:
    found = scan()
    rows, gaps = [], []

    for analyte, (canon_unit, candidates) in ANALYTES.items():
        for cyc in found:
            hit = None
            for mod_stem, var, unit, factor in candidates:
                if var in found[cyc].get(mod_stem, set()):
                    hit = (mod_stem, var, unit, factor)
                    break
            if hit is None:
                gaps.append((analyte, cyc))
                continue
            mod_stem, var, unit, factor = hit
            rows.append({
                "analyte": analyte, "cycle": cyc, "source_module": mod_stem,
                "variable": var, "unit": unit, "canonical_unit": canon_unit,
                "to_canonical": factor,
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    cycles = sorted(found)
    log.info(f"{'analyte':20s}" + "".join(c[2:4] + c[-2:] + " " for c in cycles))
    for analyte in ANALYTES:
        line = f"{analyte:20s}"
        for cyc in cycles:
            r = next((x for x in rows if x["analyte"] == analyte and x["cycle"] == cyc), None)
            mark = r["variable"][:7] if r else "--"
            if r and r["to_canonical"] != 1.0:
                mark += "*"
            line += f"{mark:9s}"
        log.info(line)
    log.info("\n* = unit conversion applied to reach the canonical unit")
    log.info(f"\n{len(rows)} analyte-cycle mappings -> {OUT}")

    if gaps:
        log.error(f"\n{len(gaps)} analyte-cycle combination(s) NOT FOUND:")
        for a, c in gaps:
            log.error(f"  {a:20s} {c}")
        raise SystemExit(1)
    log.info("Every analyte resolves in all 11 cycles.")


if __name__ == "__main__":
    main()
