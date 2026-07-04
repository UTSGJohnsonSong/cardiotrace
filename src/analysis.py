"""
Survey-weighted descriptive analysis for CardioTrace.

NHANES is a complex, stratified, multi-stage probability sample — a raw mean
over the rows is biased. Every prevalence number here is weighted by the
pooled MEC exam weight (WTMEC2YR / n_cycles), so estimates generalize to the
non-institutionalized US population. Point estimates use the weights directly:

    weighted prevalence = Σ(wᵢ · yᵢ) / Σ(wᵢ)

(Design-based standard errors would additionally use the strata/PSU columns via
a Taylor-series or replicate-weight estimator; we retain those columns in the
mart so that refinement is a drop-in.)
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CVD_OUTCOMES = {
    "has_heart_failure": "Heart Failure",
    "has_mi": "Heart Attack (MI)",
    "has_chd": "Coronary Heart Disease",
    "has_angina": "Angina",
    "has_stroke": "Stroke",
    "has_any_cvd": "Any CVD",
}


def _cycle_midyear(cycle: str) -> float:
    a, b = cycle.split("-")
    return (int(a) + int(b)) / 2.0


def weighted_prevalence(df: pd.DataFrame, outcome: str,
                        by: list[str] | None = None,
                        weight: str = "survey_weight_pooled") -> pd.DataFrame:
    """Survey-weighted prevalence (%) of `outcome`, optionally within groups."""
    d = df.dropna(subset=[outcome, weight]).copy()
    d[outcome] = d[outcome].astype(float)

    def _agg(g):
        w = g[weight].to_numpy(float)
        y = g[outcome].to_numpy(float)
        wsum = w.sum()
        return pd.Series({
            "prevalence_pct": 100.0 * (w * y).sum() / wsum if wsum else np.nan,
            "n_unweighted": len(g),
            "n_cases": int(y.sum()),
            "weighted_pop": wsum,
        })

    if by:
        out = d.groupby(by, observed=True).apply(_agg, include_groups=False).reset_index()
    else:
        out = _agg(d).to_frame().T
    return out


def prevalence_trend(df: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Weighted prevalence of one outcome by cycle, ordered in time."""
    t = weighted_prevalence(df, outcome, by=["cycle"])
    t["midyear"] = t["cycle"].map(_cycle_midyear)
    return t.sort_values("midyear").reset_index(drop=True)


def equity_trend(df: pd.DataFrame, outcome: str = "has_any_cvd") -> pd.DataFrame:
    """Weighted prevalence by race/ethnicity and cycle (health-equity view)."""
    t = weighted_prevalence(df, outcome, by=["cycle", "race_ethnicity"])
    t["midyear"] = t["cycle"].map(_cycle_midyear)
    return t.sort_values(["race_ethnicity", "midyear"]).reset_index(drop=True)


def covid_comparison(df: pd.DataFrame,
                     lab_cols=("systolic_bp_avg", "bmi", "hba1c",
                               "total_cholesterol", "fasting_glucose")) -> pd.DataFrame:
    """Weighted CVD prevalence and mean risk markers, pre- vs post-pandemic."""
    rows = []
    for period, g in df.groupby("covid_period", observed=True):
        w = g["survey_weight_pooled"]
        rec = {"covid_period": period, "n_unweighted": len(g)}
        for oc in CVD_OUTCOMES:
            gg = g.dropna(subset=[oc])
            ww = gg["survey_weight_pooled"].to_numpy(float)
            yy = gg[oc].to_numpy(float)
            rec[f"pct_{oc}"] = 100.0 * (ww * yy).sum() / ww.sum() if ww.sum() else np.nan
        for lab in lab_cols:
            gg = g.dropna(subset=[lab])
            ww = gg["survey_weight_pooled"].to_numpy(float)
            vv = gg[lab].to_numpy(float)
            rec[f"mean_{lab}"] = (ww * vv).sum() / ww.sum() if ww.sum() else np.nan
        rows.append(rec)
    order = {"pre_pandemic": 0, "post_pandemic": 1}
    return pd.DataFrame(rows).sort_values("covid_period", key=lambda s: s.map(order)).reset_index(drop=True)
