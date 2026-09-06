"""Independent published examples and analysis-contract regressions."""
import numpy as np
import pandas as pd
import pytest

from src.pce import score, coefficients, decision_curve, MortalityRecalibration


@pytest.fixture
def profiles():
    return pd.DataFrame({"age": [55]*4, "sex": ["Female", "Female", "Male", "Male"],
        "race_eth": ["NH White", "NH Black"]*2, "race_black": [0, 1]*2,
        "total_cholesterol": [213]*4, "hdl_cholesterol": [50]*4,
        "systolic_bp": [120]*4, "bp_treated": [0]*4,
        "diabetes_dx": [0]*4, "current_smoker": [0]*4})


def test_production_score_reproduces_four_published_examples(profiles):
    result = score(profiles)
    np.testing.assert_allclose(result.lp, [-29.67, 86.16, 60.69, 18.97], atol=.02)
    # Printed sums are rounded before the source's worked risk calculation;
    # the unrounded LP here gives 5.384% for white men. The separate reference
    # tests check baseline parameters against the printed sums at tighter tolerance.
    np.testing.assert_allclose(result.risk_10y_ascvd * 100, [2.1, 3., 5.3, 6.1], atol=.10)


def test_scoring_does_not_mutate_observed_pressure(profiles):
    profiles.bp_treated = 1
    original = profiles.copy(deep=True)
    score(profiles)
    pd.testing.assert_frame_equal(profiles, original)
    with pytest.raises(ValueError, match="raw measured"):
        score(profiles.assign(design_cluster="1_1"))


@pytest.mark.parametrize("column,value", [("age", 39), ("sex", "unknown"),
    ("race_eth", "unknown"), ("systolic_bp", 0), ("hdl_cholesterol", np.nan),
    ("bp_treated", 7), ("race_black", 1)])
def test_unknown_and_invalid_inputs_fail_loudly(profiles, column, value):
    profiles.loc[0, column] = value
    with pytest.raises(ValueError):
        score(profiles)


def test_other_ethnicity_mapping_is_explicit(profiles):
    profiles.loc[0, "race_eth"] = "Mexican American"
    with pytest.raises(ValueError, match="Primary"):
        score(profiles)
    assert score(profiles, other_ethnicities=True).group.iloc[0] == "white_women"


def test_reference_loader_rejects_missing_coefficient(tmp_path):
    from src.pce import REFERENCE
    table = pd.read_csv(REFERENCE)
    path = tmp_path / "broken.csv"
    table.iloc[1:].to_csv(path, index=False)
    with pytest.raises(ValueError, match="60 unique"):
        coefficients(path)


def test_decision_curve_uses_competing_death_as_noncase_and_weights():
    d = pd.DataFrame({"followup_years": [1., 2., 12.], "cvd_death": [1, 0, 0],
                      "competing_death": [0, 1, 0], "wtmec2yr": [2., 1., 1.]})
    tab = decision_curve({"model": pd.Series([.8, .7, .1])}, d, 10, [.5]).set_index("arm")
    assert tab.loc["model", "net_benefit"] == pytest.approx(.25)
    assert tab.loc["treat_all", "net_benefit"] == pytest.approx(0.)
    assert tab.loc["treat_none", "net_benefit"] == 0
    d.loc[1, "competing_death"] = 0
    with pytest.raises(ValueError, match="Early censoring"):
        decision_curve({}, d, 10)
    adjusted = decision_curve({}, d, 10, [.5], censoring="aalen_johansen").set_index("arm")
    # Weight 2/4 dies first, then censoring leaves survival unchanged: CIF=.5.
    assert adjusted.loc["treat_all", "net_benefit"] == pytest.approx(0.)
    assert adjusted.loc["treat_all", "early_censored"] == 1


def test_fixed_offset_baseline_has_hand_calculable_risk(profiles):
    d = pd.concat([profiles, profiles], ignore_index=True)
    d["followup_years"] = [1.]*4 + [2.]*4
    d["cvd_death"] = [1]*4 + [0]*4
    d["competing_death"] = [0]*4 + [1]*4
    d["wtmec2yr"] = 1.
    scores = score(d)
    fit = MortalityRecalibration().fit(d, scores)
    # Two identical-risk persons in each stratum; one CVD event at t=1.
    np.testing.assert_allclose(fit.predict(scores, .5), 0)
    np.testing.assert_allclose(fit.predict(scores, 1), .5)
    np.testing.assert_allclose(fit.predict(scores, 3), .5)
    doubled = MortalityRecalibration().fit(d.assign(wtmec2yr=2.), scores)
    pd.testing.assert_series_equal(fit.predict(scores, 3), doubled.predict(scores, 3))


def test_selection_propensity_targets_the_covariates_actually_fitted(monkeypatch):
    from src import missingness
    from src.models import aetiologic_covariates
    seen = []
    monkeypatch.setattr(missingness, "_model_frame", lambda _: pd.DataFrame())
    def capture(cohort, features, **kwargs):
        seen.append(features)
        raise RuntimeError("captured before fitting")
    monkeypatch.setattr(missingness, "ipcw", capture)
    with pytest.raises(RuntimeError, match="captured"):
        missingness.sensitivity(pd.DataFrame())
    assert seen == [aetiologic_covariates()]


@pytest.mark.parametrize("value", ["", "NA", "inf"])
def test_active_coefficient_cannot_silently_become_zero(tmp_path, value):
    from src.pce import REFERENCE
    table = pd.read_csv(REFERENCE, keep_default_na=False)
    table.loc[0, "value"] = value
    path = tmp_path / "broken.csv"
    table.to_csv(path, index=False)
    with pytest.raises(ValueError):
        coefficients(path)


def test_aj_curve_accounts_for_censoring_before_an_event():
    # Equal weights: one censor first, then one CVD death among the three at
    # risk, then a competing death. CIF=1/3, not the binary 1/4.
    d = pd.DataFrame({"followup_years": [1., 2., 3., 12.],
        "cvd_death": [0, 1, 0, 0], "competing_death": [0, 0, 1, 0], "wtmec2yr": 1.})
    tab = decision_curve({}, d, 10, [.5], censoring="aalen_johansen").set_index("arm")
    assert tab.loc["treat_all", "net_benefit"] == pytest.approx(-1/3)
    assert tab.loc["treat_none", "net_benefit"] == 0


@pytest.mark.parametrize("field,value", [("cvd_death", 7), ("competing_death", 1),
    ("followup_years", -1), ("wtmec2yr", 0), ("wtmec2yr", np.nan)])
def test_invalid_outcome_design_inputs_are_rejected(field, value):
    d = pd.DataFrame({"followup_years": [1.], "cvd_death": [1],
                      "competing_death": [0], "wtmec2yr": [1.]})
    d.loc[0, field] = value
    with pytest.raises(ValueError):
        decision_curve({}, d, 10)


@pytest.mark.parametrize("horizon", [0, -1, np.inf, np.nan])
def test_invalid_horizon_is_rejected(horizon):
    d = pd.DataFrame({"followup_years": [1.], "cvd_death": [1],
                      "competing_death": [0], "wtmec2yr": [1.]})
    with pytest.raises(ValueError, match="Horizon"):
        decision_curve({}, d, horizon)
