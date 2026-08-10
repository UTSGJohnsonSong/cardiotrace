"""Tests for the survival estimators.

The competing-risk identity is the important one: for any dataset,

    CIF_1(t) + CIF_2(t) == 1 - S_all-cause(t)

for every t. It is an algebraic consequence of the Aalen-Johansen construction,
so a violation means the estimator is wrong — not that the data are unusual. It
catches the classic mistake of building the CIF on the cause-specific KM instead
of the all-cause KM, which is exactly the bug that produces an inflated curve.

    python -m pytest tests/test_survival.py -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.survival import (  # noqa: E402
    aalen_johansen_cif, kaplan_meier, make_event_code, at_risk_counts,
)


def _toy():
    """Six subjects, hand-checkable. event: 0 censored, 1 cause of interest, 2 competing."""
    time = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    event = np.array([1, 2, 0, 1, 2, 0])
    return time, event


def test_km_matches_hand_calculation():
    time, event = _toy()
    km = kaplan_meier(time, event)
    # Cause 1 events at t=1 (n=6) and t=4 (n=3):
    #   S(1) = 1 - 1/6 = 5/6;  S(4) = 5/6 * (1 - 1/3) = 5/9
    got = km.set_index("t")["cum_inc"]
    assert got.loc[1.0] == pytest.approx(1 / 6)
    assert got.loc[4.0] == pytest.approx(1 - 5 / 9)


def test_at_risk_counts_down_by_one_each_step():
    time, event = _toy()
    km = kaplan_meier(time, event)
    assert list(km["at_risk"]) == [6, 5, 4, 3, 2, 1]


def test_cif_never_exceeds_naive_km():
    """1 - KM treats competing deaths as censoring, so it can only be >= the CIF."""
    time, event = _toy()
    naive = kaplan_meier(time, event).set_index("t")["cum_inc"]
    cif = aalen_johansen_cif(time, event).set_index("t")["cif"]
    assert (naive + 1e-12 >= cif).all()


@pytest.mark.parametrize("weighted", [False, True])
def test_competing_risk_identity_toy(weighted):
    time, event = _toy()
    w = np.array([2.0, 1.0, 3.0, 1.5, 0.5, 4.0]) if weighted else None
    c1 = aalen_johansen_cif(time, event, w, cause=1).set_index("t")["cif"]
    c2 = aalen_johansen_cif(time, event, w, cause=2).set_index("t")["cif"]
    any_event = np.where(event > 0, 1, 0)
    all_cause = kaplan_meier(time, any_event, w).set_index("t")["cum_inc"]
    assert np.allclose(c1 + c2, all_cause, atol=1e-12)


def test_competing_risk_identity_random():
    rng = np.random.default_rng(20260809)
    n = 3000
    time = rng.exponential(8.0, n).round(3)
    event = rng.choice([0, 1, 2], size=n, p=[0.55, 0.15, 0.30])
    w = rng.uniform(500, 50_000, n)
    c1 = aalen_johansen_cif(time, event, w, cause=1).set_index("t")["cif"]
    c2 = aalen_johansen_cif(time, event, w, cause=2).set_index("t")["cif"]
    all_cause = kaplan_meier(time, np.where(event > 0, 1, 0), w).set_index("t")["cum_inc"]
    assert np.allclose(c1 + c2, all_cause, atol=1e-10)


def test_cif_is_monotone_and_bounded():
    rng = np.random.default_rng(7)
    n = 2000
    time = rng.exponential(5.0, n)
    event = rng.choice([0, 1, 2], size=n, p=[0.5, 0.2, 0.3])
    cif = aalen_johansen_cif(time, event)["cif"].to_numpy()
    assert np.all(np.diff(cif) >= -1e-12), "CIF must be non-decreasing"
    assert cif.min() >= 0.0 and cif.max() <= 1.0


def test_weights_are_scale_invariant():
    """Multiplying every weight by a constant must not move the estimate."""
    time, event = _toy()
    w = np.array([2.0, 1.0, 3.0, 1.5, 0.5, 4.0])
    a = aalen_johansen_cif(time, event, w)["cif"].to_numpy()
    b = aalen_johansen_cif(time, event, w * 1000)["cif"].to_numpy()
    assert np.allclose(a, b)


def test_ties_are_handled_as_one_risk_set():
    """Two events at the same time share the risk set; they are not sequential."""
    time = np.array([1.0, 1.0, 2.0, 3.0])
    event = np.array([1, 1, 0, 1])
    km = kaplan_meier(time, event)
    # At t=1, 2 of 4 fail together: S = 1 - 2/4 = 0.5, not (1-1/4)(1-1/3).
    assert km.set_index("t")["cum_inc"].loc[1.0] == pytest.approx(0.5)


def test_make_event_code_maps_three_states():
    df = pd.DataFrame({"cvd_death": [1.0, 0.0, 0.0], "competing_death": [0.0, 1.0, 0.0]})
    assert list(make_event_code(df)) == [1, 2, 0]


def test_at_risk_counts_are_unweighted_and_grouped():
    df = pd.DataFrame({"followup_years": [1.0, 5.0, 9.0, 12.0],
                       "grp": ["a", "a", "b", "b"]})
    out = at_risk_counts(df, [0, 6], "grp")
    assert out.loc["a", "0"] == 2 and out.loc["a", "6"] == 0
    assert out.loc["b", "6"] == 2
