"""Who the complete-case analysis drops, and whether dropping them moves anything.

`models._fit` calls `.dropna()`. That is an analysis decision made by a method
call: it silently redefines the population from "US adults 40-79 free of
cardiovascular disease at baseline" to "US adults 40-79 free of cardiovascular
disease at baseline WHO HAPPENED TO HAVE EVERY VARIABLE MEASURED", and nothing
in the report said so.

The deletion is not small and it is not random. It removes 2,207 of 20,736
participants -- 10.6% -- and those removed have a cardiovascular mortality of
6.12% against 4.26% among those kept. Missingness is associated with the
outcome, which is the case in which complete-case analysis is not merely
inefficient but biased.

This module does three things and claims nothing beyond them:

  `pattern`      which variables drive the deletion, and how the dropped differ
                 from the kept on everything that IS observed for both
  `ipcw`         inverse-probability-of-completeness weights, fitted on the
                 variables observed for everyone, so a complete-case fit can be
                 re-weighted back towards the full cohort
  `sensitivity`  the exposure estimate and the discrimination under both, so a
                 reader can see how far the choice moved them

IPCW IS NOT A FIX AND IS NOT OFFERED AS ONE. It restores unbiasedness only if
completeness is independent of the outcome GIVEN the variables the completeness
model sees. Nothing here can establish that, and the variables most likely to
explain both missingness and death -- illness severity, access to care -- are
exactly the ones a survey that lost them does not have. What it can do is show
whether the answer is sensitive to the assumption at all. If the two agree, the
complete-case result is at least not fragile to this particular correction; if
they disagree, that is worth knowing before anyone quotes either.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.models import P_FEATURES, prepare

# Observed for essentially everyone, so they can model completeness without
# themselves being missing. Deliberately excludes anything from the laboratory
# or the examination: those are what goes missing.
ALWAYS_OBSERVED = ["age", "male", "race_black", "cycle"]

# Reported for the kept-versus-dropped comparison. Chosen because each is
# observed for both groups, so the comparison is possible at all.
COMPARE_ON = ["age", "male", "race_black", "cvd_death", "competing_death",
              "followup_years", "wtmec2yr"]


def _model_frame(cohort: pd.DataFrame) -> pd.DataFrame:
    d = prepare(cohort)
    d["cycle"] = cohort["cycle"].to_numpy()
    return d


def _complete(d: pd.DataFrame, features: list[str]) -> pd.Series:
    cols = list(features) + ["followup_years", "cvd_death", "wtmec2yr",
                             "design_cluster"]
    return d[cols].notna().all(axis=1)


def pattern(cohort: pd.DataFrame,
            features: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(what drives the deletion, how the two groups differ).

    The first table answers "which variable costs the most", which is the one a
    reader can act on. The second answers "are the dropped different", which is
    the one that decides whether complete-case is defensible.
    """
    features = list(features or P_FEATURES)
    d = _model_frame(cohort)
    ok = _complete(d, features)

    drivers = pd.DataFrame([
        {"variable": f,
         "n_missing": int(d[f].isna().sum()),
         "pct_missing": round(100 * float(d[f].isna().mean()), 2),
         # How many rows this variable ALONE removes: missing here and complete
         # on everything else. A variable with a large marginal count but a
         # small unique count is riding along with another one.
         "n_uniquely_lost": int((d[f].isna()
                                 & _complete(d, [c for c in features if c != f])).sum())}
        for f in features
    ]).sort_values("n_uniquely_lost", ascending=False)

    rows = []
    for col in COMPARE_ON:
        if col not in d.columns:
            continue
        kept, dropped = d.loc[ok, col], d.loc[~ok, col]
        rows.append({
            "variable": col,
            "kept_mean": round(float(kept.mean()), 4),
            "dropped_mean": round(float(dropped.mean()), 4),
            "difference": round(float(dropped.mean() - kept.mean()), 4),
        })
    compare = pd.DataFrame(rows)
    compare.attrs["n_kept"] = int(ok.sum())
    compare.attrs["n_dropped"] = int((~ok).sum())
    return drivers, compare


def ipcw(cohort: pd.DataFrame, features: list[str] | None = None) -> pd.Series:
    """Survey weight x 1 / P(complete | age, sex, race, cycle).

    Fitted on the whole cohort, so the model sees the dropped participants --
    that is the entire point, and it is only possible because these four
    variables are observed for everyone.

    The weights are trimmed at the 99th percentile. An untrimmed IPCW can hand
    one participant several per cent of the total weight, and a "corrected"
    estimate driven by three people is worse than the uncorrected one it
    replaced.
    """
    features = list(features or P_FEATURES)
    d = _model_frame(cohort)
    ok = _complete(d, features)

    X = pd.get_dummies(d[ALWAYS_OBSERVED], columns=["cycle"], drop_first=True)
    X = X.astype(float).fillna(X.astype(float).median())
    fit = LogisticRegression(max_iter=2000, C=1.0).fit(X, ok.astype(int))
    p = fit.predict_proba(X)[:, 1]

    w = d["wtmec2yr"].to_numpy(float) / np.clip(p, 0.05, 1.0)
    cap = np.nanpercentile(w[ok], 99)
    return pd.Series(np.minimum(w, cap), index=d.index, name="ipcw")


def sensitivity(cohort: pd.DataFrame, features: list[str] | None = None) -> pd.DataFrame:
    """The exposure hazard ratio under the survey weight and under IPCW.

    Only the aetiologic fit is re-run. The prediction model's discrimination is
    a ranking statistic on held-out cycles and is far less exposed to this than
    a coefficient is; re-weighting it would add a second moving part without
    answering the question the reviewer asked.
    """
    from src.models import E2_ADJUSTMENT, _fit

    features = list(features or P_FEATURES)
    d = _model_frame(cohort)
    d["ipcw"] = ipcw(cohort, features)
    covs = ["systolic_bp"] + [c for c in E2_ADJUSTMENT if c != "systolic_bp"]

    rows = []
    for label, weight_col in (("complete case, survey weight", "wtmec2yr"),
                              ("complete case, IPCW", "ipcw")):
        frame = d.copy()
        frame["wtmec2yr"] = frame[weight_col]
        cph = _fit(frame, covs, "cvd_death")
        r = cph.summary.loc["systolic_bp"]
        rows.append({
            "weighting": label,
            "n": int(cph.weights.shape[0]),
            "hr_per_10mmhg": round(float(np.exp(r["coef"] * 10)), 4),
            "lo95": round(float(np.exp(r["coef lower 95%"] * 10)), 4),
            "hi95": round(float(np.exp(r["coef upper 95%"] * 10)), 4),
        })
    return pd.DataFrame(rows)
