"""
CardioTrace end-to-end pipeline.

Runs the whole project from a populated database to final artifacts:

    load raw XPT  →  dbt build (staging + mart)  →  survey-weighted analysis
    →  ML models (LR + XGBoost per CVD outcome)  →  SHAP  →  figures + tables

Prerequisites:
    docker compose up -d            # Postgres on localhost:5435
    python data/download.py         # XPT files into data/raw/

Usage:
    python run_pipeline.py               # full run (assumes data already loaded via --load once)
    python run_pipeline.py --load        # (re)load raw XPT into Postgres first
    python run_pipeline.py --dbt         # also run `dbt build` before analysis

Outputs land in reports/ (figures/, tables/, results.json).
"""

import argparse
import json
import logging
import subprocess
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

import src.analysis as A
import src.model as M
from src.etl import get_engine, load_all_cycles

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("pipeline")

ROOT = Path(__file__).parent
FIG = ROOT / "reports" / "figures"
TAB = ROOT / "reports" / "tables"
DASH = ROOT / "dashboard" / "data"
for d in (FIG, TAB, DASH):
    d.mkdir(parents=True, exist_ok=True)

# Palette (colour-blind-safe)
C = {"blue": "#2166ac", "red": "#b2182b", "teal": "#35978f", "orange": "#d6604d",
     "purple": "#762a83", "gray": "#7f7f7f", "green": "#1a9850"}
plt.rcParams.update({"figure.dpi": 120, "font.size": 11, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False, "axes.spines.right": False})

# Features shared across all outcome models (present in the mart)
NUM_FEATURES = ["age", "poverty_income_ratio", "systolic_bp_avg", "diastolic_bp_avg",
                "bmi", "waist_cm", "total_cholesterol", "hdl_cholesterol",
                "triglycerides", "non_hdl_cholesterol", "hba1c", "crp"]
CAT_FEATURES = ["gender", "race_ethnicity", "education_level", "hypertension_flag",
                "diabetes_flag", "current_smoker", "obese"]


def _fmt(x, d=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)


# ── Analysis blocks ──────────────────────────────────────────────────────────

def run_prevalence(df, results):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    colors = [C["red"], C["orange"], C["purple"], C["teal"], C["blue"], C["gray"]]
    trends = {}
    for (oc, label), col in zip(A.CVD_OUTCOMES.items(), colors):
        t = A.prevalence_trend(df, oc)
        trends[oc] = t
        ax.plot(t["midyear"], t["prevalence_pct"], marker="o", lw=2, color=col, label=label)
        t.to_csv(TAB / f"prevalence_{oc}.csv", index=False)
    ax.set_title("Survey-weighted CVD prevalence, US adults 20+, 1999–2023", fontweight="bold")
    ax.set_xlabel("Survey cycle (midyear)"); ax.set_ylabel("Prevalence (%)")
    ax.legend(frameon=False, ncol=2, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "prevalence_trend.png"); plt.close(fig)

    any_t = trends["has_any_cvd"]
    results["prevalence"] = {
        "any_cvd_first": {"cycle": any_t.iloc[0]["cycle"], "pct": _fmt(any_t.iloc[0]["prevalence_pct"])},
        "any_cvd_last": {"cycle": any_t.iloc[-1]["cycle"], "pct": _fmt(any_t.iloc[-1]["prevalence_pct"])},
        "by_outcome_latest": {oc: _fmt(trends[oc].iloc[-1]["prevalence_pct"]) for oc in A.CVD_OUTCOMES},
        "total_n": int(len(df)),
    }
    log.info("Prevalence trends done")


def run_equity(df, results):
    eq = A.equity_trend(df, "has_any_cvd")
    eq.to_csv(TAB / "equity_any_cvd_by_race.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for race, g in eq.groupby("race_ethnicity"):
        if g["n_unweighted"].sum() < 200:
            continue
        ax.plot(g["midyear"], g["prevalence_pct"], marker="o", lw=1.8, label=race)
    ax.set_title("Any-CVD prevalence by race/ethnicity (survey-weighted)", fontweight="bold")
    ax.set_xlabel("Survey cycle (midyear)"); ax.set_ylabel("Prevalence (%)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "equity_by_race.png"); plt.close(fig)

    latest = eq[eq["midyear"] == eq["midyear"].max()].sort_values("prevalence_pct", ascending=False)
    results["equity"] = {
        "latest_cycle": latest.iloc[0]["cycle"] if len(latest) else None,
        "latest_by_race": {r["race_ethnicity"]: _fmt(r["prevalence_pct"]) for _, r in latest.iterrows()},
    }
    log.info("Equity analysis done")


def run_covid(df, results):
    cov = A.covid_comparison(df)
    cov.to_csv(TAB / "covid_pre_post.csv", index=False)
    results["covid"] = {
        row["covid_period"]: {
            "n": int(row["n_unweighted"]),
            "pct_any_cvd": _fmt(row.get("pct_has_any_cvd")),
            "mean_bmi": _fmt(row.get("mean_bmi")),
            "mean_hba1c": _fmt(row.get("mean_hba1c")),
            "mean_sbp": _fmt(row.get("mean_systolic_bp_avg")),
        } for _, row in cov.iterrows()
    }
    log.info("COVID pre/post comparison done")


def run_models(df, results):
    feats = [f for f in NUM_FEATURES + CAT_FEATURES if f in df.columns]
    cat = [f for f in CAT_FEATURES if f in df.columns]
    metrics_rows, best = [], {}
    for oc, label in A.CVD_OUTCOMES.items():
        if oc not in df.columns or df[oc].notna().sum() < 500:
            continue
        res = M.train_target(df, oc, feats, cat, cv_folds=5)
        for name, r in res.items():
            metrics_rows.append(r["metrics"])
        # pick best by PR-AUC
        bname = max(res, key=lambda n: res[n]["metrics"]["pr_auc"])
        best[oc] = (bname, res[bname])

    mdf = pd.DataFrame(metrics_rows)
    mdf.to_csv(TAB / "model_metrics.csv", index=False)

    # Performance chart: PR-AUC by outcome & model
    fig, ax = plt.subplots(figsize=(9, 5))
    outcomes = [o for o in A.CVD_OUTCOMES if o in mdf["target"].unique()]
    x = np.arange(len(outcomes)); w = 0.38
    for i, model in enumerate(["logistic_regression", "xgboost"]):
        vals = [mdf[(mdf.target == o) & (mdf.model == model)]["pr_auc"].values[0] for o in outcomes]
        ax.bar(x + (i - 0.5) * w, vals, w, label=model.replace("_", " ").title(),
               color=C["gray"] if i == 0 else C["blue"])
    ax.set_xticks(x); ax.set_xticklabels([A.CVD_OUTCOMES[o] for o in outcomes], rotation=25, ha="right")
    ax.set_ylabel("PR-AUC (cross-validated)")
    ax.set_title("Model performance by CVD outcome", fontweight="bold")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "model_performance.png"); plt.close(fig)

    # SHAP on best model for Any CVD
    shap_top = _shap_for(df, "has_any_cvd", feats, cat, best)
    results["models"] = {
        "features_used": feats,
        "metrics": {f"{r['target']}__{r['model']}": {
            "roc_auc": r["roc_auc"], "pr_auc": r["pr_auc"], "f1": r["f1"],
            "prevalence": r["prevalence"], "n": r["n_total"]} for r in metrics_rows},
        "best_by_outcome": {o: {"model": b[0], "roc_auc": b[1]["metrics"]["roc_auc"],
                                "pr_auc": b[1]["metrics"]["pr_auc"]} for o, b in best.items()},
        "shap_top_features": shap_top,
    }
    log.info("Modeling + SHAP done")


def _shap_for(df, target, feats, cat, best):
    import shap
    if target not in best:
        return []
    name, r = best[target]
    pipe = r["pipeline"]
    mask = df[target].notna()
    X = df.loc[mask, feats]
    Xs = X.sample(min(2000, len(X)), random_state=42)
    Xt = pipe.named_steps["prep"].transform(Xs)
    fnames = [f.split("__")[-1] for f in pipe.named_steps["prep"].get_feature_names_out()]
    try:
        model = pipe.named_steps["model"]
        if name == "xgboost":
            sv = shap.TreeExplainer(model).shap_values(Xt)
        else:
            sv = shap.LinearExplainer(model, Xt).shap_values(Xt)
        if isinstance(sv, list):
            sv = sv[1]
        plt.figure()
        shap.summary_plot(sv, Xt, feature_names=fnames, show=False, max_display=12)
        plt.title(f"SHAP — drivers of {A.CVD_OUTCOMES[target]} ({name})", fontweight="bold")
        plt.tight_layout(); plt.savefig(FIG / f"shap_{target}.png", dpi=120, bbox_inches="tight"); plt.close()
        mean_abs = np.abs(sv).mean(0)
        order = np.argsort(mean_abs)[::-1][:10]
        return [{"feature": fnames[i], "mean_abs_shap": round(float(mean_abs[i]), 4)} for i in order]
    except Exception as e:
        log.warning(f"SHAP failed: {e}")
        return []


def export_tableau(df):
    """Aggregated, Tableau-ready CSVs (Public can't hit Postgres directly)."""
    rows = []
    for oc, label in A.CVD_OUTCOMES.items():
        t = A.weighted_prevalence(df, oc, by=["cycle", "gender", "race_ethnicity"])
        t["outcome"] = label
        rows.append(t)
    long = pd.concat(rows, ignore_index=True)
    long["midyear"] = long["cycle"].map(A._cycle_midyear)
    long.to_csv(DASH / "prevalence_long.csv", index=False)
    log.info(f"Tableau export: {len(long)} rows → dashboard/data/prevalence_long.csv")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", action="store_true", help="Load raw XPT into Postgres first")
    ap.add_argument("--dbt", action="store_true", help="Run dbt build before analysis")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    engine = get_engine()

    if args.load:
        log.info("Loading raw XPT into Postgres…")
        load_all_cycles(engine)
    if args.dbt:
        log.info("Running dbt build…")
        subprocess.run(["dbt", "build", "--profiles-dir", "."], cwd=ROOT / "dbt", check=True)

    df = pd.read_sql("SELECT * FROM mart.mart_cv_master", engine)
    log.info(f"Loaded mart_cv_master: {df.shape[0]:,} rows × {df.shape[1]} cols")

    results = {"dataset": {"rows": int(df.shape[0]),
                           "cycles": sorted(df["cycle"].unique().tolist())}}
    run_prevalence(df, results)
    run_equity(df, results)
    run_covid(df, results)
    run_models(df, results)
    export_tableau(df)

    (ROOT / "reports" / "results.json").write_text(json.dumps(results, indent=2))
    log.info("results.json written. Pipeline complete.")


if __name__ == "__main__":
    main()
