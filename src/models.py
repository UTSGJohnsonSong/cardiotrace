"""
Survival models for the Part 3 cohort.

TWO QUESTIONS, TWO MODELS, TWO VARIABLE SETS
--------------------------------------------
The DAG in docs/research-design.md says there is no single correct covariate
list — each estimand gets its own, and mixing them is the Table 2 fallacy.

  aetiologic (E2)   how is blood pressure associated with CVD death, adjusted for
                    the confounders the graph names? Written as an effect estimate
                    for a long time; it is not one. The measured pressure is already
                    the product of unobserved treatment history, the Tobin constant
                    is a convention rather than an identification strategy, and the
                    survey selects on being alive. Adjust for confounders of BP
                    only: age, sex, race, education,
                    income, smoking, adiposity. Do NOT adjust for kidney function
                    or inflammation (downstream of BP) or for antihypertensive
                    use (a collider on BP -> treatment <- healthcare access).
                    Report hazard ratios.

  prediction (P)    what is this person's absolute 10-year risk of CVD death?
                    use everything measurable at baseline, including treatment
                    status. Interpret no coefficient. Report discrimination,
                    calibration, and absolute risk.

TREATMENT AND THE EXPOSURE
--------------------------
Measured blood pressure in a treated participant is a post-treatment value: they
are not "a person with normal blood pressure", they are a person whose blood
pressure is being held down. Conditioning on treatment opens a backdoor through
healthcare access, so the aetiologic model instead applies the standard Tobin
adjustment — add a constant to the measured value of treated participants to
approximate the untreated level. This is why the pipeline needed RXQ/BPQ at all.

COMPETING RISK, WITHOUT FINE-GRAY
---------------------------------
Absolute risk is computed from TWO cause-specific Cox models rather than a
subdistribution-hazard fit:

    CIF_1(t|X) = sum over u<=t of  S(u-|X) * dH_1(u|X)
    S(u|X)     = exp( -(H_1(u|X) + H_2(u|X)) )

This is the cause-specific-hazards route to absolute risk. It gives the same
quantity Fine-Gray targets, keeps one fitting path for both questions, and makes
the competing hazard an explicit object rather than something folded into a
reweighting. Ignoring the second model entirely — the 1 - exp(-H_1) shortcut —
is what overstates risk, by 7.4% at 15 years in this cohort.

SURVEY DESIGN
-------------
Fitted with the pooled MEC exam weight and a robust variance clustered on
stratum x PSU. Same-PSU participants are not independent: they share a
neighbourhood, a provider mix and an interviewer. A model-based standard error
would be too small, and a random K-fold split would leak them across the
train/test boundary — which is why validation below splits on survey cycle.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

log = logging.getLogger(__name__)

# Tobin et al. (2005): add a constant to the measured pressure of treated
# participants to recover the untreated level. +10/+5 mmHg is the widely used
# pair; the choice is a sensitivity analysis, not a fact.
TOBIN_SBP, TOBIN_DBP = 10.0, 5.0

# Confounders of the BP -> CVD death relation. Deliberately excludes anything
# downstream of blood pressure and anything on the treatment path.
E2_ADJUSTMENT = ["age", "male", "race_black", "education", "pir",
                 "smoke_current", "smoke_former", "bmi"]


def aetiologic_covariates(exposure: str = "systolic_bp") -> list[str]:
    """The E2 specification, exposure first: one definition, four callers.

    The expression `[exposure] + [c for c in E2_ADJUSTMENT if c != exposure]`
    was written out at three sites -- fit_aetiologic here, the IPCW sensitivity
    fit in src/missingness.py, and the R export in scripts/crosscheck_survey.py.
    Those three produce, respectively, the published hazard ratio, the
    sensitivity analysis the report describes as barely moving it, and the
    design-based interval the report leads with. The report sets them beside
    each other, so a specification that differed between them would read as a
    finding about IPCW or about the estimator rather than as two different
    models.

    Sharing the constant was not enough, and the comment in
    crosscheck_survey.py said so in the wrong direction: it claimed to mirror
    fit_aetiologic's assembly "rather than restating it" while restating it.
    Membership was shared; ordering and the exposure-first convention were not.
    """
    return [exposure] + [c for c in E2_ADJUSTMENT if c != exposure]


# Prediction: everything cheaply measurable at a clinic visit.
P_FEATURES = ["age", "male", "race_black", "systolic_bp", "bp_treated",
              "total_cholesterol", "hdl_cholesterol", "diabetes_dx",
              "smoke_current", "smoke_former", "bmi"]

# Cycles with at least ten years of follow-up on every survivor, so a 10-year
# risk is directly observable rather than extrapolated.
TRAIN_CYCLES = ["1999-2000", "2001-2002", "2003-2004"]
TEST_10Y_CYCLES = ["2005-2006", "2007-2008"]
TEST_5Y_CYCLES = ["2009-2010", "2011-2012", "2013-2014"]


def prepare(df: pd.DataFrame, tobin: bool = True) -> pd.DataFrame:
    """Model matrix: numeric encodings, Tobin adjustment, design columns.

    NOT IDEMPOTENT, which is why it refuses to run twice. The Tobin step adds a
    constant to the measured pressure of treated participants IN PLACE, so a
    second call gives them +20/+10 mmHg instead of +10/+5 -- measured: a treated
    participant at 140 becomes 150, then 160. Nothing else here would notice:
    `male`, `smoke_*` and `design_cluster` are all idempotent, the fit
    converges, and the result is a plausible wrong number. The `prepared=` flags
    on the model classes exist to avoid this; the guard is what makes forgetting
    one of them loud.
    """
    if "design_cluster" in df.columns:
        raise ValueError(
            "prepare() has already been applied to this frame (it carries "
            "design_cluster). Running it again would add the Tobin constant a "
            "second time. Pass prepared=True to the caller instead.")
    d = df.copy()
    d["male"] = (d.sex == "Male").astype(float)
    d["smoke_current"] = (d.smoking == "current").astype(float).where(d.smoking.notna())
    d["smoke_former"] = (d.smoking == "former").astype(float).where(d.smoking.notna())
    if tobin:
        treated = d.bp_treated == 1
        d.loc[treated, "systolic_bp"] = d.loc[treated, "systolic_bp"] + TOBIN_SBP
        d.loc[treated, "diastolic_bp"] = d.loc[treated, "diastolic_bp"] + TOBIN_DBP
    # Same-PSU participants are correlated; the cluster is stratum x PSU.
    d["design_cluster"] = d.strata.astype(str) + "_" + d.psu.astype(str)
    return d


def _fit(d: pd.DataFrame, covariates: list[str], event_col: str,
         penalizer: float = 0.0) -> CoxPHFitter:
    cols = covariates + ["followup_years", event_col, "wtmec2yr", "design_cluster"]
    fit_df = d[cols].dropna()
    cph = CoxPHFitter(penalizer=penalizer)
    cph.fit(fit_df, duration_col="followup_years", event_col=event_col,
            weights_col="wtmec2yr", cluster_col="design_cluster", robust=True)
    return cph


def fit_aetiologic(df: pd.DataFrame, exposure: str = "systolic_bp",
                   tobin: bool = True) -> pd.DataFrame:
    """Cause-specific Cox for the association of `exposure` with CVD death.

    Non-CVD death is treated as censoring. That is the correct handling for the
    aetiologic question — "does blood pressure raise the rate of CVD death among
    those still alive" — and the wrong handling for absolute risk, which is what
    `predict_cif` is for.
    """
    d = prepare(df, tobin=tobin)
    covs = aetiologic_covariates(exposure)
    cph = _fit(d, covs, "cvd_death")
    out = cph.summary[["coef", "exp(coef)", "exp(coef) lower 95%",
                       "exp(coef) upper 95%", "p"]].copy()
    out.columns = ["log_hr", "hr", "hr_lo95", "hr_hi95", "p"]
    out.insert(0, "n", int(cph.weights.shape[0]))
    # The LOG hazard ratio and its bounds are kept unrounded. Rounding the
    # per-unit hazard ratio to four places and then raising it to a power is a
    # 0.0005 error at ten units -- which lands on the third decimal the report
    # prints, so 1.1216 was published as 1.121. Anything scaled to a different
    # exposure contrast has to start from `log_hr`, never from `hr`.
    out["log_lo95"] = cph.summary["coef lower 95%"]
    out["log_hi95"] = cph.summary["coef upper 95%"]
    keep = ["log_hr", "log_lo95", "log_hi95"]
    rounded = out.drop(columns=keep).round(4)
    for c in keep:
        rounded[c] = out[c]
    return rounded[["n"] + keep + [c for c in rounded.columns
                                   if c not in keep and c != "n"]]


class CauseSpecificRisk:
    """Two cause-specific Cox fits combined into an absolute-risk prediction."""

    def __init__(self, features: list[str]):
        self.features = features
        self.cvd: CoxPHFitter | None = None
        self.competing: CoxPHFitter | None = None

    def fit(self, train: pd.DataFrame,
            prepared: bool = False) -> "CauseSpecificRisk":
        """`prepared=True` skips `prepare`, for callers that built the model
        frame once and subset it -- running `prepare` again on a frame whose
        source columns have been dropped raises rather than degrades."""
        d = train if prepared else prepare(train)
        self.cvd = _fit(d, self.features, "cvd_death")
        self.competing = _fit(d, self.features, "competing_death")
        return self

    def _cum_hazards(self, model: CoxPHFitter, X: pd.DataFrame, times: np.ndarray) -> np.ndarray:
        """H(t|X) on a shared time grid: baseline cumulative hazard x risk score."""
        base = model.baseline_cumulative_hazard_.iloc[:, 0]
        h0 = np.interp(times, base.index.to_numpy(float), base.to_numpy(float),
                       left=0.0)
        risk = model.predict_partial_hazard(X).to_numpy(float)
        return np.outer(risk, h0)                       # (n_people, n_times)

    def predict_cif(self, test: pd.DataFrame, horizon: float,
                    n_grid: int = 400, prepared: bool = False) -> pd.Series:
        """Absolute probability of CVD death by `horizon`, competing risk included.

        `prepared=True` takes the frame as given instead of running `prepare`
        again. Permutation importance needs it: `male`, `smoke_current` and
        `smoke_former` are constructed here from `sex` and `smoking`, so
        shuffling them in a raw frame and letting `prepare` run would rebuild
        them from the untouched source columns and report an importance of
        exactly zero for three of the eleven features.
        """
        if self.cvd is None:
            raise RuntimeError("fit() first")
        d = test if prepared else prepare(test)
        X = d[self.features]
        times = np.linspace(0.0, horizon, n_grid)
        h1 = self._cum_hazards(self.cvd, X, times)
        h2 = self._cum_hazards(self.competing, X, times)
        # S(u-) uses the ALL-CAUSE hazard: a person who has died of anything is
        # no longer at risk of dying of CVD. Dropping h2 here is exactly the
        # error the descriptive figure quantifies.
        # S(u-), not S(u): the survival that multiplies dH_1(u) is the one just
        # BEFORE u, because a person has to be alive entering the interval in
        # order to die in it. Evaluating both on the same grid point is a
        # first-order error that shrinks the estimate; on this cohort it is
        # +0.0040 pp on a ~2% risk and vanishes as the grid refines, so it never
        # reached a printed digit -- but the module docstring states the formula
        # with S(u-) and the code has to be the thing the docstring describes.
        # The two halves of that sentence come from the same estimator: +0.0040
        # pp is on the UNWEIGHTED mean of 2.827%; on the weighted 1.959% the
        # report actually prints, the shift is +0.0022 pp.
        surv = np.exp(-(h1 + h2))
        surv_prev = np.concatenate(
            [np.ones((surv.shape[0], 1)), surv[:, :-1]], axis=1)
        dh1 = np.diff(h1, axis=1, prepend=0.0)
        cif = (surv_prev * dh1).cumsum(axis=1)[:, -1]
        return pd.Series(cif, index=d.index, name=f"cif_{horizon:g}y")


def concordance(risk: pd.Series, time: pd.Series, event: pd.Series,
                weights: pd.Series | None = None,
                horizon: float | None = None) -> float:
    """Harrell's C for a higher-is-worse risk score, competing deaths censored.

    `weights` USED to be accepted and silently ignored. Every concordance in
    this project was therefore an unweighted statistic sitting under prose about
    a weighted, nationally representative analysis, and the two differ by more
    than any effect the report goes on to discuss: 0.805 unweighted against
    0.838 weighted on the ten-year test set. A parameter that is accepted and
    dropped is worse than one that does not exist, because the call site reads
    as though the question had been settled.

    `horizon` administratively censors before scoring. Without it the statistic
    ranges over the whole of follow-up while the surrounding text calls it
    ten-year performance. That is not a rounding-level distinction even on the
    cycles this project tests on: the published weighted C moves from 0.841 to
    0.838 at ten years -- a printed digit -- and the unweighted from 0.804 to
    0.805. At five years it is larger still, because the five-year test set has
    follow-up out to 11.25 years, so an uncensored statistic there is not a
    five-year statistic at all: 0.797 against 0.791.

    Pairs are weighted by w_i * w_j, which is the usual survey extension: the
    estimand is the concordance in the POPULATION, and a pair of sampled people
    stands for w_i * w_j pairs of it.
    """
    # The weights are part of the estimator, so a missing weight removes the
    # row rather than poisoning the whole statistic: without this one NaN in
    # wtmec2yr makes the denominator NaN and `concordance` returns NaN, which
    # downstream is indistinguishable from a considered null result.
    ok = risk.notna() & time.notna() & event.notna()
    if weights is not None:
        ok = ok & weights.notna()
    r = risk[ok].to_numpy(float)
    tm = time[ok].to_numpy(float)
    ev = event[ok].to_numpy(float)
    if horizon is not None:
        ev = np.where(tm > horizon, 0.0, ev)
        tm = np.minimum(tm, horizon)
    w = (np.ones_like(r) if weights is None
         else weights[ok].to_numpy(float))

    # One contract for both branches: a degenerate input RAISES. It used to
    # differ -- lifelines threw ZeroDivisionError while the weighted path
    # returned NaN -- so whether a failure was loud depended on whether the
    # caller passed weights. NaN was the dangerous half: `np.percentile` (not
    # nanpercentile) turned one NaN replicate into a NaN interval, and
    # `bool(lo > 0 or hi < 0)` then encoded total failure as "contains zero",
    # which the page reports as a considered null result.
    if len(r) == 0 or ev.sum() == 0 or float(tm.max()) == float(tm.min()):
        raise ValueError(
            f"concordance is undefined here: {len(r)} rows, {int(ev.sum())} "
            f"events, follow-up spans {float(tm.max()) - float(tm.min()):g} "
            f"years. No pair is comparable.")

    if weights is None and horizon is None:
        # Defer to lifelines when there is nothing extra to do, so the common
        # path stays backed by a maintained implementation.
        from lifelines.utils import concordance_index
        return float(concordance_index(tm, -r, ev))
    return _weighted_concordance(r, tm, ev, w)


def _weighted_concordance(risk: np.ndarray, time: np.ndarray,
                          event: np.ndarray, w: np.ndarray) -> float:
    """Weighted C in O(n log n), via a Fenwick tree over risk ranks.

    The naive double loop is O(events x n) and would be fine once. It is not
    fine 3,200 times, which is what a 400-replicate paired bootstrap over four
    arms costs, so the dominance count is done with a prefix-sum tree instead:
    walk the sample in DECREASING time, and every point already inserted is a
    valid comparison partner for the event currently being scored.

    Ties in risk contribute a half, which is Harrell's convention. Ties in time
    are not comparable and are excluded by the strict inequality.
    """
    order = np.argsort(-time, kind="stable")
    risk, time, event, w = risk[order], time[order], event[order], w[order]

    # DENSE ranks: tied risks must share a rank, or the "tied" bucket below is
    # always empty and Harrell's half-credit never applies. argsort-of-argsort
    # gives every element a distinct rank and silently routes each tie into
    # either the concordant or the discordant bucket depending on sort order --
    # which the brute-force test caught within a minute of being written.
    ranks = np.unique(risk, return_inverse=True)[1] + 1
    n = len(risk)
    tree_w = np.zeros(n + 1)          # total weight, by risk rank
    total = 0.0

    num = den = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and time[j] == time[i]:
            j += 1                     # the block of exactly-tied times
        for k in range(i, j):
            if event[k] != 1:
                continue
            # concordant: an inserted point (t > t_k) with LOWER risk
            lower = _bit_sum(tree_w, ranks[k] - 1)
            tied = _bit_sum(tree_w, ranks[k]) - lower
            num += w[k] * (lower + 0.5 * tied)
            den += w[k] * total
        for k in range(i, j):
            _bit_add(tree_w, ranks[k], w[k])
            total += w[k]
        i = j
    if den <= 0:
        raise ValueError(
            "no comparable pair: every event is at the latest observed time, "
            "so nothing can be ordered against it")
    return float(num / den)


def _bit_add(tree: np.ndarray, i: int, v: float) -> None:
    n = len(tree) - 1
    while i <= n:
        tree[i] += v
        i += i & (-i)


def _bit_sum(tree: np.ndarray, i: int) -> float:
    s = 0.0
    while i > 0:
        s += tree[i]
        i -= i & (-i)
    return s


def calibration_table(risk: pd.Series, observed: pd.Series, weights: pd.Series,
                      n_bins: int = 10) -> pd.DataFrame:
    """Predicted vs observed risk by decile of predicted risk.

    Discrimination says whether the ranking is right; calibration says whether
    the numbers are. A model can rank perfectly and still be unusable — which is
    the documented failure mode of the Pooled Cohort Equations in contemporary
    cohorts, and the reason this table exists at all.
    """
    d = pd.DataFrame({"risk": risk, "obs": observed, "w": weights}).dropna()
    # WEIGHTED quantile cut-points. `pd.qcut` splits the SAMPLE into equal-sized
    # groups; with survey weights the sample is not the population, so its
    # deciles are not population deciles. The means inside each bin were already
    # weighted, which made the mismatch invisible: every number in the table was
    # a weighted average over a group defined by an unweighted rule, and the row
    # label "decile" was the only thing that was wrong.
    order = np.argsort(d.risk.to_numpy(), kind="stable")
    cw = np.cumsum(d.w.to_numpy()[order])
    cw = cw / cw[-1]
    edges = np.searchsorted(cw, np.linspace(0.0, 1.0, n_bins + 1)[1:-1])
    cuts = np.unique(d.risk.to_numpy()[order][np.clip(edges, 0, len(order) - 1)])
    d["bin"] = np.searchsorted(cuts, d.risk.to_numpy(), side="right")
    g = d.groupby("bin")
    out = pd.DataFrame({
        "n": g.size(),
        "predicted_pct": 100 * g.apply(lambda x: np.average(x.risk, weights=x.w),
                                       include_groups=False),
        "observed_pct": 100 * g.apply(lambda x: np.average(x.obs, weights=x.w),
                                      include_groups=False),
    })
    out["difference_pp"] = (out.predicted_pct - out.observed_pct).round(2)
    return out.round(2)
