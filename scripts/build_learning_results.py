"""Run the variable screen and the discrimination comparison, and persist both.

Order matters and is enforced: the screen runs on the TRAINING cycles and its
output decides the wide arm's feature set, so nothing here may look at the test
cycles before the screen has finished. Running the two in one script rather than
two is what keeps that guarantee local enough to read.

Writes:
  reports/tables/part4_marginal_ranking.csv   every candidate against the eleven
  reports/tables/part4_forward_path.csv       which variable entered, and when
  reports/tables/part4_arms.csv               the 2x2 plus the floor arm
  reports/tables/part4_importance.csv         permutation importance, two orderings
  reports/tables/part4_creatinine.csv         the calibration this depended on
  reports/part4_learning_results.json         everything the report interpolates
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.biomarkers import calibration_effect, derive  # noqa: E402
from src.discrimination import run  # noqa: E402
from src.models import P_FEATURES  # noqa: E402
from src.screening import STATUS, screen  # noqa: E402

# lifelines is loud about ties and step sizes on every one of the ~25 fits this
# script performs. ConvergenceWarning is deliberately NOT suppressed: a fold
# that failed to converge inside the bootstrap is the one thing here that must
# not pass in silence.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed" / "cohort_part3.csv.gz"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "reports" / "part4_learning_results.json"

# What PREVENT takes that the Pooled Cohort Equations do not, split the way
# PREVENT itself splits it. Getting this structure wrong once already produced a
# claim on the site that was flattering and false -- that the screen "recovered
# the three variables PREVENT added" -- when eGFR is not one of three optional
# additions but a mandatory base predictor the screen went on to reject.
#
# Base model, from the AHA scientific statement (Circulation 2024,
# https://www.ahajournals.org/doi/10.1161/CIR.0000000000001191): "The base model
# to predict risk of total CVD included the following predictors: SBP, HDL-C,
# non-HDL-C, eGFR, smoking status, use of antihypertensive or statin
# medications, and diabetes. eGFR was newly included as a predictor in the
# primary or base model." BMI enters through the heart-failure component of the
# total-CVD outcome. Both are new relative to PCE.
#
# The same statement specifies eGFR from CKD-EPI 2021 on serum creatinine --
# the equation `biomarkers.egfr_ckdepi_2021` implements, and the reason the
# calibration in that module had to be done first.
PREVENT_BASE_NEW = {"egfr": "eGFR", "bmi": "BMI"}

# The optional cardiovascular-kidney-metabolic extensions. Three of them, and
# eGFR is NOT among them.
PREVENT_OPTIONAL = {"log_uacr": "urine albumin/creatinine ratio",
                    "hba1c": "HbA1c",
                    "sdi": "social deprivation index"}

# SDI is a geographic index keyed to census tract. NHANES withholds geography
# for the same disclosure-control reason it masks the variance units, so this
# one cannot be built from the public files at all -- it is reported as
# unavailable rather than as untested.
PREVENT_UNAVAILABLE = {"sdi": "needs census-tract geography, which NHANES "
                              "withholds for disclosure control"}


def main() -> None:
    if not PROCESSED.exists():
        raise SystemExit(f"{PROCESSED} is missing; run scripts/build_cohort_results.py")
    TABLES.mkdir(parents=True, exist_ok=True)

    cohort = derive(pd.read_csv(PROCESSED))

    creat = calibration_effect(cohort)
    creat.to_csv(TABLES / "part4_creatinine.csv", index=False)

    scr = screen(cohort)
    scr["ranking"].to_csv(TABLES / "part4_marginal_ranking.csv", index=False)
    scr["path"].to_csv(TABLES / "part4_forward_path.csv", index=False)

    res = run(cohort, scr["selected"])

    arms = pd.DataFrame([
        {"arm": name, "n_features": s["n_features"], "harrell_c": round(s["c"], 4),
         "auc_horizon": round(s["auc_horizon"], 4),
         "delta_c": res["deltas"].get(name, {}).get("delta"),
         "delta_lo": res["deltas"].get(name, {}).get("lo"),
         "delta_hi": res["deltas"].get(name, {}).get("hi"),
         "excludes_zero": res["deltas"].get(name, {}).get("excludes_zero"),
         "is_reference": name == res["reference"]}
        for name, s in res["scores"].items()])
    arms.to_csv(TABLES / "part4_arms.csv", index=False)

    # The two orderings, on one table. `e2_status` is looked up, never defaulted:
    # a variable with no declared status raises in `screening.assert_declared`
    # rather than printing "allowed" under a column headed "in the causal model?".
    imp = res["importance"].copy()
    imp["e2_status"] = imp["variable"].map(lambda v: STATUS[v][0])
    imp["e2_why"] = imp["variable"].map(lambda v: STATUS[v][1])
    imp.to_csv(TABLES / "part4_importance.csv", index=False)

    top5 = imp.head(5)
    not_admissible = top5[top5["e2_status"] != "admissible"]

    # What the screen selected, against what PREVENT takes. Reported as
    # intersections and differences rather than as a verdict: the actual result
    # is that the screen kept an OPTIONAL extension and rejected a MANDATORY
    # base predictor, and rounding that either way would be a claim the data
    # does not make.
    selected = set(scr["selected"])
    considered = {r.variable for r in scr["ranking"].itertuples()}
    # BMI is already among the eleven, so it was never a candidate: PREVENT's
    # other base addition is one this model already had.
    incumbent = set(P_FEATURES)
    base_here = {v for v in PREVENT_BASE_NEW if v in considered}
    base_incumbent = {v for v in PREVENT_BASE_NEW if v in incumbent}
    opt_here = {v for v in PREVENT_OPTIONAL if v in considered}

    results = {
        "screen": {
            "n_train": scr["n_train"], "events_train": scr["events_train"],
            "wald_threshold": scr["wald_threshold"],
            "min_coverage": scr["min_coverage"],
            "n_candidates": int(len(scr["ranking"])),
            "pool": scr["pool"], "selected": scr["selected"],
            "top_marginal": scr["ranking"].iloc[0]["variable"],
            "top_marginal_z": float(scr["ranking"].iloc[0]["z"]),
            "top_marginal_hr_per_sd": float(scr["ranking"].iloc[0]["hr_per_sd"]),
        },
        "prevent": {
            "base_new": PREVENT_BASE_NEW,
            "optional": PREVENT_OPTIONAL,
            "unavailable": PREVENT_UNAVAILABLE,
            "base_already_in_model": sorted(base_incumbent),
            "base_screened": sorted(base_here),
            "base_selected": sorted(selected & base_here),
            "base_rejected": sorted(base_here - selected),
            "optional_screened": sorted(opt_here),
            "optional_selected": sorted(selected & opt_here),
            "optional_rejected": sorted(opt_here - selected),
        },
        "arms": {
            "reference": res["reference"],
            "wide": res["wide"], "horizon": res["horizon"],
            "n_train": res["n_train"], "n_test": res["n_test"],
            "events_test": res["events_test"], "n_boot": res["n_boot"],
            "scores": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                           for kk, vv in v.items()}
                       for k, v in res["scores"].items()},
            "deltas": res["deltas"],
        },
        "importance": {
            "top5": top5["variable"].tolist(),
            "top5_not_admissible": not_admissible["variable"].tolist(),
            "n_top5_not_admissible": int(len(not_admissible)),
            # The interval on any null this section reports. The floor arm is
            # excluded: its difference is not a null by construction, so
            # including it would overstate what the comparison could detect.
            "largest_null_half_width": round(max(
                d["half_width"] for name, d in res["deltas"].items()
                if name != "floor_age_sex" and not d["excludes_zero"]), 4)
            if any(name != "floor_age_sex" and not d["excludes_zero"]
                   for name, d in res["deltas"].items()) else None,
        },
        "creatinine": {
            "corrected_cycles": creat.loc[creat["corrected"], "cycle"].tolist(),
            "table": creat.to_dict("records"),
        },
    }
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    print(f"  screen      {scr['n_train']:,} train rows, {scr['events_train']} events, "
          f"{len(scr['ranking'])} candidates")
    print(f"              pool {scr['pool']} -> selected {scr['selected'] or '(none)'}")
    print(f"  PREVENT     base new: screened {sorted(base_here)}, "
          f"selected {sorted(selected & base_here) or '(none)'}, "
          f"already in the model {sorted(base_incumbent) or '(none)'}")
    print(f"              optional: screened {sorted(opt_here)}, "
          f"selected {sorted(selected & opt_here) or '(none)'}, "
          f"unavailable {sorted(PREVENT_UNAVAILABLE)}")
    for name, s in res["scores"].items():
        d = res["deltas"].get(name)
        tail = (f"{d['delta']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}]"
                if d else "(reference)")
        print(f"  {name:15s} C {s['c']:.4f}  AUC {s['auc_horizon']:.4f}  {tail}")
    print(f"  top five predictors: {top5['variable'].tolist()}")
    print(f"  of those, {len(not_admissible)} the causal model may not adjust for: "
          f"{not_admissible['variable'].tolist() or '(none)'}")


if __name__ == "__main__":
    main()
