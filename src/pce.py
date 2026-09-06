"""Prespecified historical PCE benchmark; see docs/pce-benchmark.md §3.5.

Published probabilities target hard ASCVD, never CVD mortality. The mortality
adaptation estimates baselines from training cycles only, keeping PCE slopes.
"""
from pathlib import Path

import numpy as np
import pandas as pd

REFERENCE = Path(__file__).resolve().parents[1] / "data/reference/pce_coefficients.csv"
GROUPS = ("white_women", "aa_women", "white_men", "aa_men")
INPUTS = ["age", "sex", "race_black", "total_cholesterol", "hdl_cholesterol",
          "systolic_bp", "bp_treated", "diabetes_dx", "current_smoker"]
TERMS = ("ln_age", "ln_age_squared", "ln_total_cholesterol",
         "ln_age_x_ln_total_cholesterol", "ln_hdl_c", "ln_age_x_ln_hdl_c",
         "ln_treated_systolic_bp", "ln_age_x_ln_treated_systolic_bp",
         "ln_untreated_systolic_bp", "ln_age_x_ln_untreated_systolic_bp",
         "current_smoker", "ln_age_x_current_smoker", "diabetes")
PARAMETERS = ("mean_linear_predictor", "baseline_survival_10y")


def coefficients(path=REFERENCE):
    table = pd.read_csv(path, keep_default_na=False)
    expected = {(g, k, v) for g in GROUPS for k, variables in
                (("coefficient", TERMS), ("parameter", PARAMETERS)) for v in variables}
    keys = list(table[["group", "kind", "variable"]].itertuples(index=False, name=None))
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("PCE reference must declare all 60 unique coefficient/parameter rows")
    unused = {
        "white_women": {"ln_age_x_ln_treated_systolic_bp", "ln_age_x_ln_untreated_systolic_bp"},
        "aa_women": {"ln_age_squared", "ln_age_x_ln_total_cholesterol", "ln_age_x_current_smoker"},
        "white_men": {"ln_age_squared", "ln_age_x_ln_treated_systolic_bp", "ln_age_x_ln_untreated_systolic_bp"},
        "aa_men": {"ln_age_squared", "ln_age_x_ln_total_cholesterol", "ln_age_x_ln_hdl_c",
                   "ln_age_x_ln_treated_systolic_bp", "ln_age_x_ln_untreated_systolic_bp",
                   "ln_age_x_current_smoker"},
    }
    declared_unused = table.apply(lambda r: r.variable in unused[r.group], axis=1)
    if not (table.value.eq("NA") == declared_unused).all():
        raise ValueError("Only explicitly unused PCE terms may have NA coefficients")
    table["value"] = pd.to_numeric(table.value.replace("NA", "0"), errors="raise")
    if not np.isfinite(table.value).all():
        raise ValueError("PCE coefficients and parameters must be finite")
    survival = table.loc[table.variable == "baseline_survival_10y", "value"]
    if not ((survival > 0) & (survival < 1)).all():
        raise ValueError("PCE baseline survival must be between zero and one")
    return {g: table[table.group == g].set_index("variable").value for g in GROUPS}


def score(raw: pd.DataFrame, *, other_ethnicities=False) -> pd.DataFrame:
    """Complete, unprepared inputs only; never silently map unknown ethnicity."""
    if "design_cluster" in raw:
        raise ValueError("PCE requires raw measured SBP, not a prepared model frame")
    if raw[INPUTS + ["race_eth"]].isna().any().any():
        raise ValueError("PCE requires complete inputs and known ethnicity")
    known = {"NH White", "NH Black", "Mexican American", "Other Hispanic", "NH Asian", "Other/Multi"}
    if not raw.race_eth.isin(known).all():
        raise ValueError("Unknown ethnicity; supply an explicit mapping")
    if not other_ethnicities and not raw.race_eth.isin(["NH White", "NH Black"]).all():
        raise ValueError("Primary PCE analysis is limited to NH White/NH Black")
    if not raw.sex.isin(["Female", "Male"]).all() or not raw.age.between(40, 79).all():
        raise ValueError("PCE requires known sex and ages 40–79")
    for c in ["race_black", "bp_treated", "diabetes_dx", "current_smoker"]:
        if not raw[c].isin([0, 1]).all():
            raise ValueError(f"{c} must be coded 0/1")
    if not ((raw.race_eth == "NH Black").astype(int) == raw.race_black).all():
        raise ValueError("race_eth and race_black disagree")
    continuous = raw[["age", "total_cholesterol", "hdl_cholesterol", "systolic_bp"]]
    if not np.isfinite(continuous.to_numpy(float)).all() or (continuous <= 0).any().any():
        raise ValueError("PCE logarithms require finite positive measurements")
    la, tc, hdl, sbp = (np.log(continuous[c]) for c in continuous)
    treated, smoking = raw.bp_treated, raw.current_smoker
    terms = pd.DataFrame(dict(zip(TERMS, [la, la**2, tc, la*tc, hdl, la*hdl,
        sbp*treated, la*sbp*treated, sbp*(1-treated), la*sbp*(1-treated),
        smoking, la*smoking, raw.diabetes_dx])), index=raw.index)
    group = pd.Series(np.where(raw.race_black == 1, "aa_", "white_")
                      + np.where(raw.sex == "Male", "men", "women"), index=raw.index)
    out = pd.DataFrame({"group": group}, index=raw.index)
    for g, values in coefficients().items():
        rows = group == g
        lp = terms.loc[rows] @ values.reindex(TERMS).fillna(0)
        centered = lp - values["mean_linear_predictor"]
        out.loc[rows, "lp"] = lp
        out.loc[rows, "centered_lp"] = centered
        out.loc[rows, "risk_10y_ascvd"] = -np.expm1(
            np.log(values["baseline_survival_10y"]) * np.exp(centered))
    return out


class MortalityRecalibration:
    """Training-only weighted Breslow offsets, separately by PCE race/sex group.

    CVD slope is fixed at the published LP. The competing hazard is group-only.
    Jump integration follows the existing S(t-) dH1 convention.
    """
    def fit(self, raw, scores):
        _validate_outcomes(raw)
        _validate_scores(scores)
        if not raw.index.equals(scores.index):
            raise ValueError("Misaligned training scores")
        self.baselines = {}
        for group in GROUPS:
            d = raw.loc[scores.group == group]
            if d.empty or d.cvd_death.sum() == 0 or d.competing_death.sum() == 0:
                raise ValueError(f"Training group {group} lacks both causes of death")
            lp = scores.loc[d.index, "centered_lp"]
            time, weight = d.followup_years.to_numpy(), d.wtmec2yr.to_numpy()
            rr = np.exp(lp.to_numpy())
            rows = []
            for t in np.sort(d.loc[(d.cvd_death == 1) | (d.competing_death == 1), "followup_years"].unique()):
                at = time >= t
                now = time == t
                h1 = weight[now & (d.cvd_death.to_numpy() == 1)].sum() / (weight[at]*rr[at]).sum()
                h2 = weight[now & (d.competing_death.to_numpy() == 1)].sum() / weight[at].sum()
                rows.append({"time": float(t), "dh_cvd": float(h1), "dh_competing": float(h2)})
            self.baselines[group] = rows
        return self

    def predict(self, scores, horizon):
        if not hasattr(self, "baselines"):
            raise RuntimeError("fit() first")
        _validate_scores(scores)
        _validate_horizon(horizon)
        result = pd.Series(index=scores.index, dtype=float)
        for group in GROUPS:
            idx = scores.index[scores.group == group]
            rr = np.exp(scores.loc[idx, "centered_lp"].to_numpy())
            surv, cif = np.ones(len(idx)), np.zeros(len(idx))
            for row in self.baselines[group]:
                if row["time"] > horizon:
                    break
                dh1, dh2 = rr * row["dh_cvd"], row["dh_competing"]
                cif += surv * dh1
                surv *= np.exp(-(dh1 + dh2))
            if ((cif < 0) | (cif > 1) | ~np.isfinite(cif)).any():
                raise ValueError("Mortality offset prediction outside probability support")
            result.loc[idx] = cif
        return result


def _validate_horizon(horizon):
    if not np.isfinite(horizon) or horizon <= 0:
        raise ValueError("Horizon must be finite and positive")


def _validate_scores(scores):
    if (not scores.index.is_unique or not scores.group.isin(GROUPS).all()
            or not np.isfinite(scores.centered_lp).all()
            or not np.isfinite(np.exp(scores.centered_lp)).all()):
        raise ValueError("Invalid group, index or linear predictor")


def _validate_outcomes(d):
    cols = ["followup_years", "cvd_death", "competing_death", "wtmec2yr"]
    if d.empty or not d.index.is_unique or not np.isfinite(d[cols]).all().all():
        raise ValueError("Missing outcome/design input or empty/duplicate-index sample")
    if (d.wtmec2yr <= 0).any() or (d.followup_years < 0).any():
        raise ValueError("Positive survey weights and nonnegative follow-up required")
    if (not d[["cvd_death", "competing_death"]].isin([0, 1]).all().all()
            or ((d.cvd_death + d.competing_death) > 1).any()):
        raise ValueError("Outcome indicators must be binary and mutually exclusive")


def observed_cif(d, horizon):
    from src.survival import aalen_johansen_cif
    if d.empty:
        return 0.
    _validate_outcomes(d)
    _validate_horizon(horizon)
    events = np.where(d.cvd_death == 1, 1, np.where(d.competing_death == 1, 2, 0))
    curve = aalen_johansen_cif(d.followup_years, events, d.wtmec2yr)
    before = curve.loc[curve.t <= horizon, "cif"]
    return float(before.iloc[-1]) if len(before) else 0.


def decision_curve(risks: dict[str, pd.Series], d: pd.DataFrame, horizon: float,
                   thresholds=None, *, censoring="error") -> pd.DataFrame:
    """Weighted horizon net benefit; refuse unknown horizon status."""
    _validate_outcomes(d)
    _validate_horizon(horizon)
    known = (d.followup_years >= horizon) | (d.cvd_death == 1) | (d.competing_death == 1)
    if censoring not in ("error", "aalen_johansen"):
        raise ValueError("Unknown censoring method")
    if not known.all() and censoring == "error":
        raise ValueError("Early censoring: horizon outcome is unknown; use a censoring-aware estimator")
    thresholds = np.arange(0.005, 0.1001, 0.005) if thresholds is None else np.asarray(thresholds)
    if not np.isfinite(thresholds).all() or ((thresholds <= 0) | (thresholds >= 1)).any():
        raise ValueError("Thresholds must be strictly between zero and one")
    y = ((d.cvd_death == 1) & (d.followup_years <= horizon)).to_numpy()
    w = d.wtmec2yr.to_numpy(float)
    rows = []
    for name, p in {**risks, "treat_all": pd.Series(1., index=d.index),
                    "treat_none": pd.Series(0., index=d.index)}.items():
        if not p.index.equals(d.index) or not np.isfinite(p).all() or not p.between(0, 1).all():
            raise ValueError(f"Invalid or misaligned probabilities: {name}")
        for threshold in thresholds:
            positive = p.to_numpy() >= threshold
            fraction = float(w[positive].sum() / w.sum())
            tp = (fraction * observed_cif(d.loc[positive], horizon) if not known.all()
                  else float(w[positive & y].sum() / w.sum()))
            fp = fraction - tp
            rows.append({"arm": name, "horizon_years": horizon, "threshold": float(threshold),
                         "net_benefit": tp - fp * threshold / (1-threshold),
                         "weighted_true_positive_fraction": tp,
                         "weighted_false_positive_fraction": fp,
                         "early_censored": int((~known).sum()),
                         "estimator": "weighted AJ" if not known.all() else "fully observed weighted binary"})
    return pd.DataFrame(rows)
