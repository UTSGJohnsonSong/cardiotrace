"""Run the locked historical prognostic benchmark on paired temporal samples."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models import (CauseSpecificRisk, P_FEATURES, TRAIN_CYCLES,
                        TEST_10Y_CYCLES, TEST_5Y_CYCLES, prepare)
from src.discrimination import evaluate, cluster_bootstrap_delta
from src.pce import INPUTS, score, MortalityRecalibration, decision_curve, observed_cif

TAB = ROOT / "reports/tables"
SAME_INPUTS = ["age", "male", "race_black", "total_cholesterol", "hdl_cholesterol",
               "systolic_bp", "bp_treated", "diabetes_dx", "current_smoker"]


def common_sample(cohort, other=False):
    """Return the actual shared sample and each explicitly counted exclusion."""
    rows = []
    def record(label, d):
        rows.append({"step": label, "n": len(d), "cvd_deaths": int(d.cvd_death.sum())})
    record("published_cohort", cohort)
    d = cohort.dropna(subset=INPUTS + ["race_eth"])
    record("pce_complete_all_ethnicities", d)
    if not other:
        d = d[d.race_eth.isin(["NH White", "NH Black"])]
    record("ethnicity_eligible", d)
    prepared = prepare(d)
    needed = P_FEATURES + ["followup_years", "cvd_death", "competing_death", "wtmec2yr", "design_cluster"]
    d = d.loc[prepared[needed].notna().all(axis=1)].copy()
    record("paired_complete_all_arms", d)
    if d.empty or (d.wtmec2yr <= 0).any():
        raise ValueError("Empty paired sample or invalid exam weight")
    return d, rows


def model_parameters(model):
    result = {}
    for name in ["cvd", "competing"]:
        fitted = getattr(model, name)
        result[name] = {
            "coefficients": fitted.params_.to_dict(),
            "centering_mean": fitted._norm_mean.to_dict(),
            "baseline_cumulative_hazard": [
                {"time": float(t), "hazard": float(v)}
                for t, v in fitted.baseline_cumulative_hazard_.iloc[:, 0].items()],
        }
    return result


def run(cohort, *, other=False):
    sample, cascade = common_sample(cohort, other)
    train = sample[sample.cycle.isin(TRAIN_CYCLES)]
    train_scores = score(train, other_ethnicities=other)
    adapted = MortalityRecalibration().fit(train, train_scores)
    same = CauseSpecificRisk(SAME_INPUTS).fit(prepare(train, tobin=False), prepared=True)
    full = CauseSpecificRisk(P_FEATURES).fit(train)
    result = {"cascade": cascade, "n_train": len(train),
              "train_cvd_deaths": int(train.cvd_death.sum()),
              "train_competing_deaths": int(train.competing_death.sum()),
              "train_cycles": TRAIN_CYCLES, "tests": {}}
    curves, metric_rows = [], []
    for cycles, horizon in [(TEST_10Y_CYCLES, 10.), (TEST_5Y_CYCLES, 5.)]:
        test = sample[sample.cycle.isin(cycles)]
        raw_scores = score(test, other_ethnicities=other)
        risks = {
            "1a_published_ascvd": raw_scores.risk_10y_ascvd,
            "1b_mortality_recalibration": adapted.predict(raw_scores, horizon),
            "2_same_inputs_refit": same.predict_cif(prepare(test, tobin=False), horizon, prepared=True),
            "3_cardiotrace_refit": full.predict_cif(test, horizon),
        }
        design = prepare(test)
        mortality = {k: v for k, v in risks.items() if not k.startswith("1a")}
        dc = decision_curve(mortality, test, horizon, censoring="aalen_johansen")
        curves.append(dc)
        observed = (test.cvd_death == 1) & (test.followup_years <= horizon)
        metrics = {}
        for arm, risk in risks.items():
            m = evaluate(risk, design, horizon)
            m.update(events_at_horizon=int(observed.sum()),
                     mean_score_pct=float(100*np.average(risk, weights=test.wtmec2yr)),
                     observed_cvd_mortality_pct=100*observed_cif(test, horizon))
            metrics[arm] = m
            metric_rows.append({"horizon_years": horizon, "arm": arm, **m})
        print(f"{'sensitivity' if other else 'primary'} {horizon:g}y: {len(test)} paired participants", flush=True)
        deltas = {arm: cluster_bootstrap_delta(risk, risks["1a_published_ascvd"], design,
                                             horizon, n_boot=200, seed=20260906)
                  for arm, risk in mortality.items()}
        result["tests"][f"{horizon:g}y"] = {"cycles": cycles, "metrics": metrics,
                                          "delta_c_vs_published_pce": deltas}
    params = {"1b": adapted.baselines, "2": model_parameters(same), "3": model_parameters(full)}
    return result, pd.concat(curves, ignore_index=True), pd.DataFrame(metric_rows), params


def main():
    cohort = pd.read_csv(ROOT / "data/processed/cohort_part3.csv.gz")
    TAB.mkdir(exist_ok=True, parents=True)
    sample, _ = common_sample(cohort)
    rows = []
    for label, cycles in [("train", TRAIN_CYCLES), ("test_10y", TEST_10Y_CYCLES), ("test_5y", TEST_5Y_CYCLES)]:
        d = sample[sample.cycle.isin(cycles)]
        rows.append({"split": label, "variable": "participants", "value": len(d)})
        for col in ["age", "race_black", "systolic_bp", "bp_treated", "total_cholesterol",
                    "hdl_cholesterol", "diabetes_dx", "current_smoker", "bmi", "followup_years"]:
            rows.append({"split": label, "variable": col, "value": float(np.average(d[col], weights=d.wtmec2yr))})
        rows.append({"split": label, "variable": "male", "value": float(np.average(d.sex == "Male", weights=d.wtmec2yr))})
        for col in ["cvd_death", "competing_death"]:
            rows.append({"split": label, "variable": col, "value": int(d[col].sum())})
    pd.DataFrame(rows).to_csv(TAB / "pce_participant_characteristics.csv", index=False, float_format="%.10g")
    out = {"protocol": "docs/pce-benchmark.md §3.5; research-design.md 2026-09-06 implementation decisions",
           "endpoint_warning": "Prespecified historical prognostic benchmark. Published PCE predicts hard ASCVD; outcomes here are CVD mortality. No same-endpoint validation or clinical utility claim.",
           "bootstrap": "200 paired PSU replicates within strata; conditional on training fits",
           "five_year_pce": "Original ten-year PCE score used only for ranking; no five-year hard-ASCVD risk is estimated."}
    for name, other in [("primary", False), ("other_ethnicities_white_equation_sensitivity", True)]:
        results, curves, metrics, params = run(cohort, other=other)
        out[name] = results
        curves.to_csv(TAB / f"decision_curve_{name}.csv", index=False, float_format="%.10g")
        metrics.to_csv(TAB / f"pce_benchmark_{name}.csv", index=False, float_format="%.10g")
        (ROOT / f"reports/pce_parameters_{name}.json").write_text(
            json.dumps(params, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (ROOT / "reports/pce_results.json").write_text(
        json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from src.survival import SURFACE
    curves = pd.read_csv(TAB / "decision_curve_primary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), facecolor=SURFACE)
    labels = {"1b_mortality_recalibration": "PCE mortality adaptation", "2_same_inputs_refit": "Same inputs, refit",
              "3_cardiotrace_refit": "CardioTrace, refit", "treat_all": "Treat all", "treat_none": "Treat none"}
    for ax, horizon in zip(axes, [10, 5]):
        for arm, label in labels.items():
            d = curves[(curves.arm == arm) & (curves.horizon_years == horizon)]
            ax.plot(100*d.threshold, 1000*d.net_benefit, label=label,
                    linestyle="--" if arm.startswith("treat") else "-")
        ax.set(title=f"{horizon}-year CVD mortality", xlabel="Illustrative threshold (%)", ylabel="Net benefit per 1,000")
        ax.set_facecolor(SURFACE)
        ax.grid(alpha=.2)
    axes[0].legend(fontsize=7)
    fig.suptitle("Exploratory decision curves · NH White / Black · point estimates")
    fig.tight_layout()
    fig.savefig(ROOT / "reports/figures/pce_decision_curves.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    main()
