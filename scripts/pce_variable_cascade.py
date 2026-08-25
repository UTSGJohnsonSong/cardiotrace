"""
PCE feasibility cascade — how much sample does each alignment filter cost?

The advisor's guidance (meeting 3): don't decide how strictly to match the ASCVD
Pooled Cohort Equations in the abstract. Filter one column at a time, look at
where the nulls actually are, and only then decide whether a filter is worth its
cost. Where a column is expensive, consider imputing a risk-neutral value rather
than dropping the person.

This script answers that empirically for the Part 3 cohort.

It reads the PUBLISHED cohort rather than assembling its own frame. Two earlier
versions each got this wrong in the same direction. The first duplicated
read_cols/build_cycle here and the copies diverged exactly where it hurt: the
blood-pressure fallback and the BPQ skip-pattern decode were both fixed in
src/cohort.py and left stale here. The second called build_cycle and re-applied
its own restriction ladder -- age, exam weight, prevalent CVD -- which is a
STRICT SUBSET of the ladder build_cohort applies. It silently skipped linkage
eligibility, MEC completion and cause-of-death coding, so it started from 20,771
people where the analysis cohort has 20,736, and the feasibility of a filter was
being reported against 35 people who are not in the study.

Now the cohort section is strobe_part3.csv verbatim and the input section runs
on cohort_part3.csv.gz. Neither can drift from what was published, because
neither is recomputed here.

Output: reports/tables/pce_cascade.csv
"""

import csv
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
OUT = ROOT / "reports" / "tables" / "pce_cascade.csv"

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
    strobe_p = ROOT / "reports" / "tables" / "strobe_part3.csv"
    cohort_p = ROOT / "data" / "processed" / "cohort_part3.csv.gz"
    for f in (strobe_p, cohort_p):
        if not f.exists():
            raise SystemExit(
                f"{f.relative_to(ROOT)} is missing. This table reports the cost "
                f"of each PCE filter ON THE PUBLISHED COHORT and will not "
                f"reconstruct one. Run `make cohort` first.")

    strobe = pd.read_csv(strobe_p)
    df = pd.read_csv(cohort_p)
    n0 = int(strobe["n"].iloc[0])

    # The cohort section is the STROBE ladder as published -- copied, not
    # recomputed. If it were recomputed the two tables could disagree, and the
    # last two times this script owned a ladder of its own, they did.
    rows = [{"section": "cohort", "step": r.step, "n": int(r.n),
             "lost": int(r.excluded),
             "pct_of_section_start": round(100 * int(r.n) / n0, 1),
             "cvd_deaths": ("" if pd.isna(r.cvd_deaths) else int(r.cvd_deaths))}
            for r in strobe.itertuples()]

    log.info(f"{'cohort restriction (STROBE, as published)':44s}"
             f"{'N':>9s}{'lost':>9s}{'%':>8s}")
    for r in rows:
        log.info(f"{r['step']:44s}{r['n']:9,d}{r['lost']:9,d}"
                 f"{r['pct_of_section_start']:7.1f}%")

    if len(df) != rows[-1]["n"]:
        raise SystemExit(
            f"the cohort file holds {len(df):,} rows but the STROBE ladder ends "
            f"at {rows[-1]['n']:,}. One of the two is stale; rebuild both.")

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
                        "pct_of_section_start": round(100 * len(cur) / start, 1),
                        "cvd_deaths": int((cur.cvd_death == 1).sum())})
        log.info(f"{'require ' + label + ' non-null':40s}{len(cur):9,d}"
                 f"{before - len(cur):9,d}{100 * len(cur) / start:7.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["section", "step", "n", "lost", "cvd_deaths",
                                          "pct_of_section_start"])
        w.writeheader()
        w.writerows(rows + cascade)
    log.info(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
