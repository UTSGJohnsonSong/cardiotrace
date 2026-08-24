"""
Fit and validate the Part 3 survival models.

    aetiologic  cause-specific Cox for the total effect of systolic BP
    prediction  two cause-specific Cox fits -> absolute risk, validated forward
                in time

Validation splits on SURVEY CYCLE, not at random. Participants sampled in the
same primary sampling unit share a neighbourhood, a provider mix and an
interviewer, so a random K-fold puts correlated people on both sides of the
boundary and reports an optimistic number. Splitting on cycle also asks the
question that matters for a risk score: does it still work on people surveyed
later? In TRIPOD terms this is narrow external validation, not internal.

    train        1999-2004    every survivor followed >= 14 years
    test 10y     2005-2008    every survivor followed >= 10.8 years
    test 5y      2009-2014    tests transportability further out

    python scripts/fit_survival_models.py
"""

import json
import logging
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.models import (  # noqa: E402
    CauseSpecificRisk, P_FEATURES, TRAIN_CYCLES, TEST_10Y_CYCLES, TEST_5Y_CYCLES,
    calibration_table, concordance, fit_aetiologic,
)
from src.survival import (  # noqa: E402
    AXIS, CATEGORICAL, GRIDLINE, INK_MUTED, INK_PRIMARY, INK_SECONDARY, SURFACE,
)

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
COHORT = ROOT / "data" / "processed" / "cohort_part3.csv.gz"
FIG, TAB = ROOT / "reports" / "figures", ROOT / "reports" / "tables"

plt.rcParams.update({
    "figure.dpi": 140, "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRIDLINE, "grid.linewidth": 0.8,
})


def figure_calibration(panels: list[tuple[str, pd.DataFrame]]) -> None:
    """Predicted vs observed risk by decile, one panel per test set.

    A scatter against the identity line, not a bar chart: the question is
    agreement between two continuous quantities, and the 45-degree reference is
    the whole point. Each panel carries ONE series, so it needs no legend — the
    title names it. The identity line is chrome (muted grey), not a series.
    """
    fig, axes = plt.subplots(1, len(panels), figsize=(4.6 * len(panels), 4.6))
    axes = np.atleast_1d(axes)

    for ax, (title, tab) in zip(axes, panels):
        hi = max(tab.predicted_pct.max(), tab.observed_pct.max()) * 1.12
        ax.plot([0, hi], [0, hi], lw=1.2, color=INK_MUTED, ls="--", zorder=1)
        ax.annotate("perfect calibration", (hi * 0.62, hi * 0.66), color=INK_MUTED,
                    fontsize=8, rotation=38, ha="center")
        ax.plot(tab.predicted_pct, tab.observed_pct, "-o", lw=1.6, ms=6,
                color=CATEGORICAL[0], zorder=3)
        ax.set_title(title, fontweight="bold", color=INK_PRIMARY, loc="left", pad=10)
        ax.set_xlabel("Predicted risk (%)", color=INK_SECONDARY)
        ax.set_ylabel("Observed risk (%)", color=INK_SECONDARY)
        ax.set_xlim(0, hi)
        ax.set_ylim(0, hi)
        ax.set_aspect("equal")
        ax.grid(alpha=0.7)
        ax.set_axisbelow(True)

    # Title and subtitle need explicit vertical separation: suptitle defaults
    # place the two on top of each other once the axes are tightened.
    fig.suptitle("Absolute-risk calibration by decile of predicted risk",
                 fontweight="bold", fontsize=13, color=INK_PRIMARY,
                 x=0.015, ha="left", y=1.10)
    fig.text(0.015, 1.035, "Model trained on NHANES 1999–2004 and applied forward "
             "to later cycles · survey-weighted · each point is a decile of "
             "predicted risk", color=INK_MUTED, fontsize=8.5, ha="left", va="bottom")
    fig.savefig(FIG / "calibration.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(COHORT)
    results: dict = {}

    log.info("=== aetiologic: total effect of systolic BP on CVD death ===")
    aet = fit_aetiologic(df, "systolic_bp", tobin=True)
    aet.to_csv(TAB / "cox_systolic_bp.csv")
    log.info(aet.to_string())
    # exp(coef * 10), not hr ** 10. The second raises an ALREADY-ROUNDED
    # per-unit hazard ratio to the tenth power and compounds the rounding:
    # 1.0115 ** 10 = 1.121137 against exp(coef * 10) = 1.121588, a difference
    # that reaches the third decimal this report prints.
    hr10 = float(np.exp(aet.loc["systolic_bp", "log_hr"] * 10))
    lo10 = float(np.exp(aet.loc["systolic_bp", "log_lo95"] * 10))
    hi10 = float(np.exp(aet.loc["systolic_bp", "log_hi95"] * 10))
    log.info(f"\nper 10 mmHg: HR {hr10:.3f} (95% CI {lo10:.3f}-{hi10:.3f})")
    results["aetiologic_sbp_per_10mmhg"] = {
        "hr": round(hr10, 4), "lo95": round(lo10, 4), "hi95": round(hi10, 4)}

    # Sensitivity: the Tobin constant is a convention, so report the model
    # without it too. If the exposure effect only exists with the adjustment,
    # that is worth knowing.
    raw = fit_aetiologic(df, "systolic_bp", tobin=False)
    results["aetiologic_sbp_per_10mmhg_no_tobin"] = {
        "hr": round(float(np.exp(raw.loc["systolic_bp", "log_hr"] * 10)), 4)}
    log.info(f"without Tobin adjustment:   HR {results['aetiologic_sbp_per_10mmhg_no_tobin']['hr']:.3f}")

    log.info("\n=== prediction: forward-in-time validation ===")
    train = df[df.cycle.isin(TRAIN_CYCLES)]
    model = CauseSpecificRisk(P_FEATURES).fit(train)
    log.info(f"train {len(train):,} participants, {int(train.cvd_death.sum())} CVD deaths")

    panels, summary = [], {}
    for label, cycles, horizon in [
        ("Test 2005–2008, 10-year risk", TEST_10Y_CYCLES, 10.0),
        ("Test 2009–2014, 5-year risk", TEST_5Y_CYCLES, 5.0),
    ]:
        test = df[df.cycle.isin(cycles)]
        risk = model.predict_cif(test, horizon)
        observed = ((test.cvd_death == 1) & (test.followup_years <= horizon)).astype(float)
        w = test.wtmec2yr.reindex(risk.index)
        # Weighted, and censored at the horizon the label claims. The unweighted
        # value is kept beside it: it is what was published, and a reader
        # deserves to see how far the correction moved it rather than only the
        # corrected number.
        c = concordance(risk, test.followup_years, test.cvd_death,
                        weights=w, horizon=horizon)
        c_unw = concordance(risk, test.followup_years, test.cvd_death)
        tab = calibration_table(risk, observed.reindex(risk.index), w)
        tab.to_csv(TAB / f"calibration_{horizon:g}y.csv")
        panels.append((label, tab))

        # These two were unweighted while the calibration table beside them was
        # weighted, so a summary line and the table it summarised were different
        # estimands. Both are weighted now.
        keep = risk.dropna().index
        ww = w.reindex(keep).to_numpy(float)
        pred_mean = 100 * float(np.average(risk.reindex(keep).to_numpy(float), weights=ww))
        obs_mean = 100 * float(np.average(observed.reindex(keep).to_numpy(float), weights=ww))
        summary[label] = {"n": len(test), "cvd_deaths": int(test.cvd_death.sum()),
                          "horizon_years": horizon, "harrell_c": round(c, 3),
                          "harrell_c_unweighted": round(c_unw, 3),
                          "n_evaluable": int(len(keep)),
                          "mean_predicted_pct": round(pred_mean, 2),
                          "mean_observed_pct": round(obs_mean, 2)}
        log.info(f"\n{label}: n={len(test):,}  C={c:.3f} (unweighted {c_unw:.3f})  "
                 f"predicted {pred_mean:.2f}% vs observed {obs_mean:.2f}%")
        log.info(tab.to_string())

    results["prediction"] = summary
    figure_calibration(panels)
    (ROOT / "reports" / "model_results.json").write_text(json.dumps(results, indent=2))
    log.info(f"\nfigure -> {FIG / 'calibration.png'}")
    log.info(f"results -> {ROOT / 'reports' / 'model_results.json'}")


if __name__ == "__main__":
    main()
