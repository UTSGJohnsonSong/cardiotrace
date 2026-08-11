"""
Survival models for the Part 3 cohort.

TWO QUESTIONS, TWO MODELS, TWO VARIABLE SETS
--------------------------------------------
The DAG in docs/research-design.md says there is no single correct covariate
list — each estimand gets its own, and mixing them is the Table 2 fallacy.

  aetiologic (E2)   what is the total effect of blood pressure on CVD death?
                    adjust for confounders of BP only: age, sex, race, education,
                    income, smoking, adiposity. Do NOT adjust for kidney function
                    or inflammation (downstream of BP) or for antihypertensive
                    use (a collider on BP -> treatment <- healthcare access).
                    Report hazard ratios.

  prediction (P)    what is this person's absolute 10-year risk of CVD death?
                    use everything measurable at baseline, including treatment
                    status. Interpret no coefficient. Report discrimination,
                    calibration, and absolute risk.

TREATMENT AND THE EXPOSURE
--------------------------
Measured blood pressure in a treated participant is a post-treatment value: they
are not "a person with normal blood pressure", they are a person whose blood
pressure is being held down. Conditioning on treatment opens a backdoor through
healthcare access, so the aetiologic model instead applies the standard Tobin
adjustment — add a constant to the measured value of treated participants to
approximate the untreated level. This is why the pipeline needed RXQ/BPQ at all.

COMPETING RISK, WITHOUT FINE-GRAY
---------------------------------
Absolute risk is computed from TWO cause-specific Cox models rather than a
subdistribution-hazard fit:

    CIF_1(t|X) = sum over u<=t of  S(u-|X) * dH_1(u|X)
    S(u|X)     = exp( -(H_1(u|X) + H_2(u|X)) )

This is the cause-specific-hazards route to absolute risk. It gives the same
quantity Fine-Gray targets, keeps one fitting path for both questions, and makes
the competing hazard an explicit object rather than something folded into a
reweighting. Ignoring the second model entirely — the 1 - exp(-H_1) shortcut —
is what overstates risk, by 7.4% at 15 years in this cohort.

SURVEY DESIGN
-------------
Fitted with the pooled MEC exam weight and a robust variance clustered on
stratum x PSU. Same-PSU participants are not independent: they share a
neighbourhood, a provider mix and an interviewer. A model-based standard error
would be too small, and a random K-fold split would leak them across the
train/test boundary — which is why validation below splits on survey cycle.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

log = logging.getLogger(__name__)

# Tobin et al. (2005): add a constant to the measured pressure of treated
# participants to recover the untreated level. +10/+5 mmHg is the widely used
# pair; the choice is a sensitivity analysis, not a fact.
TOBIN_SBP, TOBIN_DBP = 10.0, 5.0

# Confounders of the BP -> CVD death relation. Deliberately excludes anything
# downstream of blood pressure and anything on the treatment path.
E2_ADJUSTMENT = ["age", "male", "race_black", "education", "pir",
                 "smoke_current", "smoke_former", "bmi"]

# Prediction: everything cheaply measurable at a clinic visit.
P_FEATURES = ["age", "male", "race_black", "systolic_bp", "bp_treated",
              "total_cholesterol", "hdl_cholesterol", "diabetes_dx",
              "smoke_current", "smoke_former", "bmi"]

# Cycles with at least ten years of follow-up on every survivor, so a 10-year
# risk is directly observable rather than extrapolated.
TRAIN_CYCLES = ["1999-2000", "2001-2002", "2003-2004"]
TEST_10Y_CYCLES = ["2005-2006", "2007-2008"]
TEST_5Y_CYCLES = ["2009-2010", "2011-2012", "2013-2014"]


def prepare(df: pd.DataFrame, tobin: bool = True) -> pd.DataFrame:
    """Model matrix: numeric encodings, Tobin adjustment, design columns."""
    d = df.copy()
    d["male"] = (d.sex == "Male").astype(float)
    d["smoke_current"] = (d.smoking == "current").astype(float).where(d.smoking.notna())
    d["smoke_former"] = (d.smoking == "former").astype(float).where(d.smoking.notna())
    if tobin:
        treated = d.bp_treated == 1
        d.loc[treated, "systolic_bp"] = d.loc[treated, "systolic_bp"] + TOBIN_SBP
        d.loc[treated, "diastolic_bp"] = d.loc[treated, "diastolic_bp"] + TOBIN_DBP
    # Same-PSU participants are correlated; the cluster is stratum x PSU.
    d["design_cluster"] = d.strata.astype(str) + "_" + d.psu.astype(str)
    return d


def _fit(d: pd.DataFrame, covariates: list[str], event_col: str,
         penalizer: float = 0.0) -> CoxPHFitter:
    cols = covariates + ["followup_years", event_col, "wtmec2yr", "design_cluster"]
    fit_df = d[cols].dropna()
    cph = CoxPHFitter(penalizer=penalizer)
    cph.fit(fit_df, duration_col="followup_years", event_col=event_col,
            weights_col="wtmec2yr", cluster_col="design_cluster", robust=True)
    return cph


def fit_aetiologic(df: pd.DataFrame, exposure: str = "systolic_bp",
                   tobin: bool = True) -> pd.DataFrame:
    """Cause-specific Cox for the total effect of `exposure` on CVD death.

    Non-CVD death is treated as censoring. That is the correct handling for the
    aetiologic question — "does blood pressure raise the rate of CVD death among
    those still alive" — and the wrong handling for absolute risk, which is what
    `predict_cif` is for.
    """
    d = prepare(df, tobin=tobin)
    covs = [exposure] + [c for c in E2_ADJUSTMENT if c != exposure]
    cph = _fit(d, covs, "cvd_death")
    out = cph.summary[["coef", "exp(coef)", "exp(coef) lower 95%",
                       "exp(coef) upper 95%", "p"]].copy()
    out.columns = ["log_hr", "hr", "hr_lo95", "hr_hi95", "p"]
    out.insert(0, "n", int(cph.weights.shape[0]))
    return out.round(4)


class CauseSpecificRisk:
    """Two cause-specific Cox fits combined into an absolute-risk prediction."""

    def __init__(self, features: list[str]):
        self.features = features
        self.cvd: CoxPHFitter | None = None
        self.competing: CoxPHFitter | None = None

    def fit(self, train: pd.DataFrame) -> "CauseSpecificRisk":
        d = prepare(train)
        self.cvd = _fit(d, self.features, "cvd_death")
        self.competing = _fit(d, self.features, "competing_death")
        return self

    def _cum_hazards(self, model: CoxPHFitter, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        """H(t|X) on a shared time grid: baseline cumulative hazard x risk score."""
        base = model.baseline_cumulative_hazard_.iloc[:, 0]
        h0 = np.interp(times, base.index.to_numpy(float), base.to_numpy(float),
                       left=0.0)
        risk = model.predict_partial_hazard(X).to_numpy(float)
        return np.outer(risk, h0)                       # (n_people, n_times)

    def predict_cif(self, test: pd.DataFrame, horizon: float,
                    n_grid: int = 400) -> pd.Series:
        """Absolute probability of CVD death by `horizon`, competing risk included."""
        if self.cvd is None:
            raise RuntimeError("fit() first")
        d = prepare(test)
        X = d[self.features]
        times = np.linspace(0.0, horizon, n_grid)
        h1 = self._cum_hazards(self.cvd, X, times)
        h2 = self._cum_hazards(self.competing, X, times)
        # S(u-) uses the ALL-CAUSE hazard: a person who has died of anything is
        # no longer at risk of dying of CVD. Dropping h2 here is exactly the
        # error the descriptive figure quantifies.
        surv_prev = np.exp(-(h1 + h2))
        dh1 = np.diff(h1, axis=1, prepend=0.0)
        cif = (surv_prev * dh1).cumsum(axis=1)[:, -1]
        return pd.Series(cif, index=d.index, name=f"cif_{horizon:g}y")


def concordance(risk: pd.Series, time: pd.Series, event: pd.Series,
                weights: pd.Series | None = None) -> float:
    """Harrell's C for a higher-is-worse risk score, competing deaths censored."""
    from lifelines.utils import concordance_index
    ok = risk.notna() & time.notna() & event.notna()
    return float(concordance_index(time[ok], -risk[ok], event[ok]))


def calibration_table(risk: pd.Series, observed: pd.Series, weights: pd.Series,
                      n_bins: int = 10) -> pd.DataFrame:
    """Predicted vs observed risk by decile of predicted risk.

    Discrimination says whether the ranking is right; calibration says whether
    the numbers are. A model can rank perfectly and still be unusable — which is
    the documented failure mode of the Pooled Cohort Equations in contemporary
    cohorts, and the reason this table exists at all.
    """
    d = pd.DataFrame({"risk": risk, "obs": observed, "w": weights}).dropna()
    d["bin"] = pd.qcut(d.risk, n_bins, labels=False, duplicates="drop")
    g = d.groupby("bin")
    out = pd.DataFrame({
        "n": g.size(),
        "predicted_pct": 100 * g.apply(lambda x: np.average(x.risk, weights=x.w),
                                       include_groups=False),
        "observed_pct": 100 * g.apply(lambda x: np.average(x.obs, weights=x.w),
                                      include_groups=False),
    })
    out["difference_pp"] = (out.predicted_pct - out.observed_pct).round(2)
    return out.round(2)
