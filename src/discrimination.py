"""Is C = 0.804 held down by the variable set, or by the model form?

The published prediction model is a cause-specific Cox pair on eleven variables
and reaches Harrell C = 0.804 at ten years on held-out later cycles. Two very
different things could be limiting it, and the report cannot say which:

  the VARIABLE SET   eleven clinic-visit measurements may not carry more
  the MODEL FORM     linear, additive and proportional-hazards may not fit

So both are varied, factorially, on one analysis set:

                    eleven variables      eleven + what the screen selected
  Cox                 cox_p (reference)     cox_wide
  gradient boosting   gbm_p                 gbm_wide

plus a floor arm on age and sex alone. The floor is not decoration: a
concordance statistic is uninterpretable without knowing what the trivial model
already achieves, and on a cohort aged 40-79 followed for cardiovascular death,
age alone is a strong predictor. If the eleven barely beat the floor, that is the
finding.

WHAT A NULL HERE MEANS, AND WHY IT IS WORTH REPORTING. If gradient boosting does
not beat the Cox pair, that is evidence about this problem -- 447 events, eleven
mostly-monotone clinical variables -- and not a defect in the method. It is also
the result that protects the rest of the project: the argument throughout is
that a high discrimination statistic is not evidence for a causal claim, and a
section that quietly showed a machine-learning model winning on discrimination
while saying nothing about identification would undercut it.

WHAT THIS SECTION MAY NOT CLAIM. Nothing here licenses any statement about
causes. The arms are ranked on discrimination, which is invariant to any
monotone transformation of predicted risk and therefore says nothing about
calibration or absolute risk. `gbm_*` also gives up the competing-risk
structure -- see `HorizonClassifier` -- so its predictions are not absolute
risks in the sense `CauseSpecificRisk.predict_cif` produces.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from src.models import (
    P_FEATURES, TEST_10Y_CYCLES, TRAIN_CYCLES, CauseSpecificRisk, concordance,
    prepare,
)

# Bootstrap replicates for the paired difference in C. Resampling is by design
# cluster, not by row: two participants from the same masked variance unit are
# correlated, and a row bootstrap would treat them as independent and produce an
# interval too narrow -- the same error the intervals in §2 exist to avoid.
N_BOOT = 400
SEED = 20260822


class HorizonClassifier:
    """Gradient boosting on "dead of CVD by the horizon", among those whose
    status at the horizon is observed.

    This is the honest way to put a general-purpose classifier next to a
    cause-specific Cox pair, and it costs three things, all stated rather than
    absorbed:

      1. Competing deaths become negative labels rather than a competing risk.
         A participant who died of cancer at year 3 is scored as "did not die of
         CVD by year 10", which is true and is not the same quantity the Cox
         arm predicts.
      2. Anyone censored before the horizon is dropped, so the training sample
         is smaller than the Cox arm's.
      3. The output ranks people; it is not an absolute risk.

    None of that affects the comparison the section makes, because that
    comparison is on discrimination, which only needs a ranking. It would
    invalidate a calibration comparison, which is why none is made.
    """

    def __init__(self, features: list[str], horizon: float, **kwargs):
        self.features = list(features)
        self.horizon = float(horizon)
        # Shallow and heavily regularised on purpose: 447 events is not a lot,
        # and an unconstrained booster on this many rows will fit the training
        # cycles perfectly and transport nothing.
        self.model = HistGradientBoostingClassifier(
            max_depth=3, max_iter=200, learning_rate=0.06,
            min_samples_leaf=40, l2_regularization=1.0,
            early_stopping=False, random_state=SEED, **kwargs)

    @staticmethod
    def label(d: pd.DataFrame, horizon: float) -> pd.Series:
        return ((d["cvd_death"] == 1) & (d["followup_years"] <= horizon)).astype(int)

    @staticmethod
    def evaluable(d: pd.DataFrame, horizon: float) -> pd.Series:
        """Status at the horizon is known: either followed that long, or dead."""
        return (d["followup_years"] >= horizon) | (d["cvd_death"] == 1) | \
               (d["competing_death"] == 1)

    def fit(self, train: pd.DataFrame,
            prepared: bool = False) -> "HorizonClassifier":
        d = train if prepared else prepare(train)
        ok = self.evaluable(d, self.horizon)
        X = d.loc[ok, self.features]
        y = self.label(d.loc[ok], self.horizon)
        # Sample weights are the survey weights: the model is meant to rank the
        # population, not the sample, and the two differ by design.
        self.model.fit(X, y, sample_weight=d.loc[ok, "wtmec2yr"])
        return self

    def predict_cif(self, test: pd.DataFrame, horizon: float,
                    prepared: bool = False) -> pd.Series:
        d = test if prepared else prepare(test)
        p = self.model.predict_proba(d[self.features])[:, 1]
        return pd.Series(p, index=d.index, name="risk")


def model_frame(df: pd.DataFrame) -> pd.DataFrame:
    return prepare(df)


def analysis_set(d: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Rows complete on every feature ANY arm uses, plus the outcome columns.

    One set for every arm. Letting each arm use the rows it happens to have
    would compare models on different people, and the difference in C would
    then be partly a difference in who was scored.
    """
    cols = list(dict.fromkeys(features)) + [
        "followup_years", "cvd_death", "competing_death", "wtmec2yr",
        "design_cluster"]
    return d[cols].dropna()


def evaluate(risk: pd.Series, d: pd.DataFrame, horizon: float) -> dict:
    """Two discrimination statistics, because one of them is not a fair contest.

    Harrell's C is the primary, so the reference arm is directly comparable to
    the 0.804 already published. But it rewards getting the ORDER of deaths
    right in time, and the boosted arms never see a time -- they are fitted on a
    binary "dead of CVD by the horizon". Reporting only C would hand the Cox
    arms an advantage that comes from the metric rather than from the model.

    So `auc_horizon` is reported alongside: the weighted area under the ROC for
    the same binary event both arms can actually predict. Whatever the two
    statistics agree on is not an artefact of the choice between them.
    """
    from sklearn.metrics import roc_auc_score

    ok = HorizonClassifier.evaluable(d, horizon)
    y = HorizonClassifier.label(d.loc[ok], horizon)
    auc = (float(roc_auc_score(y, risk.loc[ok], sample_weight=d.loc[ok, "wtmec2yr"]))
           if y.nunique() > 1 else float("nan"))
    return {"c": concordance(risk, d["followup_years"], d["cvd_death"]),
            "auc_horizon": auc,
            "n": int(len(d)), "n_evaluable": int(ok.sum()),
            "events": int(d["cvd_death"].sum())}


def cluster_bootstrap_delta(risk_a: pd.Series, risk_b: pd.Series,
                            d: pd.DataFrame, n_boot: int = N_BOOT,
                            seed: int = SEED) -> dict:
    """Interval for C(a) - C(b) on the SAME people, resampling whole clusters.

    Paired, because the two scores are computed on identical rows: the
    difference has far less variance than either C on its own, and comparing
    two independently-bootstrapped intervals for overlap would be a much less
    powerful and much less correct test.
    """
    rng = np.random.default_rng(seed)
    clusters = d["design_cluster"].to_numpy()
    unique = np.unique(clusters)
    index = {c: np.flatnonzero(clusters == c) for c in unique}

    deltas = []
    for _ in range(n_boot):
        picked = rng.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([index[c] for c in picked])
        sub = d.iloc[rows]
        if sub["cvd_death"].sum() < 10:
            continue
        ca = concordance(risk_a.iloc[rows], sub["followup_years"], sub["cvd_death"])
        cb = concordance(risk_b.iloc[rows], sub["followup_years"], sub["cvd_death"])
        deltas.append(ca - cb)

    arr = np.asarray(deltas)
    lo, hi = np.percentile(arr, [2.5, 97.5])
    point = float(concordance(risk_a, d["followup_years"], d["cvd_death"])
                  - concordance(risk_b, d["followup_years"], d["cvd_death"]))
    return {"delta": round(point, 4), "lo": round(float(lo), 4),
            "hi": round(float(hi), 4), "half_width": round(float(hi - lo) / 2, 4),
            "n_boot": int(len(arr)),
            "excludes_zero": bool(lo > 0 or hi < 0)}


def permutation_importance(model, d: pd.DataFrame, features: list[str],
                           horizon: float, n_repeat: int = 5,
                           seed: int = SEED) -> pd.DataFrame:
    """Drop in C when one feature is shuffled, measured IN THE MODEL FRAME.

    Shuffling the raw frame instead would be silently wrong for a third of the
    eleven: `male`, `smoke_current` and `smoke_former` are constructed inside
    `prepare()` from `sex` and `smoking`, so a permuted `male` column is simply
    recomputed from the untouched source and the measured importance is exactly
    zero. The features that do not exist in the raw frame at all would raise.
    """
    base = concordance(model.predict_cif(d, horizon, prepared=True),
                       d["followup_years"], d["cvd_death"])
    rng = np.random.default_rng(seed)
    rows = []
    for f in features:
        drops = []
        for _ in range(n_repeat):
            shuffled = d.copy()
            col = shuffled[f].to_numpy(copy=True)
            rng.shuffle(col)
            shuffled[f] = col
            c = concordance(model.predict_cif(shuffled, horizon, prepared=True),
                            shuffled["followup_years"], shuffled["cvd_death"])
            drops.append(base - c)
        rows.append({"variable": f, "delta_c": round(float(np.mean(drops)), 5),
                     "sd": round(float(np.std(drops)), 5)})
    out = pd.DataFrame(rows).sort_values("delta_c", ascending=False)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def run(cohort: pd.DataFrame, selected: list[str], horizon: float = 10.0) -> dict:
    """Fit every arm, score them on one analysis set, and pair every difference
    against the published model.
    """
    d = model_frame(cohort)
    wide = list(P_FEATURES) + [v for v in selected if v not in P_FEATURES]
    floor = ["age", "male"]

    everything = analysis_set(d, wide + floor + ["cycle"])
    train = everything[everything["cycle"].isin(TRAIN_CYCLES)]
    test = everything[everything["cycle"].isin(TEST_10Y_CYCLES)]

    arms = {
        "cox_p":     (CauseSpecificRisk(list(P_FEATURES)), list(P_FEATURES)),
        "cox_wide":  (CauseSpecificRisk(wide), wide),
        "gbm_p":     (HorizonClassifier(list(P_FEATURES), horizon), list(P_FEATURES)),
        "gbm_wide":  (HorizonClassifier(wide, horizon), wide),
        "floor_age_sex": (CauseSpecificRisk(floor), floor),
    }

    scores, risks = {}, {}
    for name, (model, feats) in arms.items():
        model.fit(train, prepared=True)
        risks[name] = model.predict_cif(test, horizon, prepared=True)
        scores[name] = (evaluate(risks[name], test, horizon)
                        | {"n_features": len(feats)})
        arms[name] = (model, feats)

    reference = "cox_p"
    deltas = {name: cluster_bootstrap_delta(risks[name], risks[reference], test)
              for name in arms if name != reference}

    imp = permutation_importance(arms["cox_wide"][0], test, wide, horizon)

    return {"scores": scores, "deltas": deltas, "reference": reference,
            "importance": imp, "wide": wide, "horizon": horizon,
            "n_train": int(len(train)), "n_test": int(len(test)),
            "events_test": int(test["cvd_death"].sum()),
            "n_boot": N_BOOT}
