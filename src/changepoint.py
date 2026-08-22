"""Weighted joinpoint regression: does the trend break, and where?

WHY THIS EXISTS
---------------
The Part 2 counterfactual assumes the break, if any, is at the pandemic. This
module lets the data nominate a breakpoint instead -- but only within the
window the series can actually support.

WHAT THIS TEST DOES NOT ADDRESS
-------------------------------
With eleven points and three required per segment, the last admissible knot
is eight years before the pandemic. Simulated power against a true break AT
the pandemic is 0.057 at a slope change of 1 pp per decade -- indistinguishable
from the test's own size. So a null here is a statement about breaks inside
the pre-pandemic series, and carries no information at all about a pandemic
break. Reporting it as a check on the pandemic framing would be reporting a
test that could not have failed.

THE MODEL
---------
Continuous piecewise linear, one knot:

    y = b0 + b1 * x + b2 * (x - tau)+ ,      Var(e_i) = sigma_i^2  known

Continuity is the right constraint: a national prevalence has no mechanism for
an instantaneous jump, and it costs one fewer parameter than a discontinuous
break.

WHY THE STANDARD TOOLS ARE WRONG HERE
-------------------------------------
`ruptures` (PELT, binary segmentation), CUSUM and Bai-Perron all solve a
different problem: breaks in a long, densely sampled, equally weighted signal.
This series is eleven precision-weighted summary statistics, unequally spaced,
with a four-year hole where NHANES fielded no cycle. Those tools take an
index-ordered array, so they would read the hole as one more biennial step, and
they have no per-observation variance argument, so they would treat the 2003
estimate (se 0.73 pp) as exactly as reliable as the 2011 one (se 0.33 pp). The
design-based standard errors are the most valuable thing NHANES gives us and a
signal segmenter throws them away.

WHY THE DISPERSION FLOOR IS OFF HERE
------------------------------------
`scripts.build_descriptive_results.wls_trend` floors the dispersion at 1 so an
interval is never narrower than nominal. That is the right conservatism for
reporting an interval, but it is wrong for this test: with sigma_i known, the
weighted residual sum of squares is an exact chi-square goodness-of-fit
statistic, and that is a stronger instrument than an estimated dispersion.
Fitting here therefore uses the raw known-variance calibration.

THE DAVIES PROBLEM
------------------
tau does not exist under the null of no break, so the usual asymptotics do not
apply and a chi-square or F test evaluated at the fitted tau-hat is
anticonservative -- searching over tau inflates the null by roughly half again.
Significance is therefore assessed by parametric bootstrap of the supremum
statistic, simulating under the fitted straight line with the known sigma_i and
repeating the full grid search on every replicate.
"""

from __future__ import annotations

import numpy as np

# Segments shorter than this cannot support a slope.
MIN_POINTS_PER_SEGMENT = 3


def _wls(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, float]:
    """Weighted least squares. Returns coefficients and weighted RSS."""
    W = np.diag(w)
    beta = np.linalg.solve(X.T @ W @ X, X.T @ W @ y)
    resid = y - X @ beta
    return beta, float((w * resid ** 2).sum())


def _design(x: np.ndarray, tau: float | None) -> np.ndarray:
    cols = [np.ones_like(x), x]
    if tau is not None:
        cols.append(np.clip(x - tau, 0.0, None))
    return np.column_stack(cols)


def candidate_knots(x: np.ndarray) -> np.ndarray:
    """Observed interior points that leave enough data STRICTLY on both sides.

    The knot belongs to the left segment, so the right segment is the points
    strictly greater than tau. An earlier version counted the knot on the right
    and admitted a candidate with only two points after it -- which then won the
    search, because a two-point segment fits with zero residual degrees of
    freedom and therefore always has the lowest weighted RSS available. The
    reported best knot was an artefact of the rule not being enforced.
    """
    lo = MIN_POINTS_PER_SEGMENT - 1
    hi = len(x) - MIN_POINTS_PER_SEGMENT - 1
    return x[lo:hi + 1]


def fit_line(x: np.ndarray, y: np.ndarray, se: np.ndarray) -> dict:
    """Straight line, with the exact chi-square fit test that known sigma allows."""
    from scipy import stats
    w = 1.0 / se ** 2
    beta, wrss = _wls(_design(x, None), y, w)
    df = len(x) - 2
    return {"beta": beta, "wrss": wrss, "df": df,
            "p_fit": float(stats.chi2.sf(wrss, df))}


def fit_joinpoint(x: np.ndarray, y: np.ndarray, se: np.ndarray,
                  knots: np.ndarray | None = None) -> dict:
    """Best single knot by exhaustive search over the candidate grid."""
    w = 1.0 / se ** 2
    grid = candidate_knots(x) if knots is None else np.asarray(knots, float)
    best = None
    profile = []
    for tau in grid:
        if ((x > tau).sum() < MIN_POINTS_PER_SEGMENT
                or (x <= tau).sum() < MIN_POINTS_PER_SEGMENT):
            continue
        try:
            beta, wrss = _wls(_design(x, tau), y, w)
        except np.linalg.LinAlgError:
            continue
        profile.append((float(tau), wrss))
        if best is None or wrss < best[1]:
            best = (float(tau), wrss, beta)
    if best is None:
        raise RuntimeError("no admissible knot")
    tau, wrss, beta = best
    n = len(x)
    # No AIC/BIC here on purpose. tau is chosen by exhaustive search, so the
    # joinpoint costs four effective parameters rather than three; an
    # information criterion that charges three under-penalises by exactly the
    # margin that decides this comparison. The bootstrap test below prices the
    # search correctly, so model selection goes through it instead.
    return {"tau": tau, "beta": beta, "wrss": wrss, "df": n - 3,
            "profile": profile, "grid": [float(g) for g in grid]}


def bootstrap_test(x: np.ndarray, y: np.ndarray, se: np.ndarray,
                   n_boot: int = 4000, seed: int = 20260819) -> dict:
    """Parametric bootstrap of sup_tau [wRSS(line) - wRSS(joinpoint)].

    Simulating under the fitted line with the known sigma_i and re-running the
    whole grid search on each replicate is what makes the p-value honest: it
    prices in the fact that tau was chosen by looking.
    """
    rng = np.random.default_rng(seed)
    line = fit_line(x, y, se)
    jp = fit_joinpoint(x, y, se)
    observed = line["wrss"] - jp["wrss"]

    fitted = _design(x, None) @ line["beta"]
    null = np.empty(n_boot)
    for b in range(n_boot):
        y_b = fitted + rng.normal(0.0, se)
        null[b] = fit_line(x, y_b, se)["wrss"] - fit_joinpoint(x, y_b, se)["wrss"]

    # Everything here is JSON-serialisable on purpose: this result has to be
    # written once and read by both the figure and the report. When it was not,
    # three different critical values were in circulation (600, 2000 and 4000
    # replicates) plus a fourth typed into the report prose.
    return {"observed": float(observed),
            # (1 + count) / (n_boot + 1), not the bare proportion: a Monte Carlo
            # p-value of exactly 0 asserts an impossibility a finite simulation
            # cannot establish. This does not bite on a null series -- it bites
            # the first time the answer is not null, which is when it matters.
            "p": float((1 + (null >= observed).sum()) / (n_boot + 1)),
            "crit95": float(np.quantile(null, 0.95)),
            "n_boot": n_boot, "seed": seed,
            "tau": jp["tau"],
            "line_wrss": line["wrss"], "line_p_fit": line["p_fit"],
            "line_df": line["df"],
            "line_beta": [float(b) for b in line["beta"]],
            "joinpoint_wrss": jp["wrss"],
            "profile": [[float(a), float(b)] for a, b in jp["profile"]],
            "grid": jp["grid"]}


def profile_set(boot: dict) -> list[float]:
    """Knots whose fit is within the bootstrap critical value of the best.

    Reported instead of a Wald standard error on tau: the segmented-regression
    literature warns those are trustworthy only for clear-cut kinks (Muggeo 2017),
    which this is not. When the set spans the whole grid, that IS the answer -- the data
    cannot localise a break.
    """
    floor = boot["joinpoint_wrss"] + boot["crit95"]
    return [tau for tau, wrss in boot["profile"] if wrss <= floor]


def power_curve(x: np.ndarray, se: np.ndarray, tau: float,
                slope_changes: list[float], n_sim: int = 600,
                n_boot: int = 600, seed: int = 20260819) -> list[dict]:
    """How large a break would this design actually detect?

    Reported alongside any null result. Without it, "no break found" reads as
    evidence of absence, when for eleven points it is mostly evidence of a
    design that cannot see one.
    """
    rng = np.random.default_rng(seed)
    # seed + 1, not seed: sharing it made power_curve's first simulated dataset
    # byte-identical to the first null replicate that set this very threshold,
    # so the first row reported the test's own size rather than its power.
    crit = bootstrap_test(x, np.zeros_like(x) + 0.09, se, n_boot=n_boot,
                          seed=seed + 1)["crit95"]
    out = []
    for delta in slope_changes:
        truth = 0.09 - 0.0005 * (x - x.mean()) + delta * np.clip(x - tau, 0.0, None)
        hits = 0
        for _ in range(n_sim):
            y_b = truth + rng.normal(0.0, se)
            stat = fit_line(x, y_b, se)["wrss"] - fit_joinpoint(x, y_b, se)["wrss"]
            hits += stat >= crit
        out.append({"slope_change_per_year": delta,
                    "slope_change_per_decade_pp": 100 * 10 * delta,
                    "power": hits / n_sim})
    return out
