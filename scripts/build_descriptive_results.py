"""Produce the Part 1 and Part 2 result tables from the corrected data.

Part 1 is the age-standardised prevalence series, overall and by race/ethnicity.
Part 2 fits the pre-pandemic trend and extrapolates a counterfactual for
2021-2022, which is the only fielded cycle after the pandemic.

WHAT THE COUNTERFACTUAL CAN AND CANNOT SAY
------------------------------------------
A segmented regression normally estimates a level change AND a slope change.
Here there is exactly one post-pandemic point, so the slope change is not
identified and is not reported. What is reported is the gap between the
observed 2021-2022 value and the value the pre-pandemic trend predicts for it.

The series also has a hole: NHANES suspended field operations, so there is no
2019-2020 cycle and the extrapolation reaches 5.1 years past the last observed
point instead of the usual 2. The prediction interval widens accordingly, but
the gap is still an extrapolation and is labelled as one.

Residual dispersion is estimated from the pre-pandemic fit AND FLOORED AT 1.
The reasoning for estimating it is that design-based standard errors describe
sampling error only, and real cycle-to-cycle movement in a national prevalence
could be larger; pretending otherwise would give a counterfactual interval too
narrow and a "significant" COVID effect that is an artefact of the model.

On this series the estimate comes out at 0.86 -- the series moves LESS than
sampling error alone explains -- so the floor binds and the published interval
is the design-based one. Both are in the artefact (`gap_ci` against
`gap_ci_unfloored`) because which one is on the page is not something a reader
should have to infer.
"""

from __future__ import annotations

import json
from pathlib import Path

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.descriptive import (  # noqa: E402
    CONDITION_LABELS, build_descriptive, by_cycle, PRE_COVID_CYCLES, cycle_midpoint,
    AGE_LABELS, AGE_MIN_DESC, STD_2000, WEIGHT_EXAM, WEIGHT_INTERVIEW,
)
from src.changepoint import bootstrap_test, power_curve, profile_set  # noqa: E402

ROOT = Path(__file__).parent.parent
TABLES = ROOT / "reports" / "tables"
REPORTS = ROOT / "reports"

# Race groups present in every cycle. Non-Hispanic Asian is reported separately
# only from 2011 (RIDRETH3), so a series drawn across all cycles would show a
# break that is an instrument change, not a health change.
RACE_ALL_CYCLES = ["Non-Hispanic White", "Non-Hispanic Black",
                   "Mexican American", "Other Hispanic"]


def wls_trend(x: np.ndarray, y: np.ndarray, se: np.ndarray) -> dict:
    """Weighted least squares with a dispersion estimated from the residuals."""
    w = 1.0 / se ** 2
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(w)
    XtWX_inv = np.linalg.inv(X.T @ W @ X)
    beta = XtWX_inv @ (X.T @ W @ y)
    resid = y - X @ beta
    dof = len(x) - 2
    # Dispersion > 1 means the series moves more than sampling error explains.
    phi = float((w * resid ** 2).sum() / dof)
    # Floored at 1: never let an estimated dispersion below one NARROW the
    # interval past the design-based one. Ten points cannot establish that a
    # national series is more stable than its own sampling error, and a phi of
    # 0.86 -- which is what this series gives -- would shrink the band on the
    # strength of that claim. The floor binds here; `gap_ci_unfloored` records
    # what it would have been.
    cov = XtWX_inv * max(phi, 1.0)
    return {"beta": beta, "cov": cov, "cov_unfloored": XtWX_inv * phi,
            "phi": phi, "dof": dof,
            "slope": float(beta[1]), "slope_se": float(np.sqrt(cov[1, 1]))}


def predict_at(fit: dict, x0: float) -> tuple[float, float]:
    """Fitted value at x0 and the standard error of that fitted value."""
    x0v = np.array([1.0, x0])
    yhat = float(x0v @ fit["beta"])
    se = float(np.sqrt(x0v @ fit["cov"] @ x0v))
    return yhat, se


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    ladder = []
    df = build_descriptive(ladder=ladder)
    flow = pd.DataFrame(ladder)
    flow.to_csv(TABLES / "part1_flow.csv", index=False)

    # The same ladder under the examination weight. It is not an alternative
    # analysis -- it is the evidence for why the analysis weight changed. Under
    # the exam weight the post-pandemic cycle loses 22% of its age-eligible
    # respondents and every other cycle loses 3-9%, and that gap was reported
    # for a while as a competing explanation for the pandemic effect. It was an
    # artefact of asking a self-reported outcome to carry an examination weight.
    exam_ladder = []
    build_descriptive(ladder=exam_ladder, weight=WEIGHT_EXAM)
    exam_flow = pd.DataFrame(exam_ladder)
    exam_flow.to_csv(TABLES / "part1_flow_examweight.csv", index=False)

    # ── Part 1: overall series ────────────────────────────────────────────
    overall = by_cycle(df)
    overall.to_csv(TABLES / "part1_prevalence_by_cycle.csv", index=False)

    # Age-group detail, to show what standardisation is correcting for.
    age_rows = []
    for (cycle, year, ag), g in df.groupby(["cycle", "year", "age_group"], observed=True):
        w, y = g["weight"].to_numpy(), g["prev_cvd"].to_numpy()
        age_rows.append({"cycle": cycle, "year": year, "age_group": str(ag),
                         "n": len(g), "p": float((w * y).sum() / w.sum())})
    age_detail = pd.DataFrame(age_rows).sort_values(["year", "age_group"])
    age_detail.to_csv(TABLES / "part1_prevalence_by_age.csv", index=False)

    # The sample itself aged, which is the whole reason standardisation matters.
    comp_rows = []
    for (cycle, year), g in df.groupby(["cycle", "year"], observed=True):
        w = g["weight"]
        row = {"cycle": cycle, "year": year,
               "mean_age_weighted": float((w * g["age"]).sum() / w.sum())}
        for lab in AGE_LABELS:
            m = g["age_group"] == lab
            row[lab] = float(w[m].sum() / w.sum())
        comp_rows.append(row)
    comp = pd.DataFrame(comp_rows).sort_values("year")
    comp.to_csv(TABLES / "part1_age_composition.csv", index=False)

    # ── Part 1: each condition on its own ─────────────────────────────────
    # These exist because the Tableau extract was still reading
    # reports/tables/prevalence_has_*.csv, whose only writer is
    # legacy-invalid/run_pipeline.py. Two wrong things reached the published
    # extract as a result: those rows carried the deprecated pipeline's crude
    # pooled-weight prevalence beside this one's (8.0967% against 8.0208% for
    # the same outcome and cycle, in the same column), and they dated the
    # redesigned cycle 2021.5 where every other block dates it 2022.6 -- so a
    # time series plotted 66 rows 1.1 years to the left of everything else.
    #
    # Same estimator as the headline series, so they are comparable with it:
    # age-standardised, interview-weighted, design-based interval.
    for outcome, label in CONDITION_LABELS.items():
        cond = by_cycle(df[df[outcome].notna()], outcome=outcome)
        cond.insert(0, "outcome", label)
        cond.to_csv(TABLES / f"part1_prevalence_{outcome}.csv", index=False)
    print(f"condition series -> {len(CONDITION_LABELS)} tables in "
          f"{TABLES.relative_to(ROOT)}")

    # ── Part 1: by race/ethnicity ─────────────────────────────────────────
    race = by_cycle(df[df["race_eth"].isin(RACE_ALL_CYCLES)], group="race_eth")
    race.to_csv(TABLES / "part1_prevalence_by_race.csv", index=False)

    # ── Part 1: trend test on the pre-pandemic series ─────────────────────
    pre = overall[overall["cycle"].isin(PRE_COVID_CYCLES)]
    fit = wls_trend(pre["year"].to_numpy(), pre["p_std"].to_numpy(),
                    pre["se_std"].to_numpy())
    slope_per_decade = fit["slope"] * 10
    # Two critical values, because with ten points and a dispersion estimated
    # from the same ten the normal quantile is not the honest one. The residual
    # degrees of freedom are n_cycles - 2 = 8, and t(8) = 2.306 against 1.960 --
    # an 18% wider interval, which is enough to move this particular slope
    # across zero. Both are reported; the conclusion is stated against the wider
    # one, because claiming the narrower is claiming a precision ten points do
    # not carry.
    slope_ci = (1.96 * fit["slope_se"] * 10)
    t_crit = float(stats.t.ppf(0.975, fit["dof"]))
    slope_ci_t = (t_crit * fit["slope_se"] * 10)

    crude_fit = wls_trend(pre["year"].to_numpy(), pre["p_crude"].to_numpy(),
                          pre["se_crude"].to_numpy())

    # ── Part 2: counterfactual for 2021-2022 ──────────────────────────────
    # The change-point test runs on the FULL series: its question is whether a
    # break sits anywhere, not whether one sits at the pandemic.
    x_pre_all = overall["year"].to_numpy()
    y_pre_all = overall["p_std"].to_numpy()
    se_pre_all = overall["se_std"].to_numpy()

    post = overall[overall["cycle"] == "2021-2022"].iloc[0]
    x0 = cycle_midpoint("2021-2022")
    yhat, se_fit = predict_at(fit, x0)
    _x0v = np.array([1.0, x0])
    x0v_unfloored = float(_x0v @ fit["cov_unfloored"] @ _x0v)
    obs, se_obs = float(post["p_std"]), float(post["se_std"])
    gap = obs - yhat
    se_gap = float(np.sqrt(se_fit ** 2 + se_obs ** 2))
    z = gap / se_gap
    # The report contrasts the floored interval against the un-floored one to
    # show the null does not depend on that choice. Both must come from here;
    # the un-floored pair was previously typed into the prose by hand.
    se_fit_raw = float(np.sqrt(x0v_unfloored))
    se_gap_raw = float(np.sqrt(se_fit_raw ** 2 + se_obs ** 2))
    # Same argument as the slope: the fitted half of this standard error comes
    # from ten points and a dispersion estimated from them, so the interval is
    # built on t(dof) and the normal one is kept for comparison.
    gap_ci_t = t_crit * se_gap
    gap_ci_normal = 1.96 * se_gap

    results = {
        "part1": {
            "n_adults": int(len(df)),
            "n_cycles": int(df["cycle"].nunique()),
            "age_floor": AGE_MIN_DESC,
            "weight": WEIGHT_INTERVIEW,
            "weight_sensitivity": WEIGHT_EXAM,
            "max_loss_pct": float(flow["lost_pct"].max()),
            "max_loss_cycle": str(flow.loc[flow["lost_pct"].idxmax(), "cycle"]),
            "exam_weight_loss_post_pct": float(
                exam_flow.loc[exam_flow["cycle"] == "2021-2022", "lost_pct"].iloc[0]),
            "exam_weight_loss_other_min_pct": float(
                exam_flow.loc[exam_flow["cycle"] != "2021-2022", "lost_pct"].min()),
            "exam_weight_loss_other_max_pct": float(
                exam_flow.loc[exam_flow["cycle"] != "2021-2022", "lost_pct"].max()),
            "n_adults_exam_weight": int(exam_flow["analysed"].sum()),
            "crude_first": float(overall.iloc[0]["p_crude"]),
            "crude_last_pre": float(pre.iloc[-1]["p_crude"]),
            "std_first": float(overall.iloc[0]["p_std"]),
            "std_last_pre": float(pre.iloc[-1]["p_std"]),
            # The full series as well as the pre-pandemic one, because the report
            # needs both and had no way to say so: the standardisation figure
            # plots all eleven cycles and computes its heading off the last of
            # them, while the statistic strip beside it read `*_last_pre` and so
            # described 1999-2018. Two windows, adjacent on the page, neither
            # labelled. The trend estimate stays pre-pandemic -- it is a
            # pre-pandemic trend by construction, and section 3 exists to ask
            # what the last cycle did relative to it.
            "crude_last": float(overall.iloc[-1]["p_crude"]),
            "std_last": float(overall.iloc[-1]["p_std"]),
            "last_cycle": str(overall.iloc[-1]["cycle"]),
            "pre_last_cycle": str(pre.iloc[-1]["cycle"]),
            "mean_age_first": float(comp.iloc[0]["mean_age_weighted"]),
            "mean_age_last": float(comp.iloc[-1]["mean_age_weighted"]),
            "std_slope_per_decade": float(slope_per_decade),
            "std_slope_ci": [float(slope_per_decade - slope_ci_t),
                             float(slope_per_decade + slope_ci_t)],
            "std_slope_ci_normal": [float(slope_per_decade - slope_ci),
                                    float(slope_per_decade + slope_ci)],
            "slope_dof": int(fit["dof"]),
            "slope_t_crit": t_crit,
            "std_slope_excludes_zero": bool(
                (slope_per_decade - slope_ci_t) * (slope_per_decade + slope_ci_t) > 0),
            "std_slope_excludes_zero_normal": bool(
                (slope_per_decade - slope_ci) * (slope_per_decade + slope_ci) > 0),
            "crude_slope_per_decade": float(crude_fit["slope"] * 10),
            "dispersion": float(fit["phi"]),
        },
        "part2": {
            "post_cycle": "2021-2022",
            "observed": obs,
            "observed_se": se_obs,
            "counterfactual": float(yhat),
            "counterfactual_se": float(se_fit),
            "gap": float(gap),
            "gap_se": se_gap,
            "gap_ci": [float(gap - gap_ci_t), float(gap + gap_ci_t)],
            "gap_ci_normal": [float(gap - gap_ci_normal),
                              float(gap + gap_ci_normal)],
            "gap_ci_unfloored": [float(gap - t_crit * se_gap_raw),
                                 float(gap + t_crit * se_gap_raw)],
            "gap_dof": int(fit["dof"]),
            "gap_t_crit": t_crit,
            "extrapolation_from_cycle": str(pre.iloc[-1]["cycle"]),
            "z": float(z),
            "extrapolation_years": float(x0 - cycle_midpoint(PRE_COVID_CYCLES[-1])),
            "n_post_cycles": 1,
            "slope_change_identified": False,
        },
    }

    # ── Part 2: change-point test and power, persisted once ───────────
    # These were produced ad hoc once and read by both the figure and the
    # report, which is how three different bootstrap critical values ended up in
    # circulation. Running the test here makes the artefact reproducible and
    # gives both consumers one number to read.
    boot = bootstrap_test(x_pre_all, y_pre_all, se_pre_all, n_boot=4000)
    pset = profile_set(boot)
    power_tau = 2011.5
    curve = power_curve(x_pre_all, se_pre_all, tau=power_tau,
                        slope_changes=[0.0002, 0.0004, 0.0006, 0.0010, 0.0015, 0.0025],
                        n_sim=400, n_boot=800)
    (TABLES / "part2_changepoint.json").write_text(json.dumps({
        **boot,
        "profile_set": pset,
        "profile_set_spans_grid": len(pset) == len(boot["grid"]),
        "power_tau": power_tau,
        "power_n_sim": 400,
        "power_n_boot": 800,
        "power": curve,
    }, indent=2), encoding="utf-8")

    (REPORTS / "descriptive_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    print(f"Part 1: {len(df):,} adults, {df['cycle'].nunique()} cycles")
    print(f"  crude      {results['part1']['crude_first']:.4f} -> "
          f"{results['part1']['crude_last_pre']:.4f}")
    print(f"  standardised {results['part1']['std_first']:.4f} -> "
          f"{results['part1']['std_last_pre']:.4f}")
    print(f"  mean age   {results['part1']['mean_age_first']:.1f} -> "
          f"{results['part1']['mean_age_last']:.1f}")
    print(f"  std slope/decade {slope_per_decade:+.4f} "
          f"[{slope_per_decade - slope_ci:+.4f}, {slope_per_decade + slope_ci:+.4f}]"
          f"  dispersion {fit['phi']:.2f}")
    print(f"Part 2: observed {obs:.4f} vs counterfactual {yhat:.4f} "
          f"(SE {se_fit:.4f}) -> gap {gap:+.4f} [{gap - 1.96 * se_gap:+.4f}, "
          f"{gap + 1.96 * se_gap:+.4f}], z={z:.2f}")


if __name__ == "__main__":
    main()
