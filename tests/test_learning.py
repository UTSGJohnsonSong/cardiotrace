"""Regressions for the screen and the discrimination comparison.

Part 4 reports two things that look the same whether or not the code is right:
a variable that "adds nothing" and a model that "does not help". Both are nulls,
and a null is only informative if the machinery could have said otherwise. Each
test here is a defect that would have produced a plausible, publishable, wrong
number rather than a crash.
"""

import numpy as np
import pandas as pd
import pytest

from src.biomarkers import (
    CREATININE_CALIBRATION, calibrate_creatinine, derive, egfr_ckdepi_2021,
)
from src.discrimination import HorizonClassifier, cluster_bootstrap_delta
from src.models import P_FEATURES, CauseSpecificRisk, prepare
from src.screening import STATUS, assert_declared


# ── the calibration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("sex,scr,age,expected", [
    ("Female", 0.7, 55, 102.07),
    ("Male",   0.9, 55, 100.86),
])
def test_egfr_matches_the_published_equation(sex, scr, age, expected):
    """Two points where the equation collapses to something checkable by hand.

    At Scr exactly equal to kappa both the min and the max terms are 1, so eGFR
    reduces to 142 * 0.9938^age * (1.012 if female) -- 102.07 and 100.86. A
    swapped kappa, a swapped alpha, or a female multiplier applied to the wrong
    sex all survive a smoke test and fail here.
    """
    got = egfr_ckdepi_2021(pd.Series([scr]), pd.Series([age]),
                           pd.Series([sex == "Female"]))
    assert got.iloc[0] == pytest.approx(expected, abs=0.05)


def test_egfr_falls_as_creatinine_rises_and_as_age_rises():
    """Direction, which no single reference point pins down."""
    scr = pd.Series([0.6, 1.0, 2.0, 4.0])
    age = pd.Series([50.0] * 4)
    fem = pd.Series([False] * 4)
    e = egfr_ckdepi_2021(scr, age, fem)
    assert (e.diff().dropna() < 0).all()
    young = egfr_ckdepi_2021(pd.Series([1.0]), pd.Series([30.0]), pd.Series([False]))
    old = egfr_ckdepi_2021(pd.Series([1.0]), pd.Series([80.0]), pd.Series([False]))
    assert young.iloc[0] > old.iloc[0]


def test_only_the_two_documented_cycles_are_corrected():
    """The correction is a per-cycle fact, and applying it to the wrong cycle is
    invisible: every value simply shifts, and the series stays plausible.

    CDC names 1999-2000 and 2005-2006 and states explicitly that 2001-2002 and
    2003-2004 need none. A map lookup that fell back to the first entry, or a
    `.fillna` on the wrong side, would correct everything.
    """
    d = pd.DataFrame({
        "cycle": ["1999-2000", "2001-2002", "2003-2004", "2005-2006", "2013-2014"],
        "creatinine": [1.0] * 5,
    })
    out = calibrate_creatinine(d)
    assert out.iloc[0] == pytest.approx(0.147 + 1.013)
    assert out.iloc[1] == 1.0
    assert out.iloc[2] == 1.0
    assert out.iloc[3] == pytest.approx(-0.016 + 0.978)
    assert out.iloc[4] == 1.0
    assert set(CREATININE_CALIBRATION) == {"1999-2000", "2005-2006"}


def test_the_two_corrections_move_in_opposite_directions():
    """Which is why the uncorrected series carries a step at the train/test
    boundary rather than a uniform offset. If someone ever 'simplifies' these to
    one shared equation, the artefact this module exists to remove comes back.
    """
    d = pd.DataFrame({"cycle": ["1999-2000", "2005-2006"], "creatinine": [1.0, 1.0]})
    out = calibrate_creatinine(d)
    assert out.iloc[0] > 1.0 and out.iloc[1] < 1.0


def test_uacr_is_mg_per_gram():
    """Urine albumin is ug/mL and urine creatinine mg/dL, so the ratio needs
    100x. A missing factor puts every value two orders of magnitude out, which
    still looks like a plausible column and silently moves the 30 mg/g
    albuminuria threshold to 3,000.
    """
    d = pd.DataFrame({
        "cycle": ["2013-2014"] * 2, "creatinine": [1.0, 1.0], "age": [50.0, 50.0],
        "sex": ["Male", "Male"], "systolic_bp": [120.0, 120.0],
        "diastolic_bp": [80.0, 80.0],
        "urine_albumin": [30.0, 300.0],       # ug/mL
        "urine_creatinine": [100.0, 100.0],   # mg/dL == 1 g/L
    })
    out = derive(d)
    assert out["uacr"].tolist() == pytest.approx([30.0, 300.0])


# ── the declarations ─────────────────────────────────────────────────────────

def test_every_variable_the_report_prints_has_a_declared_causal_status():
    assert_declared(list(P_FEATURES))


def test_an_undeclared_variable_raises_rather_than_defaulting_to_admissible():
    """The alternative is a page that prints "allowed" under a column headed
    "in the causal model?" for a variable nobody classified -- a false statement
    rather than a missing one.
    """
    with pytest.raises(KeyError, match="no declared e2 status"):
        assert_declared(["age", "some_new_biomarker"])


def test_the_three_states_are_all_actually_used():
    """Two states would have forced a guess on the variables the locked DAG does
    not settle, and the screen selected one of those. If `undetermined` ever
    disappears from the declarations, someone has quietly decided something.
    """
    used = {v[0] for v in STATUS.values()}
    assert {"admissible", "forbidden", "undetermined"} <= used


# ── the comparison ───────────────────────────────────────────────────────────

def _synthetic(n=1200, seed=5):
    rng = np.random.default_rng(seed)
    age = rng.uniform(40, 79, n)
    risk = 0.03 * (age - 40) + rng.normal(0, 1, n)
    return pd.DataFrame({
        "age": age,
        "sex": rng.choice(["Male", "Female"], n),
        "smoking": rng.choice(["never", "former", "current"], n),
        "race_black": rng.integers(0, 2, n).astype(float),
        "systolic_bp": rng.normal(128, 18, n),
        "diastolic_bp": rng.normal(76, 11, n),
        "bp_treated": rng.integers(0, 2, n).astype(float),
        "total_cholesterol": rng.normal(200, 38, n),
        "hdl_cholesterol": rng.normal(52, 14, n),
        "diabetes_dx": rng.integers(0, 2, n).astype(float),
        "bmi": rng.normal(28, 5, n),
        "wtmec2yr": rng.uniform(5000, 60000, n),
        "strata": rng.integers(1, 8, n),
        "psu": rng.integers(1, 3, n),
        "followup_years": rng.uniform(1, 20, n),
        # Both causes have to occur. `CauseSpecificRisk` fits TWO models, and a
        # competing-death column that is constantly zero makes the second one
        # singular -- which fails as a convergence error rather than as anything
        # resembling the thing under test.
        "cvd_death": (risk > np.quantile(risk, 0.88)).astype(int),
        "competing_death": ((risk <= np.quantile(risk, 0.88))
                           & (rng.random(n) < 0.12)).astype(int),
    })


def test_permutation_shuffles_in_the_model_frame_for_every_feature():
    """The defect this exists for: `male`, `smoke_current` and `smoke_former`
    are built inside `prepare()` from `sex` and `smoking`.

    Shuffling a raw frame and letting `prepare` run again rebuilds all three
    from untouched source columns, so their measured importance is exactly zero
    -- a plausible, publishable, wrong result for three of the eleven. This
    asserts that shuffling in the prepared frame moves the predictions for every
    feature, which is only possible if the model reads the shuffled column.
    """
    d = prepare(_synthetic())
    model = CauseSpecificRisk(list(P_FEATURES)).fit(d, prepared=True)
    base = model.predict_cif(d, 10.0, prepared=True)

    rng = np.random.default_rng(0)
    for f in P_FEATURES:
        shuffled = d.copy()
        col = shuffled[f].to_numpy(copy=True)
        rng.shuffle(col)
        shuffled[f] = col
        moved = model.predict_cif(shuffled, 10.0, prepared=True)
        assert not np.allclose(base.to_numpy(), moved.to_numpy()), (
            f"shuffling {f} changed nothing; it is probably being recomputed")


def test_predict_cif_without_prepared_still_rebuilds_the_derived_columns():
    """The other half of the same contract: `prepared=False` must remain the
    behaviour every existing caller relies on."""
    raw = _synthetic()
    model = CauseSpecificRisk(list(P_FEATURES)).fit(raw)
    assert model.predict_cif(raw, 10.0).notna().all()


def test_the_bootstrap_resamples_clusters_and_not_rows():
    """A row bootstrap on clustered data produces an interval that is too narrow,
    which is the same error the design-based intervals in Part 1 exist to avoid.
    Here the outcome is constant within cluster, so a cluster bootstrap must
    show far more spread than the rows alone would suggest.
    """
    n_clusters, per = 12, 40
    cluster = np.repeat(np.arange(n_clusters), per)
    rng = np.random.default_rng(3)
    shift = np.repeat(rng.normal(0, 3, n_clusters), per)
    d = pd.DataFrame({
        "design_cluster": [f"c{c}" for c in cluster],
        "followup_years": rng.uniform(1, 10, n_clusters * per),
        "cvd_death": rng.integers(0, 2, n_clusters * per),
        "wtmec2yr": rng.uniform(5_000, 60_000, n_clusters * per),
    })
    a = pd.Series(rng.normal(0, 1, len(d)) + shift, index=d.index)
    b = pd.Series(rng.normal(0, 1, len(d)), index=d.index)

    out = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=120, seed=1)
    assert out["n_boot"] > 0
    assert out["lo"] <= out["delta"] <= out["hi"]
    # 12 clusters resampled with replacement is a coarse thing; the interval has
    # to be wide enough to show it, or clusters are not what is being drawn.
    assert out["half_width"] > 0.01


def test_the_horizon_label_and_the_evaluable_mask_mean_what_they_say():
    """Both are one-liners and both are silently wrong in the same direction:
    counting a death after the horizon as an event, or scoring someone whose
    status at the horizon is unknown, inflates every discrimination statistic in
    the section.
    """
    d = pd.DataFrame({
        "followup_years": [5.0, 12.0, 3.0, 11.0],
        "cvd_death": [1, 1, 0, 0],
        "competing_death": [0, 0, 1, 0],
    })
    assert HorizonClassifier.label(d, 10.0).tolist() == [1, 0, 0, 0]
    assert HorizonClassifier.evaluable(d, 10.0).tolist() == [True, True, True, True]
    short = pd.DataFrame({"followup_years": [4.0], "cvd_death": [0],
                          "competing_death": [0]})
    assert HorizonClassifier.evaluable(short, 10.0).tolist() == [False]
