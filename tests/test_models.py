"""Tests for the survival models.

Focus is on the transformations that silently change a number: the treatment
adjustment, the three-level smoking encoding, and whether absolute risk actually
accounts for the competing hazard rather than only appearing to.

    python -m pytest tests/test_models.py -q
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.models import (  # noqa: E402
    TOBIN_DBP, TOBIN_SBP, CauseSpecificRisk, calibration_table, prepare,
)

warnings.filterwarnings("ignore")


def _cohort(n=600, seed=11):
    """Synthetic cohort with a real BP effect and a large competing hazard."""
    rng = np.random.default_rng(seed)
    sbp = rng.normal(128, 18, n)
    age = rng.normal(60, 10, n)
    # CVD hazard rises with BP and age; the competing hazard rises with age only.
    h_cvd = 0.004 * np.exp(0.02 * (sbp - 128) + 0.05 * (age - 60))
    h_oth = 0.012 * np.exp(0.06 * (age - 60))
    t_cvd = rng.exponential(1 / h_cvd)
    t_oth = rng.exponential(1 / h_oth)
    t_cen = rng.uniform(5, 20, n)
    t = np.minimum(np.minimum(t_cvd, t_oth), t_cen)
    return pd.DataFrame({
        "followup_years": t,
        "cvd_death": ((t_cvd <= t_oth) & (t_cvd <= t_cen)).astype(float),
        "competing_death": ((t_oth < t_cvd) & (t_oth <= t_cen)).astype(float),
        "systolic_bp": sbp, "diastolic_bp": rng.normal(75, 10, n), "age": age,
        "sex": rng.choice(["Male", "Female"], n),
        "race_black": rng.choice([0.0, 1.0], n),
        "education": rng.choice([3.0, 4.0, 5.0], n),
        "pir": rng.uniform(0.5, 5, n),
        "bmi": rng.normal(28, 5, n),
        "total_cholesterol": rng.normal(200, 35, n),
        "hdl_cholesterol": rng.normal(52, 14, n),
        "diabetes_dx": rng.choice([0.0, 1.0], n, p=[0.88, 0.12]),
        "bp_treated": rng.choice([0.0, 1.0], n, p=[0.7, 0.3]),
        "smoking": rng.choice(["never", "former", "current"], n),
        "wtmec2yr": rng.uniform(2000, 40000, n),
        "strata": rng.integers(1, 15, n), "psu": rng.integers(1, 3, n),
    })


# ── prepare() ────────────────────────────────────────────────────────────────

def test_tobin_raises_only_treated_participants():
    df = pd.DataFrame({"sex": ["Male", "Male"], "smoking": ["never", "never"],
                       "bp_treated": [1.0, 0.0], "systolic_bp": [130.0, 130.0],
                       "diastolic_bp": [80.0, 80.0], "strata": [1, 1], "psu": [1, 1]})
    out = prepare(df, tobin=True)
    assert out.systolic_bp.tolist() == [130.0 + TOBIN_SBP, 130.0]
    assert out.diastolic_bp.tolist() == [80.0 + TOBIN_DBP, 80.0]


def test_tobin_can_be_switched_off_for_sensitivity():
    df = pd.DataFrame({"sex": ["Male"], "smoking": ["never"], "bp_treated": [1.0],
                       "systolic_bp": [130.0], "diastolic_bp": [80.0],
                       "strata": [1], "psu": [1]})
    assert prepare(df, tobin=False).systolic_bp.iloc[0] == 130.0


def test_unknown_treatment_status_is_not_treated_as_untreated():
    """bp_treated is NaN only when the respondent refused. Adding the Tobin
    constant to them would invent a treatment; leaving the value alone is the
    conservative reading, and the row drops out of the fit on the NaN."""
    df = pd.DataFrame({"sex": ["Male"], "smoking": ["never"], "bp_treated": [np.nan],
                       "systolic_bp": [130.0], "diastolic_bp": [80.0],
                       "strata": [1], "psu": [1]})
    assert prepare(df, tobin=True).systolic_bp.iloc[0] == 130.0


@pytest.mark.parametrize("smoking,current,former", [
    ("never", 0.0, 0.0), ("former", 0.0, 1.0), ("current", 1.0, 0.0),
])
def test_smoking_dummies(smoking, current, former):
    df = pd.DataFrame({"sex": ["Male"], "smoking": [smoking], "bp_treated": [0.0],
                       "systolic_bp": [130.0], "diastolic_bp": [80.0],
                       "strata": [1], "psu": [1]})
    out = prepare(df)
    assert out.smoke_current.iloc[0] == current
    assert out.smoke_former.iloc[0] == former


def test_missing_smoking_stays_missing_in_both_dummies():
    """Two zero dummies mean 'never', which is a claim. Unknown must stay NaN so
    the row leaves the fit rather than joining the reference category."""
    df = pd.DataFrame({"sex": ["Male"], "smoking": [np.nan], "bp_treated": [0.0],
                       "systolic_bp": [130.0], "diastolic_bp": [80.0],
                       "strata": [1], "psu": [1]})
    out = prepare(df)
    assert pd.isna(out.smoke_current.iloc[0]) and pd.isna(out.smoke_former.iloc[0])


def test_design_cluster_is_stratum_crossed_with_psu():
    """PSU numbers restart within each stratum, so PSU alone merges unrelated
    clusters and understates the standard error."""
    df = pd.DataFrame({"sex": ["Male"] * 2, "smoking": ["never"] * 2,
                       "bp_treated": [0.0] * 2, "systolic_bp": [130.0] * 2,
                       "diastolic_bp": [80.0] * 2, "strata": [1, 2], "psu": [1, 1]})
    assert prepare(df).design_cluster.nunique() == 2


# ── absolute risk ────────────────────────────────────────────────────────────

FEATURES = ["age", "male", "systolic_bp", "bmi", "smoke_current", "smoke_former"]


@pytest.fixture(scope="module")
def fitted():
    return CauseSpecificRisk(FEATURES).fit(_cohort())


def test_cif_is_a_probability(fitted):
    r = CauseSpecificRisk(FEATURES).fit(_cohort()).predict_cif(_cohort(seed=99), 10.0)
    assert r.between(0, 1).all()


def test_cif_grows_with_the_horizon(fitted):
    test = _cohort(seed=42)
    a = fitted.predict_cif(test, 5.0)
    b = fitted.predict_cif(test, 15.0)
    assert (b >= a - 1e-12).all() and (b > a).mean() > 0.9


def test_cif_is_below_the_no_competing_risk_shortcut(fitted):
    """1 - exp(-H_1) ignores that a person may die of something else first, so
    it can only overstate. If the two agree, the competing model is not being
    used — the exact failure this class is built to avoid."""
    test = _cohort(seed=7)
    cif = fitted.predict_cif(test, 15.0)
    d = prepare(test)
    h1 = fitted.cvd.predict_cumulative_hazard(d[FEATURES], times=[15.0]).iloc[0]
    naive = pd.Series(1 - np.exp(-h1.to_numpy(float)), index=cif.index)
    assert (naive >= cif - 1e-9).all()
    assert (naive > cif + 1e-6).mean() > 0.9, "competing hazard is being ignored"


def test_higher_blood_pressure_predicts_higher_risk(fitted):
    base = _cohort(seed=5).head(50)
    lo, hi = base.copy(), base.copy()
    lo["systolic_bp"], hi["systolic_bp"] = 110.0, 170.0
    assert (fitted.predict_cif(hi, 10.0) > fitted.predict_cif(lo, 10.0)).all()


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError):
        CauseSpecificRisk(FEATURES).predict_cif(_cohort(), 10.0)


# ── calibration ──────────────────────────────────────────────────────────────

def test_calibration_bins_are_ordered_by_predicted_risk():
    n = 500
    rng = np.random.default_rng(3)
    risk = pd.Series(rng.uniform(0, 0.2, n))
    tab = calibration_table(risk, pd.Series(rng.binomial(1, risk).astype(float)),
                            pd.Series(np.ones(n)))
    assert tab.predicted_pct.is_monotonic_increasing
    assert len(tab) == 10 and tab.n.sum() == n


def test_calibration_recovers_a_well_calibrated_model():
    rng = np.random.default_rng(17)
    n = 40_000
    risk = pd.Series(rng.uniform(0.01, 0.4, n))
    observed = pd.Series(rng.binomial(1, risk).astype(float))
    tab = calibration_table(risk, observed, pd.Series(np.ones(n)))
    assert tab.difference_pp.abs().max() < 2.0


def test_calibration_detects_a_systematically_inflated_model():
    """The failure mode that matters clinically: ranking is perfect, absolute
    numbers are twice too large. Discrimination cannot see this at all."""
    rng = np.random.default_rng(23)
    n = 40_000
    truth = rng.uniform(0.01, 0.2, n)
    observed = pd.Series(rng.binomial(1, truth).astype(float))
    tab = calibration_table(pd.Series(truth * 2), observed, pd.Series(np.ones(n)))
    assert (tab.difference_pp > 0).all()
    assert tab.difference_pp.max() > 5.0
