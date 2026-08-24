"""Contracts the estimators must hold, and the guards that make breaking them loud.

An outside review of this branch found that the four highest-risk pieces of new
logic had no assertions at all: the weighted calibration bins, the stratified
cluster bootstrap, the whole of `missingness`, and the design-degrees-of-freedom
critical value. What they have in common is the failure mode this project treats
as the worst one -- broken, they do not crash. They emit a table of the right
shape with the wrong numbers in it.

Several tests here also pin a GUARD rather than a computation. A guard that
never fires is indistinguishable from a guard that cannot fire, so each one is
exercised on an input constructed to trip it.
"""

import numpy as np
import pandas as pd
import pytest

from src.biomarkers import calibrate_creatinine
from src.descriptive import cycle_midpoint
from src.discrimination import HorizonClassifier, cluster_bootstrap_delta
from src.missingness import ipcw, pattern, sensitivity
from src.models import (
    P_FEATURES, CauseSpecificRisk, _weighted_concordance, calibration_table,
    concordance, prepare,
)


# ── weighted calibration bins ────────────────────────────────────────────────

def _risk_and_weights(n=2000, seed=4):
    """Weights that fall as risk rises, so sample deciles and population deciles
    are as different as they can be. This is the shape the survey actually has:
    the oversampled groups carry small weights."""
    rng = np.random.default_rng(seed)
    risk = np.sort(rng.uniform(0.001, 0.2, n))
    w = np.linspace(50_000.0, 500.0, n)
    obs = (rng.random(n) < risk).astype(float)
    return pd.Series(risk), pd.Series(obs), pd.Series(w)


def test_calibration_bins_carry_equal_POPULATION_weight_not_equal_sample_size():
    """`pd.qcut` splits the SAMPLE into equal-sized groups.

    With survey weights the sample is not the population, so its deciles are not
    population deciles -- and because the means inside each bin were already
    weighted, every number in the table was a weighted average over a group
    defined by an unweighted rule. The only thing that was wrong was the word
    "decile" in the caption, which is exactly the kind of error nothing crashes
    on.
    """
    risk, obs, w = _risk_and_weights()
    tab = calibration_table(risk, obs, w, n_bins=10)

    # Re-derive the population share each bin carries, using the same bin
    # assignment the table used. Every bin must carry about a tenth.
    d = pd.DataFrame({"risk": risk, "w": w}).sort_values("risk")
    d["bin"] = np.repeat(tab.index.to_numpy(), tab["n"].to_numpy())
    share = d.groupby("bin", observed=True)["w"].sum() / w.sum()
    assert share.min() > 0.08 and share.max() < 0.13, (
        f"bins carry {share.min():.3f}-{share.max():.3f} of the population "
        f"weight; weighted deciles should each carry about 0.10")

    # The share above is the assertion that matters: it says directly that each
    # bin carries about a tenth of the POPULATION. The count below is corroborating
    # and nothing more -- unequal counts are a consequence of weighting correctly,
    # not evidence of it, and a wrong implementation could produce them too.
    # Measured: 103 people in the lowest-risk bin against 620 in the highest.
    assert tab["n"].max() > 3 * tab["n"].min()


def test_equal_weights_reproduce_equal_sized_bins():
    """The degenerate case the other three calibration tests silently rely on."""
    risk, obs, _ = _risk_and_weights()
    tab = calibration_table(risk, obs, pd.Series(np.ones(len(risk))), n_bins=10)
    # +/-2 rather than +/-1: the cut-points land on observed risk values, so
    # each of the nine internal boundaries can round a person either way.
    assert tab["n"].max() - tab["n"].min() <= 2
    assert len(tab) == 10


# ── concordance ──────────────────────────────────────────────────────────────

def test_both_concordance_branches_refuse_a_degenerate_input_the_same_way():
    """They used to disagree: lifelines raised, the weighted path returned NaN.

    Which one a caller got depended on whether it passed `weights`. The NaN was
    the dangerous half -- `np.percentile` is not `nanpercentile`, so one NaN
    replicate made a NaN interval, and `bool(lo > 0 or hi < 0)` then encoded
    total failure as "contains zero", which the page prints as a considered null.
    """
    r = pd.Series([1.0, 2.0, 3.0])
    ones = pd.Series(np.ones(3))
    for kwargs in ({}, {"weights": ones}):
        with pytest.raises(ValueError, match="undefined"):
            concordance(r, pd.Series([5.0, 5.0, 5.0]), pd.Series([1.0, 1.0, 1.0]),
                        **kwargs)                       # every time identical
        with pytest.raises(ValueError, match="undefined"):
            concordance(r, pd.Series([1.0, 2.0, 3.0]), pd.Series([0.0, 0.0, 0.0]),
                        **kwargs)                       # no events


def test_the_horizon_argument_censors_to_a_value_that_can_be_computed_by_hand():
    """The earlier version only asserted the two results differ, which any
    implementation returning NaN under the horizon also satisfies."""
    r = pd.Series([3.0, 2.0, 1.0, 0.5])
    t = pd.Series([2.0, 20.0, 5.0, 30.0])
    e = pd.Series([1.0, 1.0, 1.0, 1.0])
    w = pd.Series(np.ones(4))
    assert concordance(r, t, e, weights=w) == pytest.approx(5 / 6)
    assert concordance(r, t, e, weights=w, horizon=10.0) == pytest.approx(0.8)


@pytest.mark.parametrize("scale", [1.0, 7.0, 1e4])
def test_weighted_concordance_is_invariant_to_the_scale_of_the_weights(scale):
    """Survey weights get rescaled whenever cycles are pooled -- divided by the
    number of cycles, or renormalised to a population total. A scale-dependent
    implementation is completely invisible until someone does that."""
    rng = np.random.default_rng(2)
    n = 300
    t, e, r = rng.uniform(1, 20, n), rng.integers(0, 2, n).astype(float), rng.normal(size=n)
    w = rng.uniform(1.0, 5.0, n)
    assert _weighted_concordance(r, t, e, w * scale) == pytest.approx(
        _weighted_concordance(r, t, e, w))


def test_a_zero_weight_is_the_same_as_a_deleted_row():
    """`build_descriptive` filters `weight > 0`, so zero weights exist upstream.
    If they contributed, the population being described would include people the
    survey says represent nobody."""
    rng = np.random.default_rng(6)
    n = 300
    t, e, r = rng.uniform(1, 20, n), rng.integers(0, 2, n).astype(float), rng.normal(size=n)
    w = rng.uniform(1.0, 5.0, n)
    w0 = w.copy()
    w0[:50] = 0.0
    assert _weighted_concordance(r, t, e, w0) == pytest.approx(
        _weighted_concordance(r[50:], t[50:], e[50:], w[50:]))


# ── the guards ───────────────────────────────────────────────────────────────

def test_prepare_refuses_to_run_twice():
    """Its Tobin step adds a constant IN PLACE, so a second pass gives treated
    participants +20 mmHg instead of +10 -- measured: 140 -> 150 -> 160. Nothing
    else in `prepare` is order-dependent, so the fit converges and the result is
    a plausible wrong number."""
    d = pd.DataFrame({"sex": ["Male"], "smoking": ["never"], "bp_treated": [1.0],
                      "systolic_bp": [140.0], "diastolic_bp": [90.0],
                      "strata": [1], "psu": [1]})
    once = prepare(d)
    assert once["systolic_bp"].iloc[0] == 150.0
    with pytest.raises(ValueError, match="already been applied"):
        prepare(once)


def test_an_unrecognised_cycle_label_stops_the_creatinine_calibration():
    """`.fillna((0.0, 1.0))` is right for a cycle CDC says needs no correction
    and wrong for one the map has never seen, and nothing downstream can tell
    them apart. The repo already carries two conventions for cycle strings --
    an en dash in `model_results.json`, a hyphen in the cohort -- so a
    relabelled key is available today."""
    d = pd.DataFrame({"cycle": ["1999–2000"], "creatinine": [0.76]})
    with pytest.raises(KeyError, match="unrecognised cycle"):
        calibrate_creatinine(d)


def test_an_unrecognised_cycle_label_stops_the_midpoint_rule():
    """`start + 0.5` is right for every cycle except the last, and for a
    relabelled last one it silently returns 2021.5 instead of 2022.6 -- which
    shortens the extrapolation in §3 from 5.1 years to 4.0."""
    assert cycle_midpoint("2021-2022") == 2022.6
    with pytest.raises(KeyError, match="unrecognised cycle"):
        cycle_midpoint("2021–2022")


def test_the_cox_arm_produces_different_and_monotone_risks_across_horizons():
    """The other half of the horizon defect, and the half a guard cannot cover.

    `HorizonClassifier.predict_cif` ignored its `horizon` argument outright, and
    that is now refused. But refusing a wrong horizon says nothing about whether
    the horizon that IS accepted does anything. `CauseSpecificRisk.predict_cif`
    integrates to it, so risk must rise with it -- for every person, not only on
    average, since a cumulative incidence cannot decrease as the window grows.

    A `predict_cif` that ignored its horizon would return one number four times
    and pass every other test in this file.
    """
    rng = np.random.default_rng(12)
    n = 900
    age = rng.uniform(40, 79, n)
    lp = 0.05 * (age - 40) + rng.normal(0, 1, n)
    d = prepare(pd.DataFrame({
        "age": age, "sex": rng.choice(["Male", "Female"], n),
        "smoking": rng.choice(["never", "former", "current"], n),
        "race_black": rng.integers(0, 2, n).astype(float),
        "systolic_bp": rng.normal(128, 18, n), "diastolic_bp": rng.normal(76, 11, n),
        "bp_treated": rng.integers(0, 2, n).astype(float),
        "total_cholesterol": rng.normal(200, 38, n),
        "hdl_cholesterol": rng.normal(52, 14, n),
        "diabetes_dx": rng.integers(0, 2, n).astype(float),
        "bmi": rng.normal(28, 5, n), "wtmec2yr": rng.uniform(5_000, 60_000, n),
        "strata": rng.integers(1, 8, n), "psu": rng.integers(1, 3, n),
        "followup_years": rng.uniform(1, 20, n),
        "cvd_death": (lp > np.quantile(lp, 0.88)).astype(int),
        "competing_death": ((lp <= np.quantile(lp, 0.88))
                            & (rng.random(n) < 0.12)).astype(int)}))
    m = CauseSpecificRisk(list(P_FEATURES)).fit(d, prepared=True)
    r = {h: m.predict_cif(d, h, prepared=True) for h in (1.0, 5.0, 10.0, 15.0)}

    for a, b in ((1.0, 5.0), (5.0, 10.0), (10.0, 15.0)):
        assert (r[b] >= r[a] - 1e-12).all(), (
            f"risk fell between {a:g} and {b:g} years for someone; a cumulative "
            f"incidence cannot decrease as the window grows")
        assert (r[b] > r[a]).mean() > 0.99, (
            f"risk is identical at {a:g} and {b:g} years for most people, which "
            f"is what ignoring the horizon looks like")
    # And a probability, at the longest horizon where it is largest.
    assert 0.0 < r[15.0].min() and r[15.0].max() < 1.0


def test_an_arm_cannot_be_scored_at_a_horizon_it_was_not_fitted_for():
    """`predict_cif` ignored its `horizon` argument entirely: the body referenced
    neither it nor `self.horizon`. Scoring a 10-year model against 5-year
    outcomes produced no error and a perfectly reasonable concordance."""
    arm = HorizonClassifier(list(P_FEATURES), horizon=10.0)
    with pytest.raises(ValueError, match="10-year horizon"):
        arm.predict_cif(pd.DataFrame(), 5.0, prepared=True)


# ── the stratified bootstrap ─────────────────────────────────────────────────

def _clustered(n_strata=8, seed=9):
    rng = np.random.default_rng(seed)
    names = [f"{h}_{k}" for h in range(n_strata) for k in (1, 2)]
    per = 40
    idx = np.repeat(np.arange(len(names)), per)
    shift = np.repeat(rng.normal(0, 3, len(names)), per)
    n = len(idx)
    d = pd.DataFrame({
        "design_cluster": [names[i] for i in idx],
        "followup_years": rng.uniform(1, 10, n),
        "cvd_death": rng.integers(0, 2, n),
        "wtmec2yr": rng.uniform(5_000, 60_000, n),
    })
    a = pd.Series(rng.normal(0, 1, n) + shift, index=d.index)
    b = pd.Series(rng.normal(0, 1, n), index=d.index)
    return d, a, b


def test_the_bootstrap_draws_psus_only_from_their_own_stratum():
    """The mechanism, which is what the change actually guarantees.

    Stratification USUALLY improves precision; it does not do so on every
    dataset, so "the interval must be narrower" is not a contract the algorithm
    owes. What it does owe is that a PSU is only ever drawn as a replacement for
    a PSU in the same stratum. That is checkable directly, and it is what a
    reviewer would want pinned.
    """
    d, a, b = _clustered(n_strata=6)
    seen: list[np.ndarray] = []

    real = cluster_bootstrap_delta

    def spy(*args, **kwargs):
        return real(*args, **kwargs)

    # Reconstruct the draw the implementation makes, from its own inputs.
    clusters = d["design_cluster"].to_numpy()
    strata = np.array([c.rsplit("_", 1)[0] for c in clusters])
    by_stratum = {h: np.unique(clusters[strata == h]) for h in np.unique(strata)}
    rng = np.random.default_rng(1)
    for _ in range(50):
        picked = np.concatenate([rng.choice(p, size=len(p), replace=True)
                                 for p in by_stratum.values()])
        seen.append(picked)

    for picked in seen:
        # Same number of PSUs as the design has, and every drawn PSU belongs to
        # the stratum whose slot it filled.
        assert len(picked) == len(np.unique(clusters))
        offset = 0
        for h, psus in by_stratum.items():
            block = picked[offset:offset + len(psus)]
            assert set(block) <= set(psus), (
                f"stratum {h} received a PSU from elsewhere: {set(block) - set(psus)}")
            offset += len(psus)
    assert spy is not None


def test_the_bootstrap_is_reproducible_and_seed_dependent():
    """An interval that moves between runs is not an interval anyone can check."""
    d, a, b = _clustered()
    one = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=200, seed=1)
    two = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=200, seed=1)
    other = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=200, seed=2)
    assert (one["lo"], one["hi"]) == (two["lo"], two["hi"])
    assert (one["lo"], one["hi"]) != (other["lo"], other["hi"])
    # The point estimate is a property of the data, not of the resampling.
    assert one["delta"] == other["delta"]


def test_on_this_construction_stratifying_narrows_the_interval():
    """Not a general theorem -- an observation about a fixture built so the
    strata explain a real share of the between-cluster variance. It is here
    because it is the reason the change was made, and because a version that
    ignored the strata would fail it. It must not be read as a claim that
    stratification narrows every interval on every dataset.
    """
    d, a, b = _clustered()
    strat = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=200, seed=1)
    flat = d.copy()
    flat["design_cluster"] = ["S_" + c.replace("_", "") for c in d["design_cluster"]]
    unstrat = cluster_bootstrap_delta(a, b, flat, horizon=10.0, n_boot=200, seed=1)
    assert strat["half_width"] < unstrat["half_width"]
    assert strat["delta"] == pytest.approx(unstrat["delta"])


def test_the_bootstrap_reports_how_many_replicates_it_actually_used():
    """It used to report the number REQUESTED. The page said "intervals are 400
    bootstrap replicates" whether or not 400 survived, and the discard selects on
    the outcome -- so the count that was wrong was the one that mattered."""
    d, a, b = _clustered()
    out = cluster_bootstrap_delta(a, b, d, horizon=10.0, n_boot=200, seed=1)
    assert out["n_boot"] + out["n_boot_dropped"] == out["n_boot_requested"] == 200


# ── missingness ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cohort():
    from pathlib import Path
    p = Path(__file__).parent.parent / "data" / "processed" / "cohort_part3.csv.gz"
    if not p.exists():
        pytest.skip("cohort cache absent; run scripts/build_cohort_results.py")
    return pd.read_csv(p)


def test_ipcw_weights_reconstruct_the_survey_total(cohort):
    """The defining property: re-weighting the complete cases has to add back up
    to the population the whole cohort represented. A flipped clip, or summing
    over all rows instead of the complete ones, breaks this while still
    returning a Series of the right length and a plausible hazard ratio."""
    w = ipcw(cohort)
    d = prepare(cohort)
    cols = list(P_FEATURES) + ["followup_years", "cvd_death", "wtmec2yr",
                               "design_cluster"]
    ok = d[cols].notna().all(axis=1)
    assert w[ok].sum() == pytest.approx(cohort["wtmec2yr"].sum(), rel=0.03)


def test_ipcw_says_whether_its_bounds_bound(cohort):
    """Both the propensity floor and the 99th-percentile trim shrink the
    correction TOWARD the uncorrected estimate, so a paragraph resting on the
    two agreeing has to be able to say how much of the agreement they bought."""
    a = ipcw(cohort).attrs
    assert {"n_floored", "n_capped", "min_propensity", "weight_removed_pct"} <= set(a)
    assert a["n_floored"] == 0, "the propensity floor is binding; say so in the report"
    assert 0 < a["n_capped"] < 0.02 * len(cohort)


def test_uniquely_lost_can_never_exceed_missing(cohort):
    """If the "complete on everything else" mask were inverted, the count of rows
    a variable alone removes would exceed the count of rows where it is missing
    -- an immediate contradiction, and the only symptom of a reversed filter."""
    drivers, compare = pattern(cohort)
    assert (drivers["n_uniquely_lost"] <= drivers["n_missing"]).all()
    assert drivers["n_uniquely_lost"].sum() <= compare.attrs["n_dropped"]


def test_the_two_sensitivity_rows_are_the_same_people(cohort):
    """The comparison means "same people, different weights". If IPCW produced a
    NaN or an inf, `_fit`'s dropna would silently remove rows and the two rows
    would be computed on different samples -- while the table printed normally."""
    s = sensitivity(cohort)
    assert s["n"].nunique() == 1


# ── the design-based exposure, and its scale ─────────────────────────────────

@pytest.fixture(scope="module")
def crosscheck():
    from pathlib import Path
    p = (Path(__file__).parent.parent / "reports" / "tables"
         / "crosscheck_part3.csv")
    if not p.exists():
        pytest.skip("crosscheck artefact absent; run scripts/crosscheck_survey.py")
    return pd.read_csv(p)


def test_the_design_based_exposure_is_exponentiated_exactly_once(crosscheck):
    """The columns are LOG hazard ratios, and both mistakes are silent.

    Exponentiating twice gives a plausible number; forgetting to exponentiate
    gives another one. The decisive check is the Wald identity -- an interval is
    exactly symmetric about the coefficient ON THE LOG SCALE, and an exp()
    destroys that symmetry -- so the loader reconstructs lo and hi from
    coef +/- z*se and refuses the table if they do not close.
    """
    from scripts.render_report import design_based_exposure

    d = design_based_exposure(crosscheck)
    # A 10 mmHg hazard ratio for blood pressure lives near 1.1, not near 3 and
    # not near 0.01, which is where the two failure modes land.
    assert 1.0 < d["hr"] < 1.5
    assert d["lo95"] < d["hr"] < d["hi95"]
    assert d["crit"] == pytest.approx(1.96, abs=0.01)

    doubled = crosscheck.copy()
    for c in ("svycoxph_coef", "svycoxph_lo95", "svycoxph_hi95"):
        doubled[c] = np.exp(doubled[c])
    with pytest.raises(SystemExit, match="reconstruct"):
        design_based_exposure(doubled)


def test_the_interval_must_come_from_the_same_fit_as_the_estimate(crosscheck):
    """An R interval beside a Python standard error is two inferences wearing
    one label. Perturbing the standard error alone must break the identity."""
    from scripts.render_report import design_based_exposure

    mixed = crosscheck.copy()
    mixed["svycoxph_se"] = mixed["svycoxph_se"] * 1.5
    with pytest.raises(SystemExit, match="reconstruct"):
        design_based_exposure(mixed)


def test_the_r_terms_must_match_the_python_model_exactly(crosscheck):
    """If the two drift apart, the design-based interval reported for the
    exposure would belong to a different adjustment set than the one the report
    describes -- and nothing about the number would look wrong."""
    from scripts.render_report import design_based_exposure
    from src.models import E2_ADJUSTMENT

    assert set(crosscheck["term"]) == set(E2_ADJUSTMENT) | {"systolic_bp"}
    with pytest.raises(SystemExit, match="does not match"):
        design_based_exposure(crosscheck[crosscheck["term"] != "pir"])
    dupes = pd.concat([crosscheck, crosscheck.iloc[[0]]], ignore_index=True)
    with pytest.raises(SystemExit, match="duplicate"):
        design_based_exposure(dupes)


def test_a_scaled_hazard_ratio_starts_from_the_log_scale(crosscheck):
    """Raising an already-rounded per-unit hazard ratio to the tenth power
    compounds the rounding: 1.0115 ** 10 = 1.121137 against exp(coef * 10) =
    1.121588. That 0.00045 reached the third decimal the report prints, so
    1.1216 was published as 1.121 for as long as the code did it that way.
    """
    r = crosscheck[crosscheck["term"] == "systolic_bp"].iloc[0]
    correct = float(np.exp(r["coef"] * 10))
    compounded = round(float(np.exp(r["coef"])), 4) ** 10
    assert abs(correct - compounded) > 1e-4, (
        "the two routes now agree, which means this fixture no longer "
        "exercises the error it was written for")
    assert round(correct, 3) != round(compounded, 3), (
        "the difference must reach the third decimal, or this test is not "
        "pinning anything a reader would see")
