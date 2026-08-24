"""
Survival estimators and descriptive curves for the Part 3 cohort.

Two estimators, implemented directly rather than pulled from lifelines:

  kaplan_meier          treats every non-event as censoring
  aalen_johansen_cif    treats death from another cause as a COMPETING EVENT

The distinction is the point of the second figure. In this cohort competing
deaths outnumber CVD deaths 2.9 : 1 (2,711 vs 925), and the naive 1 - KM curve
answers a question nobody asks: "what fraction would die of CVD if it were
impossible to die of anything else". Aalen-Johansen answers the real one: "what
fraction actually do". With competing events this common the gap is large enough
to change a clinical reading, so both are plotted side by side.

Weights: point estimates use the pooled MEC exam weight, so the curves describe
the US non-institutionalised adult population rather than the NHANES sample.
Design-based confidence bands need the strata/PSU columns through a Taylor or
replicate-weight estimator and are NOT produced here — the curves are point
estimates only, and the figures say so.

Implemented here rather than imported because both estimators are short, the
project gains a unit-testable component, and it avoids a dependency for what is
ultimately a weighted cumulative sum. Cox and Fine-Gray will need lifelines.
"""

from __future__ import annotations

from enum import IntEnum

import numpy as np
import pandas as pd

# Missing values in this pipeline are ALWAYS np.nan, never pd.NA. The two do not
# interoperate: `.loc` setitem quietly down-casts pd.NA to np.nan, while
# `.replace()` widens the column to object and the next `.astype(float)` raises.
# Same value, two assignment paths, different behaviour — one convention removes
# the whole class of surprise.

# Palette — dataviz reference instance, validated (see docs/research-design.md).
# Blood-pressure strata are ORDINAL: swapping their order changes the meaning, so
# they take a one-hue ramp with monotone lightness rather than categorical hues.
# Steps 250/350/450/550/650 of the blue ramp; validated with --ordinal (monotone
# L, adjacent dL >= 0.06, light end 2.06:1 on the light surface, hue spread 3deg).
ORDINAL_BLUE = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
# Naive vs competing-risk are two nominal series -> categorical slots 1 and 2.
CATEGORICAL = ["#2a78d6", "#eb6834"]

INK_PRIMARY, INK_SECONDARY, INK_MUTED = "#0b0b0b", "#52514e", "#898781"
GRIDLINE, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

SBP_BINS = [-np.inf, 120, 130, 140, 160, np.inf]
SBP_LABELS = ["<120", "120–129", "130–139", "140–159", "≥160"]


class Event(IntEnum):
    """Event codes. Defined once so the three estimators cannot drift apart."""

    CENSORED = 0
    CAUSE_OF_INTEREST = 1
    COMPETING = 2


def _event_table(time: np.ndarray, event: np.ndarray, weight: np.ndarray) -> pd.DataFrame:
    """Weighted risk set and event counts at each distinct observed time.

    `event` uses the `Event` codes: 0 censored, 1 cause of interest, 2 competing.
    """
    # A NaN follow-up time is silently poisonous here: groupby drops it, so the
    # subject never leaves the `exit` column, but `total` below still counts
    # their weight — the risk set stays permanently inflated and every
    # cumulative incidence comes out too low, with no error. Four subjects, one
    # with NaN time, gives CIF(t=1) = 0.25 instead of 0.333. Refuse the input.
    time = np.asarray(time, float)
    n_nan = int(np.isnan(time).sum())
    if n_nan:
        raise ValueError(
            f"{n_nan} of {len(time)} rows have NaN follow-up time. They would "
            "inflate the risk set and understate cumulative incidence without "
            "raising. Filter them out before calling."
        )
    bad = ~np.isin(event, [e.value for e in Event])
    if bad.any():
        raise ValueError(f"event must be one of {[e.value for e in Event]}; "
                         f"got {sorted(set(np.asarray(event)[bad]))}")

    if len(time) == 0:
        # groupby on an empty frame returns an empty DataFrame from .apply, whose
        # .to_numpy() is 2-D, and the constructor below then fails with
        # "Per-column arrays must each be 1-dimensional" — an error that points
        # nowhere near the real cause. An empty stratum is a legitimate input.
        return pd.DataFrame({c: pd.Series(dtype=float)
                             for c in ("t", "d1", "d2", "exit", "at_risk")})

    df = pd.DataFrame({"t": time, "e": event, "w": weight}).sort_values("t")
    g = df.groupby("t", sort=True)
    tab = pd.DataFrame({
        "t": g.size().index.to_numpy(float),
        "d1": g.apply(lambda x: x.w[x.e == 1].sum(), include_groups=False).to_numpy(float),
        "d2": g.apply(lambda x: x.w[x.e == 2].sum(), include_groups=False).to_numpy(float),
        "exit": g["w"].sum().to_numpy(float),
    })
    total = df.w.sum()
    # At risk just before t = everyone minus everyone who already left.
    tab["at_risk"] = total - np.concatenate([[0.0], np.cumsum(tab["exit"].to_numpy())[:-1]])
    return tab


def kaplan_meier(time, event, weight=None, cause: int = 1) -> pd.DataFrame:
    """1 - S(t) treating competing events as censoring (the naive curve)."""
    weight = np.ones_like(time, dtype=float) if weight is None else np.asarray(weight, float)
    tab = _event_table(np.asarray(time, float), np.asarray(event, int), weight)
    d = tab["d1"] if cause == 1 else tab["d2"]
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(tab["at_risk"] > 0, d / tab["at_risk"], 0.0)
    surv = np.cumprod(1.0 - frac)
    return pd.DataFrame({"t": tab["t"], "cum_inc": 1.0 - surv, "at_risk": tab["at_risk"]})


def aalen_johansen_cif(time, event, weight=None, cause: int = 1) -> pd.DataFrame:
    """Cumulative incidence of `cause` in the presence of competing events.

    CIF_k(t) = sum over event times u <= t of  S(u-) * d_k(u) / n(u),
    where S is the ALL-CAUSE Kaplan-Meier (any event removes you from risk).
    Using the cause-specific KM here instead is the classic error that produces
    the inflated naive curve.
    """
    weight = np.ones_like(time, dtype=float) if weight is None else np.asarray(weight, float)
    tab = _event_table(np.asarray(time, float), np.asarray(event, int), weight)
    n = tab["at_risk"].to_numpy()
    d_any = (tab["d1"] + tab["d2"]).to_numpy()
    d_k = (tab["d1"] if cause == 1 else tab["d2"]).to_numpy()

    with np.errstate(divide="ignore", invalid="ignore"):
        haz_any = np.where(n > 0, d_any / n, 0.0)
        haz_k = np.where(n > 0, d_k / n, 0.0)
    # S(u-) is the all-cause survival just BEFORE u, hence the shift.
    s_prev = np.concatenate([[1.0], np.cumprod(1.0 - haz_any)[:-1]])
    return pd.DataFrame({"t": tab["t"], "cif": np.cumsum(s_prev * haz_k),
                         "at_risk": tab["at_risk"]})


def make_event_code(df: pd.DataFrame) -> np.ndarray:
    """Map the cohort's two death flags onto `Event` codes.

    Raises rather than folding an unknown mortality status into CENSORED. Both
    flags NaN means "we do not know whether this person died", which is not the
    same statement as "alive at the end of follow-up" — but `np.where` renders
    them identically, and the resulting curve is biased downward with nothing
    to show for it. This is the project's recurring failure mode (missing data
    that looks like an ordinary observation), so it fails loudly here.
    """
    unknown = df.cvd_death.isna() | df.competing_death.isna()
    if unknown.any():
        raise ValueError(
            f"{int(unknown.sum())} rows have unknown mortality status "
            "(cvd_death or competing_death is NaN). Coding them as censored "
            "would understate cumulative incidence. Resolve or exclude them."
        )
    both = (df.cvd_death == 1) & (df.competing_death == 1)
    if both.any():
        raise ValueError(f"{int(both.sum())} rows are flagged as both a CVD death "
                         "and a competing death; the causes must be mutually exclusive.")
    return np.where(df.cvd_death == 1, Event.CAUSE_OF_INTEREST,
                    np.where(df.competing_death == 1, Event.COMPETING, Event.CENSORED))


def at_risk_counts(df: pd.DataFrame, times: list[float], group: str | None = None) -> pd.DataFrame:
    """Unweighted numbers at risk — the count readers expect under a KM plot."""
    def row(d):
        return {f"{t:g}": int((d.followup_years >= t).sum()) for t in times}
    if group is None:
        return pd.DataFrame([row(df)], index=["All"])
    return pd.DataFrame({k: row(g) for k, g in df.groupby(group, observed=True)}).T
