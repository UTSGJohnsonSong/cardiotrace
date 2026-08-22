"""Regressions for the weighted joinpoint test.

The module only ever reports a null on the real series, so nothing here is
protected by the analysis itself. A null is informative only if the procedure
could have said otherwise, which is why the first test is a positive control: a
sign error in the hinge basis, a reversed subtraction in the statistic, or a
grid search that silently returned its first candidate would all leave "no break
found" looking exactly the same while making it unfalsifiable.
"""

import numpy as np
import pytest

from src.changepoint import (
    MIN_POINTS_PER_SEGMENT, _design, _wls, bootstrap_test, candidate_knots,
    fit_joinpoint, fit_line, power_curve, profile_set,
)

# The real cycle geometry: biennial, with the four-year hole where NHANES
# fielded no cycle. Tests use it so they exercise the spacing the estimator
# actually meets.
YEARS = np.array([1999.5, 2001.5, 2003.5, 2005.5, 2007.5, 2009.5,
                  2011.5, 2013.5, 2015.5, 2017.5, 2021.5])
SE = np.full(len(YEARS), 0.004)


def test_a_break_that_is_really_there_is_found_where_it_is():
    """Positive control. Everything else in this module reports nulls.

    The break is deliberately unmissable: a slope change of 0.004 per year on a
    series whose points carry a standard error of 0.004. If this stops being
    detected, the procedure cannot find anything, and every null it reports is
    vacuous rather than informative.
    """
    truth = (0.09 - 0.0005 * (YEARS - YEARS.mean())
             + 0.004 * np.clip(YEARS - 2009.5, 0.0, None))
    y = truth + np.random.default_rng(42).normal(0.0, SE)

    boot = bootstrap_test(YEARS, y, SE, n_boot=300, seed=11)

    assert boot["tau"] == 2009.5
    assert boot["observed"] > boot["crit95"]
    assert boot["p"] < 0.01
    # The profile must be informative, not flat: the true knot has to beat the
    # ends, or "best knot" is an argmin over noise.
    by_tau = dict(boot["profile"])
    assert by_tau[2009.5] < by_tau[2003.5]
    assert by_tau[2009.5] < by_tau[2013.5]


def test_a_straight_line_is_not_reported_as_a_break():
    """Negative control on the same machinery, so the pair brackets the test."""
    y = (0.09 - 0.0005 * (YEARS - YEARS.mean())
         + np.random.default_rng(1).normal(0.0, SE))
    boot = bootstrap_test(YEARS, y, SE, n_boot=300, seed=7)
    assert boot["observed"] < boot["crit95"]
    assert boot["p"] > 0.10


def test_precision_weights_actually_move_the_fit():
    """The whole reason this module exists instead of an off-the-shelf segmenter
    is that it uses the design-based standard errors. A `_wls` that ignored its
    weights would still reduce to OLS when the weights are equal, so an
    equal-weight check cannot detect it. This pair can.
    """
    X = np.column_stack([np.ones(6), np.arange(6.0)])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 20.0])          # last point an outlier
    equal, _ = _wls(X, y, np.ones(6))
    scaled, _ = _wls(X, y, np.full(6, 7.0))
    trusted, _ = _wls(X, y, np.array([1., 1., 1., 1., 1., 100.]))
    distrusted, _ = _wls(X, y, np.array([1., 1., 1., 1., 1., 0.01]))

    assert np.allclose(equal, scaled)                       # scale invariance
    assert trusted[1] > equal[1] > distrusted[1]            # relative precision bites
    assert distrusted[1] == pytest.approx(1.0, abs=0.05)    # the clean line's slope


def test_the_joinpoint_can_never_fit_worse_than_the_line_it_contains():
    """The straight line is the joinpoint with the hinge coefficient at zero, so
    the improvement statistic is non-negative for every knot by construction.

    This is the cheapest possible check on `_wls`: a solve that drops the weight
    matrix, or a weighted RSS that forgets to weight, breaks it while leaving the
    p-value inside [0, 1] and the figure perfectly drawable.
    """
    y = 0.09 - 0.0005 * (YEARS - YEARS.mean())
    line = fit_line(YEARS, y, SE)
    jp = fit_joinpoint(YEARS, y, SE)
    assert jp["wrss"] <= line["wrss"] + 1e-12
    for tau, wrss in jp["profile"]:
        assert wrss <= line["wrss"] + 1e-12, f"knot {tau} fits worse than no knot"


def test_the_hinge_basis_is_continuous_at_the_knot():
    """Continuity is a modelling claim, not an implementation detail: a national
    prevalence has no mechanism for an instantaneous jump, and the continuous
    form costs one fewer parameter. A step basis would fit better, report a
    smaller p, and raise nothing.
    """
    x = np.array([0., 1., 2., 3., 4., 5.])
    D = _design(x, 2.0)
    assert D.shape == (6, 3)
    assert np.allclose(D[:, 0], 1.0) and np.allclose(D[:, 1], x)
    assert np.allclose(D[:3, 2], 0.0)                       # zero at and before
    assert np.allclose(D[3:, 2], [1., 2., 3.])              # slope 1 after, no jump
    assert _design(np.array([1.0, 2.0]), 1.5)[:, 2].tolist() == [0.0, 0.5]
    assert _design(x, None).shape == (6, 2)


@pytest.mark.parametrize("n,expected", [
    (5, []), (6, [2]), (7, [2, 3]), (11, [2, 3, 4, 5, 6, 7]),
])
def test_candidate_knots_leave_a_supportable_segment_strictly_on_both_sides(n, expected):
    """The knot belongs to the left segment, so the right segment is the points
    strictly after it. An earlier version counted the knot on the right and
    admitted a candidate with only two points after it -- which then won the
    search, because a two-point segment fits with zero residual degrees of
    freedom and therefore always has the lowest available weighted RSS. The
    reported best knot was an artefact of the rule not being enforced.
    """
    x = np.arange(float(n))
    assert candidate_knots(x).tolist() == [float(i) for i in expected]


def test_every_returned_knot_leaves_the_documented_minimum_on_both_sides():
    """Holds even when a caller supplies its own grid, which bypasses
    `candidate_knots` entirely."""
    y = 0.09 - 0.0005 * (YEARS - YEARS.mean())
    jp = fit_joinpoint(YEARS, y, SE, knots=YEARS)          # deliberately too wide
    for tau, _ in jp["profile"]:
        assert (YEARS > tau).sum() >= MIN_POINTS_PER_SEGMENT
        assert (YEARS <= tau).sum() >= MIN_POINTS_PER_SEGMENT


def test_a_series_too_short_to_carry_a_knot_raises_rather_than_inventing_one():
    with pytest.raises(RuntimeError, match="no admissible knot"):
        fit_joinpoint(np.arange(4.0), np.array([1., 2., 4., 3.]), np.ones(4))


def test_bootstrap_p_is_never_exactly_zero():
    """A Monte Carlo p-value of zero asserts an impossibility a finite simulation
    cannot establish. The floor is 1 / (n_boot + 1); the bare proportion prints
    0.00 on exactly the series where the number matters most.
    """
    y = 0.09 + 0.01 * np.clip(YEARS - 2009.5, 0.0, None)   # unmissable break
    boot = bootstrap_test(YEARS, y, SE, n_boot=200, seed=3)
    assert boot["p"] > 0.0
    assert boot["p"] >= 1.0 / (boot["n_boot"] + 1)


def test_bootstrap_is_reproducible_and_serialisable():
    """The result has to be written once and read by both the figure and the
    report. When it was not, three different critical values were in circulation
    because each consumer re-ran the bootstrap with its own replicate count.
    """
    import json

    y = 0.09 - 0.0005 * (YEARS - YEARS.mean())
    a = bootstrap_test(YEARS, y, SE, n_boot=200, seed=7)
    b = bootstrap_test(YEARS, y, SE, n_boot=200, seed=7)
    assert (a["p"], a["crit95"], a["tau"]) == (b["p"], b["crit95"], b["tau"])
    assert bootstrap_test(YEARS, y, SE, n_boot=200, seed=8)["crit95"] != a["crit95"]
    assert 0.0 <= a["p"] <= 1.0
    # Numerically zero on a perfectly straight line, and floating point can
    # put it a hair below.
    assert a["observed"] >= -1e-12
    json.dumps(a)                                           # must not raise


def test_the_critical_value_depends_on_the_design_not_on_the_data():
    """`power_curve` feeds a flat dummy series into `bootstrap_test` and keeps
    only the critical value. That is sound -- the statistic is invariant to
    adding any linear function of x, so the null depends on x, se and the seed
    alone -- but it reads like an oversight and will be "fixed".
    """
    flat = bootstrap_test(YEARS, np.zeros_like(YEARS) + 0.09, SE, n_boot=200, seed=5)
    tilted = bootstrap_test(YEARS, 0.05 + 0.002 * YEARS, SE, n_boot=200, seed=5)
    assert flat["crit95"] == pytest.approx(tilted["crit95"])


def test_power_rises_with_the_size_of_the_break():
    curve = power_curve(YEARS, SE, 2011.5, [0.0, 0.001, 0.0025],
                        n_sim=120, n_boot=120)
    powers = [r["power"] for r in curve]
    assert powers[0] < 0.20                                 # no break -> ~alpha
    assert powers[0] < powers[1] < powers[2]
    assert curve[-1]["slope_change_per_decade_pp"] == pytest.approx(2.5)


def test_the_profile_set_is_read_from_one_persisted_result():
    """`profile_set` takes the bootstrap result alone. It used to take the
    joinpoint fit as well, which let a caller pair a threshold from one run with
    a profile from another."""
    y = 0.09 - 0.0005 * (YEARS - YEARS.mean())
    boot = bootstrap_test(YEARS, y, SE, n_boot=200, seed=13)
    pset = profile_set(boot)
    assert set(pset) <= set(boot["grid"])
    assert boot["tau"] in pset                              # the best knot is in its own set
