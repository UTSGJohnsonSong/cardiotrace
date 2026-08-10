"""
PCE feasibility cascade — how much sample does each alignment filter cost?

The advisor's guidance (meeting 3): don't decide how strictly to match the ASCVD
Pooled Cohort Equations in the abstract. Filter one column at a time, look at
where the nulls actually are, and only then decide whether a filter is worth its
cost. Where a column is expensive, consider imputing a risk-neutral value rather
than dropping the person.

This script answers that empirically for the Part 3 cohort.

It builds on src.cohort rather than assembling its own frame. An earlier version
duplicated read_cols/build_cycle here, and the copies diverged exactly where it
hurt: the blood-pressure fallback and the BPQ skip-pattern decode were both
fixed in src/cohort.py and left stale here, so this table reported a cost the
pipeline no longer paid. One builder, one set of decisions.

Output: reports/tables/pce_cascade.csv
"""

import csv
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.cohort import (  # noqa: E402
    AGE_MAX, AGE_MIN, CYCLES, build_cycle, load_crosswalk,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

OUT = Path(__file__).parent.parent / "reports" / "tables" / "pce_cascade.csv"

# The nine inputs the 2013 ACC/AHA Pooled Cohort Equations require, named as
# src.cohort produces them.
PCE_INPUTS = [
    ("age", "age 40-79"),
    ("sex", "sex"),
    ("race_black", "race (Black vs other)"),
    ("total_cholesterol", "total cholesterol"),
    ("hdl_cholesterol", "HDL cholesterol"),
    ("systolic_bp", "systolic BP"),
    ("bp_treated", "on BP medication"),
    ("diabetes_dx", "diabetes"),
    ("current_smoker", "current smoker"),
]


def main() -> None:
    xw = load_crosswalk()
    df = pd.concat([build_cycle(c, xw) for c in CYCLES], ignore_index=True)
    log.info(f"Pooled 1999-2014: {len(df):,} participants (all ages)\n")

    n0 = len(df)
    steps = [("start: all 1999-2014 respondents", df)]
    df = df[df.age.between(AGE_MIN, AGE_MAX)]
    steps.append((f"age {AGE_MIN}-{AGE_MAX}", df))
    df = df[df.wtmec2yr.fillna(0) > 0]
    steps.append(("MEC exam weight > 0", df))
    df = df[df.prev_cvd == 0]
    steps.append(("free of self-reported CVD at baseline", df))

    rows, prev = [], n0
    for label, d in steps:
        rows.append({"section": "cohort", "step": label, "n": len(d),
                     "lost": prev - len(d),
                     "pct_of_section_start": round(100 * len(d) / n0, 1)})
        prev = len(d)

    log.info(f"{'cohort restriction':40s}{'N':>9s}{'lost':>9s}{'%':>8s}")
    for r in rows:
        log.info(f"{r['step']:40s}{r['n']:9,d}{r['lost']:9,d}{r['pct_of_section_start']:7.1f}%")

    base = df
    missing = [c for c, _ in PCE_INPUTS if c not in base.columns]
    if missing:
        # A PCE input that was never constructed used to be logged and skipped,
        # so the cascade never charged its cost and the alignment looked cheaper
        # than it is. That is a wrong number in a table the advisor reads.
        raise KeyError(f"PCE inputs absent from the cohort frame: {missing}")

    log.info(f"\n{'PCE input':40s}{'missing':>9s}{'%':>8s}")
    miss = []
    for col, label in PCE_INPUTS:
        n_miss = int(base[col].isna().sum())
        miss.append((col, label, n_miss))
        log.info(f"{label:40s}{n_miss:9,d}{100 * n_miss / len(base):7.1f}%")

    # Drop one required column at a time, most-complete first, so the marginal
    # cost of each additional requirement is visible rather than pooled.
    log.info(f"\n{'cascade (ascending missingness)':40s}{'N':>9s}{'lost':>9s}{'%':>8s}")
    cur, start, cascade = base, len(base), []
    for col, label, _ in sorted(miss, key=lambda x: x[2]):
        before = len(cur)
        cur = cur[cur[col].notna()]
        # Its own section: this block's denominator is the post-exclusion cohort,
        # not the survey total. Written to one CSV without a marker, the two
        # blocks silently mixed two different 100% baselines.
        cascade.append({"section": "pce_inputs", "step": f"require {label} non-null",
                        "n": len(cur), "lost": before - len(cur),
                        "pct_of_section_start": round(100 * len(cur) / start, 1)})
        log.info(f"{'require ' + label + ' non-null':40s}{len(cur):9,d}"
                 f"{before - len(cur):9,d}{100 * len(cur) / start:7.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "step", "n", "lost",
                                          "pct_of_section_start"])
        w.writeheader()
        w.writerows(rows + cascade)
    log.info(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
