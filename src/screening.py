"""Systematic screening of the variables the prediction model does not carry.

The published model uses eleven variables. The advisor
asked whether anything outside that set carries independent information. This
module answers that, and it answers it under the constraint the rest of the
project runs on: a variable that helps a prediction is not thereby a variable a
causal model may adjust for.

Every candidate therefore carries TWO declarations, and neither is derived:

  `e2_status`  what the aetiologic model may do with it, read off the locked DAG
               at docs/research-design.md node 4. Three states, because two
               would force a guess:
                 admissible    a confounder, or already in E2_ADJUSTMENT
                 forbidden     a descendant of blood pressure, a collider on the
                               treatment path, or the exposure itself
                 undetermined  the locked DAG does not settle it
  `why`        the sentence that justifies the status, in the DAG's own terms

`undetermined` is not a hedge. The DAG draws no parents for the kidney node and
no edge between blood pressure and kidney function, so it cannot say whether
eGFR is a confounder or a mediator; deciding that is a modelling decision, and
this module has no standing to make it. Lipids sit at a collider between the
unmeasured genetic node and adiposity, and are excluded from E2_ADJUSTMENT
without a stated reason. Those cases are reported as open, not resolved.

Screening happens on the TRAINING cycles only. A variable chosen with the test
cycles in view is a variable chosen with the answer in view, and the C statistic
that follows would be an in-sample number wearing an out-of-sample label.

The survey design is deliberately absent from the selection step and present in
the fit: selection asks which variables carry signal in this sample, which is a
question about the sample, while the standard errors that follow are about the
population and need the design.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

from src.biomarkers import derive
from src.models import P_FEATURES, TRAIN_CYCLES, prepare

# Selection is scored by the DESIGN-BASED Wald statistic -- the coefficient over
# its cluster-robust standard error -- and not by a likelihood ratio.
#
# The first version of this module used 2*(ll1 - ll0) and produced "chi-square"
# values in the millions. lifelines scales a weighted partial log-likelihood by
# the sum of the weights, and `wtmec2yr` is a population weight in the tens of
# thousands, so the statistic was on the scale of the US adult population rather
# than of 538 events. The deeper problem survives rescaling: a pseudo-likelihood
# built from survey weights has no chi-square null without a Rao-Scott
# correction, whereas the robust Wald statistic is exactly what the rest of this
# project already uses for design-based inference.
#
# 3.84 is the 5% chi-square point on one degree of freedom, i.e. |z| >= 1.96. It
# is a screening rule and not a test -- searching over candidates inflates it,
# the same way searching over knots inflates the change-point threshold in §3 --
# and it was fixed before the screen was run.
WALD_THRESHOLD = 3.84
MAX_SELECTED = 6

# A candidate joins the forward path only if it is observed for at least this
# share of the training rows the eleven incumbents are complete on.
#
# Without the gate the common analysis set collapsed from 6,772 rows and 538
# events to 1,644 and 104, because fasting glucose, triglycerides and LDL are
# measured only in the morning fasting subsample -- half the cohort by design --
# and alcohol intake is missing for a third. Selecting six variables on 104
# events is fitting noise. Those candidates keep their marginal rankings, each
# computed on its own rows, and are reported as out of the path with the reason.
MIN_COVERAGE = 0.80

# Below this the candidate is not offered to the fitter at all. Named, because
# "did not fit" and "was never fitted" are different statements and the second
# one used to be printed as the first.
MIN_ROWS_TO_FIT = 300


@dataclass(frozen=True)
class Candidate:
    name: str
    label: str
    e2_status: str          # admissible | forbidden | undetermined
    why: str


# Every candidate the cohort can supply, each with its causal status stated.
# Nothing is defaulted: a variable absent from this list is absent from the
# screen, and `assert_declared` refuses to run if the two ever disagree.
CANDIDATES: list[Candidate] = [
    Candidate("egfr", "eGFR (CKD-EPI 2021)", "undetermined",
              "The DAG draws the kidney node with no parents and no edge to or "
              "from blood pressure, so it cannot say whether this is a "
              "confounder or a mediator."),
    Candidate("log_uacr", "log urine albumin/creatinine", "undetermined",
              "Same node as eGFR, same omission."),
    Candidate("hba1c", "HbA1c", "undetermined",
              "Glucose is parallel to blood pressure in the DAG, not downstream "
              "of it, yet E2_ADJUSTMENT excludes it without a stated reason."),
    Candidate("fasting_glucose", "Fasting glucose", "undetermined",
              "Same node as HbA1c."),
    Candidate("triglycerides", "Triglycerides", "undetermined",
              "Lipids sit at a collider between the unmeasured genetic node and "
              "adiposity; conditioning on them opens a path the DAG cannot "
              "close, because the genetic node is unmeasured."),
    Candidate("ldl_cholesterol", "LDL cholesterol", "undetermined",
              "Same node as triglycerides."),
    Candidate("uric_acid", "Uric acid", "undetermined",
              "Not a node in the locked DAG at all."),
    Candidate("waist_cm", "Waist circumference", "admissible",
              "The adiposity node, which E2_ADJUSTMENT already adjusts through "
              "BMI. A second measure of the same node, not a new one."),
    Candidate("drinks_per_day", "Alcohol, drinks per day", "admissible",
              "A behaviour node with edges into blood pressure and into death: "
              "a confounder by the DAG's own construction."),
    Candidate("insured", "Health insurance", "admissible",
              "Socioeconomic position. It reaches death only through "
              "medication, and is not a descendant of blood pressure."),
    Candidate("pulse_pressure", "Pulse pressure", "forbidden",
              "It is the exposure: systolic minus diastolic, both of them the "
              "blood pressure node."),
    Candidate("diastolic_bp", "Diastolic pressure", "forbidden",
              "The exposure node."),
    Candidate("htn_diagnosed", "Told they have hypertension", "forbidden",
              "A descendant of measured blood pressure, and of access to care."),
    Candidate("on_insulin", "On insulin", "forbidden",
              "Treatment, downstream of glucose, and on the same collider "
              "structure as antihypertensive use."),
    Candidate("kidney_dx", "Told they have kidney disease", "forbidden",
              "A diagnosis: a descendant of both the kidney node and insurance."),
]

# The eleven the model already carries, so the two orderings can be compared on
# one table. Status again declared rather than derived; `systolic_bp` gets its
# own state because "admissible" is wrong for an exposure and "forbidden" reads
# as though something were wrong with it.
INCUMBENT_STATUS: dict[str, tuple[str, str]] = {
    "age":               ("admissible", "In E2_ADJUSTMENT."),
    "male":              ("admissible", "In E2_ADJUSTMENT."),
    "race_black":        ("admissible", "In E2_ADJUSTMENT."),
    "smoke_current":     ("admissible", "In E2_ADJUSTMENT."),
    "smoke_former":      ("admissible", "In E2_ADJUSTMENT."),
    "bmi":               ("admissible", "In E2_ADJUSTMENT."),
    "systolic_bp":       ("exposure",   "The exposure whose effect E2 estimates."),
    "bp_treated":        ("forbidden",  "A collider: blood pressure and prevalent "
                                        "disease both cause treatment."),
    "total_cholesterol": ("undetermined", "The lipid node; see triglycerides."),
    "hdl_cholesterol":   ("undetermined", "The lipid node; see triglycerides."),
    "diabetes_dx":       ("undetermined", "A diagnosis at the glucose node, so it "
                                          "carries access to care as well."),
}

STATUS = {c.name: (c.e2_status, c.why) for c in CANDIDATES} | INCUMBENT_STATUS

# `|` resolves a key collision by silently taking the right-hand side. A
# variable added to CANDIDATES that is already an incumbent would therefore lose
# its declared status and print the incumbent's instead -- in the importance
# table but not the ranking table, on the same page. These run at import, the
# only moment early enough to matter. All five hold today.
_names = [c.name for c in CANDIDATES]
_declared = {"admissible", "forbidden", "undetermined", "exposure"}
assert len(_names) == len(set(_names)), f"duplicate candidate names: {_names}"
assert not (set(_names) & set(INCUMBENT_STATUS)), (
    f"candidate is also an incumbent: {sorted(set(_names) & set(INCUMBENT_STATUS))}; "
    f"STATUS would keep the incumbent's status and discard the candidate's")
assert set(INCUMBENT_STATUS) == set(P_FEATURES), (
    f"INCUMBENT_STATUS and P_FEATURES disagree: "
    f"{sorted(set(INCUMBENT_STATUS) ^ set(P_FEATURES))}")
_used = {v[0] for v in STATUS.values()}
assert _used <= _declared, f"undeclared e2 state(s): {sorted(_used - _declared)}"
assert "exposure" not in {c.e2_status for c in CANDIDATES}, (
    "'exposure' describes the variable the aetiologic model estimates, not a "
    "candidate for addition to the prediction model")


def assert_declared(names) -> None:
    """Refuse to report on a variable whose causal status nobody wrote down.

    The alternative -- defaulting to admissible -- would print "allowed" under a
    column headed "in the causal model?" for variables the DAG says nothing
    about, which is a false statement on a public page rather than a missing one.
    """
    undeclared = sorted(set(names) - set(STATUS))
    if undeclared:
        raise KeyError(f"no declared e2 status for {undeclared}; add them to "
                       f"CANDIDATES or INCUMBENT_STATUS in src/screening.py")


def candidate_frame(cohort: pd.DataFrame) -> pd.DataFrame:
    """The model frame plus every candidate, with the derived columns added."""
    d = prepare(derive(cohort))
    assert_declared(list(P_FEATURES) + [c.name for c in CANDIDATES])
    return d


# pulse_pressure is systolic minus diastolic, and systolic is already in
# P_FEATURES: the three are linearly dependent, so a model holding all of them
# is rank-deficient and the fit does not converge. Declared rather than
# discovered, because the failure it causes is a LinAlg warning followed by a
# crash deep inside the fitter, which reads like a bug in the screen.
EXCLUDES: dict[str, set[str]] = {
    "pulse_pressure": {"diastolic_bp"},
    "diastolic_bp": {"pulse_pressure"},
}


def _wald(d: pd.DataFrame, covariates: list[str], target: str) -> dict | None:
    """Design-based Wald statistic for `target`, adjusted for `covariates`.

    Returns None if the fit will not run. A candidate that cannot be fitted
    alongside what is already chosen is a fact about that candidate: the screen
    records it and carries on rather than stopping, and it is never silently
    scored as zero.
    """
    cols = list(covariates) + [target] if target not in covariates else list(covariates)
    frame = d[cols + ["followup_years", "cvd_death", "wtmec2yr",
                      "design_cluster"]].dropna()
    cph = CoxPHFitter(penalizer=0.01)
    try:
        cph.fit(frame, duration_col="followup_years", event_col="cvd_death",
                weights_col="wtmec2yr", cluster_col="design_cluster", robust=True)
        row = cph.summary.loc[target]
    except Exception:
        return None
    z = float(row["z"])
    if not np.isfinite(z):
        return None
    # Per standard deviation, so candidates on wildly different scales -- mg/dL,
    # mL/min, a 0/1 indicator -- are comparable at a glance. The Wald statistic
    # itself is scale-free and is what the selection uses.
    sd = float(frame[target].std(ddof=0))
    return {"z": z, "wald": z * z, "hr_per_sd": float(np.exp(row["coef"] * sd)),
            "n": int(len(frame)), "events": int(frame["cvd_death"].sum())}


def marginal_ranking(train: pd.DataFrame) -> pd.DataFrame:
    """Each candidate on its own, against the eleven the model already has.

    Marginal rather than univariate: a candidate is only interesting if it adds
    to what is already there, and a univariate hazard ratio for eGFR mostly
    reports that older people have worse kidneys.

    Every candidate is scored on the rows IT has, not on a set common to all of
    them, so one poorly measured candidate cannot silently shrink the sample the
    others are judged on. `n` and `coverage` are reported per row for exactly
    that reason, and `coverage` is what decides whether it can join the path.
    """
    base = train[list(P_FEATURES) + ["followup_years", "cvd_death", "wtmec2yr",
                                     "design_cluster"]].dropna()
    denom = len(base)

    absent = [c.name for c in CANDIDATES if c.name not in train.columns]
    if absent:
        raise KeyError(
            f"declared candidates missing from the frame: {absent}. Skipping "
            f"them silently would shrink n_candidates -- a number the report, "
            f"the index card and the README all print -- with no other symptom.")

    rows = []
    for c in CANDIDATES:
        have = base.index.intersection(train[c.name].dropna().index)
        coverage = len(have) / denom if denom else 0.0
        stat = (_wald(train.loc[have], list(P_FEATURES), c.name)
                if len(have) > MIN_ROWS_TO_FIT else None)
        rows.append({
            "variable": c.name, "label": c.label, "e2_status": c.e2_status,
            "n": int(len(have)), "coverage": round(coverage, 3),
            "events": int(base.loc[have, "cvd_death"].sum()),
            "hr_per_sd": round(stat["hr_per_sd"], 3) if stat else np.nan,
            "z": round(stat["z"], 2) if stat else np.nan,
            "wald": round(stat["wald"], 2) if stat else np.nan,
            "in_pool": bool(stat and stat["wald"] >= WALD_THRESHOLD
                            and coverage >= MIN_COVERAGE),
            # Every state gets a name, and the names distinguish things that
            # are genuinely different. An empty string here became NaN on the
            # way through CSV -- and NaN is truthy, so the renderer's fallback
            # never fired and nine rows of the published table read "nan".
            # "did not fit" also used to cover a candidate that was never
            # OFFERED to the fitter, which is a false statement about what the
            # code did, in a column a reader uses to judge the screen.
            "note": ("only %d rows, below the %d needed to attempt a fit"
                     % (len(have), MIN_ROWS_TO_FIT)
                     if len(have) <= MIN_ROWS_TO_FIT else
                     "the fit did not converge" if stat is None else
                     "observed for %.0f%% of the training rows, below the %.0f%% gate"
                     % (100 * coverage, 100 * MIN_COVERAGE)
                     if coverage < MIN_COVERAGE else
                     "below the Wald threshold" if stat["wald"] < WALD_THRESHOLD
                     else "entered the pool"),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("wald", ascending=False, na_position="last")


def forward_select(train: pd.DataFrame, pool: list[str]) -> pd.DataFrame:
    """Greedy forward selection on top of P_FEATURES, on the training cycles.

    Recorded as a path rather than a set: which variable entered at which step,
    and what it bought. A set hides that the second choice is conditional on the
    first, which is the whole reason a marginal ranking and a selected set can
    disagree.

    One common analysis set for the whole path -- complete on every pooled
    candidate -- so a step is never credited with an improvement that came from
    the sample growing as a variable dropped out. The coverage gate upstream is
    what keeps that set from collapsing.
    """
    cols = list(P_FEATURES) + list(pool)
    keep = ["followup_years", "cvd_death", "wtmec2yr", "design_cluster"]
    common = train[cols + keep].dropna()
    n, events = int(len(common)), int(common["cvd_death"].sum())

    chosen: list[str] = []
    failed: list[str] = []
    remaining = list(pool)
    rows = [{"step": 0, "entered": "(the eleven already in the model)",
             "z": np.nan, "wald": np.nan, "n": n, "events": events,
             "selected": True}]

    while remaining and len(chosen) < MAX_SELECTED:
        scored = []
        for v in remaining:
            if EXCLUDES.get(v, set()) & set(chosen):
                continue        # linearly dependent on something already in
            stat = _wald(common, list(P_FEATURES) + chosen, v)
            if stat is None:
                # A candidate that will not fit alongside what is already chosen
                # is a fact about the path. Dropping it silently would change
                # which variable the report says was selected, with nothing
                # anywhere recording that another had been considered.
                failed.append(f"{v} (step {len(chosen) + 1})")
                remaining.remove(v)
                continue
            scored.append((stat["wald"], v, stat["z"]))
        if not scored:
            break
        wald, best, z = max(scored)
        entered = wald >= WALD_THRESHOLD
        rows.append({"step": len(chosen) + 1, "entered": best,
                     "z": round(z, 2), "wald": round(wald, 2),
                     "n": n, "events": events, "selected": bool(entered)})
        if not entered:
            break
        chosen.append(best)
        remaining.remove(best)

    out = pd.DataFrame(rows)
    out.attrs["failed"] = failed
    return out


def screen(cohort: pd.DataFrame) -> dict:
    """Run the whole screen and return everything it produced.

    `selected` may legitimately be empty. That is a result -- it says the eleven
    already carry what this cohort can see -- and the report must be able to say
    so rather than assuming otherwise.
    """
    d = candidate_frame(cohort)
    train = d[d["cycle"].isin(TRAIN_CYCLES)]

    ranking = marginal_ranking(train)
    pool = [r.variable for r in ranking.itertuples() if r.in_pool]
    path = forward_select(train, pool) if pool else pd.DataFrame()
    selected = [r.entered for r in path.itertuples()
                if r.step > 0 and r.selected] if len(path) else []

    return {
        "ranking": ranking,
        "path": path,
        "selected": selected,
        "pool": pool,
        "n_train": int(len(train)),
        "events_train": int(train["cvd_death"].sum()),
        "wald_threshold": WALD_THRESHOLD,
        "min_coverage": MIN_COVERAGE,
    }
