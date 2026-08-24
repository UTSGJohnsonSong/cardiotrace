"""
How much does ignoring the 1999-2002 four-year weights actually cost?

NCHS releases WTMEC4YR alongside WTMEC2YR for 1999-2000 and 2001-2002, and its
analytic guidelines say a pooled analysis spanning those cycles should use them
rather than treating the two-year weights as if they were interchangeable. This
project pools eight cycles on WTMEC2YR throughout, so it does not follow that
guidance.

That is a known simplification, and the reason it is recorded as one rather than
quietly fixed or quietly ignored is that neither adjective was known until it was
measured. The four-year weights are not the average of the two-year weights --
they were post-stratified separately -- so the per-person disagreement is large
even where the aggregate one is not. Both halves of that sentence need a number
before anyone can say whether the simplification matters.

Writes reports/tables/fouryear_weight_check.csv so the claim in
docs/research-design.md has a source that regenerates.

    python scripts/check_fouryear_weights.py
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src.models import fit_aetiologic  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

OUT = ROOT / "reports" / "tables" / "fouryear_weight_check.csv"
DEMO = {"1999-2000": ROOT / "data" / "raw" / "1999-2000" / "DEMO.XPT",
        "2001-2002": ROOT / "data" / "raw" / "2001-2002" / "DEMO_B.XPT"}
COHORT = ROOT / "data" / "processed" / "cohort_part3.csv.gz"


def four_year_ratio() -> pd.DataFrame:
    """Per-person WTMEC4YR / (WTMEC2YR / 2) for the two cycles that have both.

    Dividing the two-year weight by two is what pooling on WTMEC2YR effectively
    does to a 1999-2002 participant's share of a four-year period, so this ratio
    is exactly the correction factor that was skipped.
    """
    frames = []
    for cycle, f in DEMO.items():
        if not f.exists():
            raise SystemExit(
                f"{f.relative_to(ROOT)} is missing. This check needs the raw "
                f"demographics files, which carry WTMEC4YR; the processed "
                f"cohort does not.")
        d = pd.read_sas(f)[["SEQN", "WTMEC2YR", "WTMEC4YR"]]
        d["cycle"] = cycle
        frames.append(d)
    w = pd.concat(frames, ignore_index=True)
    w = w[(w.WTMEC2YR > 0) & (w.WTMEC4YR > 0)].copy()
    w["ratio"] = w.WTMEC4YR / (w.WTMEC2YR / 2.0)
    return w


def main() -> None:
    w = four_year_ratio()
    df = pd.read_csv(COHORT)

    rows = [
        {"quantity": "participants with both weights", "value": len(w)},
        {"quantity": "sum WTMEC4YR", "value": round(float(w.WTMEC4YR.sum()))},
        {"quantity": "sum WTMEC2YR / 2", "value": round(float((w.WTMEC2YR / 2).sum()))},
        {"quantity": "aggregate gap (%)",
         "value": round(100 * (w.WTMEC4YR.sum() / (w.WTMEC2YR / 2).sum() - 1), 4)},
        {"quantity": "per-person ratio, median", "value": round(float(w.ratio.median()), 4)},
        {"quantity": "per-person ratio, 1st pctile", "value": round(float(w.ratio.quantile(.01)), 4)},
        {"quantity": "per-person ratio, 99th pctile", "value": round(float(w.ratio.quantile(.99)), 4)},
        {"quantity": "share of people off by >20% (%)",
         "value": round(100 * float((w.ratio.sub(1).abs() > 0.20).mean()), 2)},
    ]

    merged = df.merge(w[["SEQN", "ratio"]], on="SEQN", how="left")
    early = merged.ratio.notna()
    rows += [
        {"quantity": "cohort members from 1999-2002", "value": int(early.sum())},
        {"quantity": "their share of cohort weight (%)",
         "value": round(100 * float(merged.loc[early, "wtmec2yr"].sum()
                                    / merged.wtmec2yr.sum()), 2)},
    ]

    published = fit_aetiologic(df, "systolic_bp", tobin=True)
    corrected_frame = merged.copy()
    corrected_frame["wtmec2yr"] = corrected_frame.wtmec2yr * corrected_frame.ratio.fillna(1.0)
    corrected = fit_aetiologic(corrected_frame.drop(columns=["ratio"]),
                               "systolic_bp", tobin=True)

    hr = lambda t, per: float(np.exp(t.loc["systolic_bp", "log_hr"] * per))  # noqa: E731
    rows += [
        {"quantity": "HR per 10 mmHg, WTMEC2YR throughout (published)",
         "value": round(hr(published, 10), 4)},
        {"quantity": "HR per 10 mmHg, four-year weights applied",
         "value": round(hr(corrected, 10), 4)},
    ]

    terms = [t for t in published.index if t in corrected.index]
    shift = 100 * (np.exp(corrected.loc[terms, "log_hr"])
                   / np.exp(published.loc[terms, "log_hr"]) - 1)
    rows += [
        {"quantity": "largest hazard-ratio shift across all terms (%)",
         "value": round(float(shift.abs().max()), 4)},
        {"quantity": "term carrying that shift", "value": shift.abs().idxmax()},
    ]

    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    log.info(out.to_string(index=False))
    log.info(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
