"""Produce the Part 3 cohort table and its participant flow.

`build_cohort` has always returned the STROBE flow alongside the cohort, and
nothing has ever written it. The table shipped in the report came from an
interactive session, so it could not be regenerated and nothing would have
caught it drifting -- which is how its step labels stayed in the analyst's
working language inside an English report for as long as they did.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.cohort import build_cohort  # noqa: E402

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    cohort, strobe = build_cohort()
    cohort.to_csv(PROCESSED / "cohort_part3.csv.gz", index=False)
    strobe.to_csv(TABLES / "strobe_part3.csv", index=False)

    # The report and the site both state these. Until now three of them were
    # typed into render_report.py by hand, which is the one thing this project
    # does not allow anywhere else.
    (ROOT / "reports" / "cohort_results.json").write_text(
        json.dumps({
            "n_participants":     int(len(cohort)),
            "cvd_deaths":         int(cohort["cvd_death"].sum()),
            "competing_deaths":   int(cohort["competing_death"].sum()),
            "person_years":       round(float(cohort["followup_years"].sum()), 1),
            "max_followup_years": round(float(cohort["followup_years"].max()), 2),
            "median_followup_years": round(float(cohort["followup_years"].median()), 2),
        }, indent=2) + "\n", encoding="utf-8")

    print(f"cohort: {len(cohort):,} participants, "
          f"{int(cohort['cvd_death'].sum()):,} CVD deaths, "
          f"{int(cohort['competing_death'].sum()):,} competing deaths")
    print(f"person-years: {cohort['followup_years'].sum():,.0f}")
    for r in strobe.itertuples(index=False):
        print(f"  {r[0]:<44s} {r[1]:>7,}")


if __name__ == "__main__":
    main()
