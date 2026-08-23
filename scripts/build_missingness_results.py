"""Disclose who the complete-case analysis drops, and test whether it matters.

`.dropna()` inside `models._fit` redefines the population without saying so.
This writes the three things a reader needs in order to judge that decision for
themselves: what causes the deletion, who is lost, and whether re-weighting
towards the full cohort moves the answer.

Writes:
  reports/tables/part3_missing_drivers.csv     which variable costs which rows
  reports/tables/part3_missing_compare.csv     kept versus dropped
  reports/tables/part3_missing_sensitivity.csv the exposure HR under both weightings
  reports/missingness_results.json             what the report interpolates
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.missingness import pattern, sensitivity  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed" / "cohort_part3.csv.gz"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "reports" / "missingness_results.json"


def main() -> None:
    if not PROCESSED.exists():
        raise SystemExit(f"{PROCESSED} is missing; run scripts/build_cohort_results.py")
    TABLES.mkdir(parents=True, exist_ok=True)

    cohort = pd.read_csv(PROCESSED)
    drivers, compare = pattern(cohort)
    sens = sensitivity(cohort)

    drivers.to_csv(TABLES / "part3_missing_drivers.csv", index=False)
    compare.to_csv(TABLES / "part3_missing_compare.csv", index=False)
    sens.to_csv(TABLES / "part3_missing_sensitivity.csv", index=False)

    kept, dropped = compare.attrs["n_kept"], compare.attrs["n_dropped"]
    base, ipcw_row = sens.iloc[0], sens.iloc[1]
    top = drivers.iloc[0]

    def diff(v):
        return float(compare.loc[compare["variable"] == v, "difference"].iloc[0])

    results = {
        "n_cohort": int(len(cohort)),
        "n_analysed": kept,
        "n_dropped": dropped,
        "pct_dropped": round(100 * dropped / (kept + dropped), 2),
        "top_driver": str(top["variable"]),
        "top_driver_uniquely_lost": int(top["n_uniquely_lost"]),
        # The two differences that decide whether this is a footnote or a
        # limitation. Both are in the direction that matters.
        "cvd_death_kept": float(compare.loc[compare["variable"] == "cvd_death",
                                            "kept_mean"].iloc[0]),
        "cvd_death_dropped": float(compare.loc[compare["variable"] == "cvd_death",
                                               "dropped_mean"].iloc[0]),
        "race_black_kept": float(compare.loc[compare["variable"] == "race_black",
                                             "kept_mean"].iloc[0]),
        "race_black_dropped": float(compare.loc[compare["variable"] == "race_black",
                                                "dropped_mean"].iloc[0]),
        "race_black_diff": diff("race_black"),
        "sensitivity": {
            "n": int(base["n"]),
            "hr_survey": float(base["hr_per_10mmhg"]),
            "hr_survey_ci": [float(base["lo95"]), float(base["hi95"])],
            "hr_ipcw": float(ipcw_row["hr_per_10mmhg"]),
            "hr_ipcw_ci": [float(ipcw_row["lo95"]), float(ipcw_row["hi95"])],
            "abs_shift": round(abs(float(ipcw_row["hr_per_10mmhg"])
                                   - float(base["hr_per_10mmhg"])), 4),
        },
    }
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(f"  cohort {results['n_cohort']:,} -> analysed {kept:,} "
          f"({results['pct_dropped']:.1f}% dropped)")
    print(f"  biggest single cause: {top['variable']} "
          f"({top['n_uniquely_lost']} rows lost to it alone)")
    print(f"  CVD mortality  kept {100 * results['cvd_death_kept']:.2f}%  "
          f"dropped {100 * results['cvd_death_dropped']:.2f}%")
    print(f"  Black          kept {100 * results['race_black_kept']:.1f}%  "
          f"dropped {100 * results['race_black_dropped']:.1f}%")
    print(f"  exposure HR    survey {results['sensitivity']['hr_survey']:.4f}  "
          f"IPCW {results['sensitivity']['hr_ipcw']:.4f}  "
          f"shift {results['sensitivity']['abs_shift']:.4f}")


if __name__ == "__main__":
    main()
