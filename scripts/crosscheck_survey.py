"""Cross-validate the hand-written survey estimators against R's `survey` package.

WHAT THIS IS EVIDENCE FOR, AND WHAT IT IS NOT
---------------------------------------------
Every variance estimator in this project is hand-written: the Taylor
linearisation in `src.descriptive` and the cluster-robust Cox in `src.models`.
Both are covered by unit tests, and unit tests written by the author of an
estimator can only check that it does what the author believed it should do.
They cannot catch a shared misreading of the formula, because the test encodes
the same misreading. The only thing that can is an implementation written by
someone else from the same published definitions.

So this script does not test the estimators. It compares them, term by term,
against `survey` -- Lumley's package, which is the reference implementation the
NCHS analytic guidelines and the Stata/SAS survey procedures are checked
against. Agreement to several decimal places is the claim the unit tests cannot
make. Disagreement is a finding, and this script is written to make a
disagreement loud rather than to make the two sides meet: nothing here tunes
the R side toward the Python answer.

WHAT WOULD SILENTLY GO WRONG WITHOUT IT
---------------------------------------
A design-based standard error has no smell. If `_linearised_variance` dropped
the between-age-group covariance, or used n_h rather than n_h/(n_h-1), or
centred PSU totals on the grand mean instead of the stratum mean, the numbers
would still be positive, still be the right order of magnitude, still move in
the right direction across cycles, and still pass a test asserting they are
positive and the right order of magnitude. Every published confidence interval
in Part 1 would be wrong by a factor nobody could see. The same holds for the
Cox robust variance, with one extra trap: lifelines and `survey` compute
DIFFERENT estimators under the same name, and the difference is not a bug in
either. See PART 3 below.

THE EXCHANGE
------------
Python writes the analytic frames it actually fits -- not a re-derivation, the
same rows the shipped code path produces -- into `data/processed/crosscheck/`,
shells out to Rscript, and reads back one CSV per part. The frames are exported
rather than rebuilt in R because rebuilding them in R would put a second cohort
definition in the repository, and then a disagreement could mean either "the
variance formula differs" or "the two sides are looking at different people",
which is the one thing this script must never leave ambiguous.

PART 1: age-standardised prevalence
-----------------------------------
The comparator is `svyby(..., covmat=TRUE)` + `svycontrast`: the same estimand
written the same way, as domain means per age band, their full covariance
matrix, and a fixed linear combination over it. `svystandardize` is run as well
and reported alongside, because it is the route most analysts would take and it
does NOT linearise the same quantity -- it rescales the weights and then takes
an ordinary mean, which treats the within-band weight totals as fixed. Where
the two R routes disagree with each other, that gap is the scale on which
"which R answer are you comparing against" matters, and it belongs in the
output rather than in a footnote.

Both lonely-PSU settings are run. `_linearised_variance` documents a collapse
rule for singleton strata; `survey.lonely.psu="adjust"` centres a lone PSU on
the grand mean, which is the same remedy. The overall by-cycle series has no
singleton strata at all, so if the two settings ever differ for Part 1 then the
export is not the sample that docstring describes and the run is invalid.

PART 3: cause-specific Cox
--------------------------
The coefficients should agree to near machine precision: both sides maximise
the same weighted Efron partial likelihood. If they do not, the disagreement is
in the model frame or in tie handling, not in the variance.

The standard errors are the interesting half, and a difference there is
EXPECTED rather than alarming. lifelines' `cluster_col` sandwich sums squared
cluster-level score residuals with no reference to strata:

    V = sum over clusters c of  u_c u_c'

`survey`'s design-based variance is the stratified ultimate-cluster estimator:

    V = sum over strata h of  n_h/(n_h-1) *
        sum over PSUs i in h of (u_hi - u_h.)(u_hi - u_h.)'

These estimate different things. The first ignores stratification, discarding
the stratification gain; the second removes between-stratum variation and pays
an n_h/(n_h-1) = 2 inflation for it at two PSUs per stratum. Neither is a bug.
But only the second is the design-based variance the NHANES analytic guidelines
ask for, and this project reports its intervals as design-based.

To separate "different estimator" from "different implementation", the R side
also fits plain `coxph` with `cluster()`, which is the SAME estimator lifelines
computes. Python-vs-coxph measures the implementation; coxph-vs-svycoxph
measures the estimator choice. Without that third fit a single number would be
carrying both explanations at once.

    python scripts/crosscheck_survey.py
    python scripts/crosscheck_survey.py --part 1     # one part only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import models  # noqa: E402
from src.descriptive import STD_2000, build_descriptive, by_cycle  # noqa: E402

EXCHANGE = ROOT / "data" / "processed" / "crosscheck"
TABLES = ROOT / "reports" / "tables"
R_SCRIPT = ROOT / "scripts" / "crosscheck_survey.R"
COHORT = ROOT / "data" / "processed" / "cohort_part3.csv.gz"

# R is deliberately NOT assumed to be on PATH -- it is not, on this machine. A
# bare "Rscript" would fail with a message about a missing executable rather
# than about a missing cross-check, which is the kind of failure that gets
# shrugged off and turns into "we ran the crosscheck once, back in August".
RSCRIPT_DEFAULT = r"C:\Program Files\R\R-4.5.2\bin\Rscript.exe"


def rscript_path() -> str:
    """Absolute path to Rscript, overridable for another machine."""
    env = os.environ.get("RSCRIPT")
    if env:
        return env
    if Path(RSCRIPT_DEFAULT).exists():
        return RSCRIPT_DEFAULT
    found = shutil.which("Rscript")
    if found:
        return found
    raise FileNotFoundError(
        f"Rscript not found at {RSCRIPT_DEFAULT}, not on PATH, and $RSCRIPT is "
        "unset. Nothing here can be verified without it -- set RSCRIPT.")


# ---------------------------------------------------------------- part 1 -----

def export_part1() -> pd.DataFrame:
    """Write the Part 1 analytic frame and the Python estimates beside it.

    The standard population is exported too, taken from `STD_2000` itself rather
    than retyped into the R file. Transcribing eleven decimal constants into a
    second language is a silent-drift generator: both sides would still run,
    both would still produce plausible prevalences, and the disagreement would
    be read as a variance problem.
    """
    # `weight` is whichever analysis weight build_descriptive selected; the
    # estimators read that column by name, so exporting the column instead of a
    # hard-coded WTINT2YR/WTMEC2YR keeps the crosscheck pointed at whatever the
    # shipped default currently is rather than at what it was when this was
    # written.
    df = build_descriptive()
    cols = ["cycle", "strata", "psu", "weight", "age_group", "prev_cvd"]
    out = df[cols].copy()
    out["age_group"] = out["age_group"].astype(str)
    out.to_csv(EXCHANGE / "part1_input.csv", index=False)

    std = pd.DataFrame({"age_group": list(STD_2000),
                        "std_weight": list(STD_2000.values())})
    std.to_csv(EXCHANGE / "part1_stdpop.csv", index=False)

    py = by_cycle(df)[["cycle", "n", "n_psu", "p_std", "se_std",
                       "p_crude", "se_crude"]].copy()
    py.to_csv(EXCHANGE / "part1_python.csv", index=False)
    return py


def compare_part1(py: pd.DataFrame) -> pd.DataFrame:
    r = pd.read_csv(EXCHANGE / "part1_r.csv")
    # "adjust" is the setting matching the documented collapse rule. The other
    # setting is carried into the table as evidence that it changed nothing,
    # not as an alternative answer to choose between.
    adj = r[r.lonely_psu == "adjust"].drop(columns=["lonely_psu"])
    adj = adj.rename(columns={c: f"r_{c}" for c in adj.columns if c != "cycle"})
    ave = r[r.lonely_psu == "average"][["cycle", "p_std", "se_std"]]
    ave.columns = ["cycle", "r_p_std_average", "r_se_std_average"]

    m = py.merge(adj, on="cycle", how="outer").merge(ave, on="cycle", how="left")
    for col in ("p_std", "se_std", "p_crude", "se_crude"):
        rcol = f"r_{col}"
        m[f"absdiff_{col}"] = (m[col] - m[rcol]).abs()
        m[f"reldiff_{col}"] = np.where(
            m[rcol] != 0, (m[col] - m[rcol]).abs() / m[rcol].abs(), np.nan)
    return m


# ---------------------------------------------------------------- part 3 -----

def export_part3() -> pd.DataFrame:
    """Write the Part 3 model frame and the lifelines fit beside it.

    The frame is rebuilt here the way `models._fit` builds it and then checked
    against the fitted object's own row count. That assertion carries the whole
    safety of the comparison: if `_fit` ever changes which rows it drops, this
    script would hand R one sample, fit Python on another, and report the
    difference as a variance discrepancy.
    """
    df = pd.read_csv(COHORT)
    d = models.prepare(df, tobin=True)

    # Mirrors fit_aetiologic's covariate assembly rather than restating it, so
    # a change to E2_ADJUSTMENT reaches the crosscheck without a second edit.
    exposure = "systolic_bp"
    covs = [exposure] + [c for c in models.E2_ADJUSTMENT if c != exposure]
    model_cols = covs + ["followup_years", "cvd_death", "wtmec2yr",
                         "design_cluster"]
    fit_df = d[model_cols].dropna()

    cph = models._fit(d, covs, "cvd_death")
    n_fitted = int(cph.weights.shape[0])
    if n_fitted != len(fit_df):
        raise AssertionError(
            f"_fit used {n_fitted} rows, this script exported {len(fit_df)}. "
            "The export mirrors _fit's own dropna and has drifted from it; fix "
            "the mirror before believing any number below.")

    export = d.loc[fit_df.index, model_cols + ["strata", "psu", "cycle"]]
    export.to_csv(EXCHANGE / "part3_input.csv", index=False)
    (EXCHANGE / "part3_covariates.txt").write_text(
        "\n".join(covs) + "\n", encoding="utf-8")

    s = cph.summary
    py = pd.DataFrame({
        "term": s.index,
        "coef": s["coef"].to_numpy(),
        "se": s["se(coef)"].to_numpy(),
        "lo95": s["coef lower 95%"].to_numpy(),
        "hi95": s["coef upper 95%"].to_numpy(),
    })
    py["n"] = n_fitted
    py.to_csv(EXCHANGE / "part3_python.csv", index=False)
    return py


def compare_part3(py: pd.DataFrame) -> pd.DataFrame:
    r = pd.read_csv(EXCHANGE / "part3_r.csv")
    # `crit` comes along so the table records which multiplier each side used.
    # Comparing two intervals that were built with different quantiles and
    # calling the gap a variance difference is the error this column prevents.
    wide = r.pivot(index="term", columns="fit",
                   values=["coef", "se", "lo95", "hi95", "crit"])
    wide.columns = [f"{fit}_{stat}" for stat, fit in wide.columns]
    m = py.set_index("term").join(wide, how="outer").reset_index()

    for fit in ("svycoxph", "coxph_cluster"):
        m[f"absdiff_coef_{fit}"] = (m["coef"] - m[f"{fit}_coef"]).abs()
        m[f"absdiff_se_{fit}"] = (m["se"] - m[f"{fit}_se"]).abs()
        m[f"reldiff_se_{fit}"] = (m["se"] - m[f"{fit}_se"]).abs() / m[f"{fit}_se"]
    m["reldiff_coef_svycoxph"] = np.where(
        m["svycoxph_coef"] != 0,
        (m["coef"] - m["svycoxph_coef"]).abs() / m["svycoxph_coef"].abs(),
        np.nan)
    # The interval is what the report prints, so it is compared as an interval
    # and not left to be inferred from the standard error.
    m["absdiff_lo95_svycoxph"] = (m["lo95"] - m["svycoxph_lo95"]).abs()
    m["absdiff_hi95_svycoxph"] = (m["hi95"] - m["svycoxph_hi95"]).abs()
    return m


# ------------------------------------------------------------------ run ------

def run_r(part: str) -> None:
    exe = rscript_path()
    cmd = [exe, str(R_SCRIPT), str(EXCHANGE), part]
    print(f"  -> {Path(exe).name} {R_SCRIPT.name} {part}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print("\n".join("     R| " + ln
                        for ln in proc.stdout.strip().splitlines()))
    if proc.returncode != 0:
        print("\n".join("     R! " + ln
                        for ln in proc.stderr.strip().splitlines()))
        raise RuntimeError(f"Rscript exited {proc.returncode}")
    if proc.stderr.strip():
        # survey emits real warnings here -- lonely PSUs, non-integer weights.
        # They are part of the finding, so they are printed rather than eaten.
        print("\n".join("     R? " + ln
                        for ln in proc.stderr.strip().splitlines()))


def print_part1(m: pd.DataFrame) -> None:
    print("\nPART 1  age-standardised CVD prevalence, per cycle")
    print("  python = src.descriptive.by_cycle | "
          "R = svyby + svycontrast, lonely.psu='adjust'")
    print(f"  {'cycle':<10} {'py p_std':>10} {'R p_std':>10} {'absdiff':>10} "
          f"{'py se':>10} {'R se':>10} {'absdiff':>10} {'rel':>9} {'df':>4}")
    for r in m.itertuples(index=False):
        print(f"  {r.cycle:<10} {r.p_std:>10.6f} {r.r_p_std:>10.6f} "
              f"{r.absdiff_p_std:>10.2e} {r.se_std:>10.6f} {r.r_se_std:>10.6f} "
              f"{r.absdiff_se_std:>10.2e} {r.reldiff_se_std:>9.2e} "
              f"{int(r.r_design_df):>4}")
    print(f"  max |diff|: point {m.absdiff_p_std.max():.3e} | "
          f"se {m.absdiff_se_std.max():.3e} | "
          f"relative se {m.reldiff_se_std.max():.3e}")
    print(f"  crude prevalence max |diff|: point {m.absdiff_p_crude.max():.3e} "
          f"| se {m.absdiff_se_crude.max():.3e}")
    same = np.allclose(m.r_se_std, m.r_se_std_average, rtol=0, atol=1e-12)
    print(f"  lonely.psu adjust == average: {same}   "
          "(expected True: the overall series has no singleton strata)")
    d = (m.r_se_std_svystd - m.r_se_std).abs().max()
    print(f"  svystandardize vs svycontrast, max |se diff|: {d:.3e}")


def print_part3(m: pd.DataFrame) -> None:
    print("\nPART 3  cause-specific Cox for CVD death, "
          "systolic BP + E2 adjustment")
    print("  python = lifelines cluster sandwich | svycoxph = stratified "
          "ultimate cluster | coxph_cluster = lifelines' own estimator, in R")
    print(f"  {'term':<14} {'py coef':>10} {'svy coef':>10} {'absdiff':>9} "
          f"{'py se':>9} {'svy se':>9} {'rel':>8} {'coxph se':>9} {'rel':>8}")
    for r in m.itertuples(index=False):
        print(f"  {r.term:<14} {r.coef:>10.6f} {r.svycoxph_coef:>10.6f} "
              f"{r.absdiff_coef_svycoxph:>9.2e} {r.se:>9.6f} "
              f"{r.svycoxph_se:>9.6f} {r.reldiff_se_svycoxph:>8.1%} "
              f"{r.coxph_cluster_se:>9.6f} {r.reldiff_se_coxph_cluster:>8.1%}")
    print(f"  max |coef diff| vs svycoxph: {m.absdiff_coef_svycoxph.max():.3e}")
    print(f"  se vs svycoxph      : median rel "
          f"{m.reldiff_se_svycoxph.median():.2%}  "
          f"max {m.reldiff_se_svycoxph.max():.2%}")
    print(f"  se vs coxph+cluster : median rel "
          f"{m.reldiff_se_coxph_cluster.median():.2%}  "
          f"max {m.reldiff_se_coxph_cluster.max():.2%}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=["1", "3", "both"], default="both")
    args = ap.parse_args()

    EXCHANGE.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    if args.part in ("1", "both"):
        print("PART 1: exporting analytic frame and Python estimates")
        py1 = export_part1()
        run_r("part1")
        m1 = compare_part1(py1)
        m1.to_csv(TABLES / "crosscheck_part1.csv", index=False)
        print_part1(m1)
        print(f"  written: {TABLES / 'crosscheck_part1.csv'}")

    if args.part in ("3", "both"):
        print("\nPART 3: exporting model frame and lifelines fit")
        py3 = export_part3()
        run_r("part3")
        m3 = compare_part3(py3)
        m3.to_csv(TABLES / "crosscheck_part3.csv", index=False)
        print_part3(m3)
        print(f"  written: {TABLES / 'crosscheck_part3.csv'}")


if __name__ == "__main__":
    main()
