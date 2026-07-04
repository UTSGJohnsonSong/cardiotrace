"""
Feature selection pipeline for CardioTrace.
Three-layer funnel: domain knowledge → statistical filtering → VIF.
"""

import pandas as pd
import numpy as np
from scipy.stats import chi2_contingency, pointbiserialr
from sklearn.feature_selection import mutual_info_classif
import logging

log = logging.getLogger(__name__)

# Layer 1: Domain knowledge — known CVD risk factors (always include)
DOMAIN_FEATURES = [
    "age",
    "gender",
    "race_ethnicity",
    "education_level",
    "poverty_income_ratio",
    "systolic_bp_avg",
    "diastolic_bp_avg",
    "hypertension_diagnosed",
    "hypertension_on_meds",
    "hypertension_flag",
    "bmi",
    "waist_cm",
    "obese",
    "diabetes_diagnosed",
    "diabetes_flag",
    "current_smoker",
    "cigarettes_per_day",
    "total_cholesterol",
    "hdl_cholesterol",
    "ldl_cholesterol",
    "triglycerides",
    "non_hdl_cholesterol",
    "fasting_glucose",
    "hba1c",
    "crp",
    "creatinine",
    "vigorous_activity",
    "sedentary_minutes_per_day",
]

CATEGORICAL_FEATURES = [
    "gender", "race_ethnicity", "education_level",
    "hypertension_diagnosed", "hypertension_flag",
    "diabetes_diagnosed", "diabetes_flag",
    "current_smoker", "obese", "vigorous_activity",
    "hypertension_on_meds", "on_insulin",
]

CONTINUOUS_FEATURES = [
    "age", "poverty_income_ratio", "systolic_bp_avg", "diastolic_bp_avg",
    "bmi", "waist_cm", "cigarettes_per_day", "total_cholesterol",
    "hdl_cholesterol", "ldl_cholesterol", "triglycerides", "non_hdl_cholesterol",
    "fasting_glucose", "hba1c", "crp", "creatinine", "uric_acid",
    "sedentary_minutes_per_day",
]


def filter_by_missing_rate(df: pd.DataFrame, threshold: float = 0.30) -> list[str]:
    """Drop columns with > threshold missing rate."""
    missing_rate = df.isnull().mean()
    keep = missing_rate[missing_rate <= threshold].index.tolist()
    dropped = [c for c in df.columns if c not in keep]
    if dropped:
        log.info(f"Dropped {len(dropped)} cols with >{threshold*100:.0f}% missing: {dropped[:5]}...")
    return keep


def chi2_filter(
    df: pd.DataFrame,
    cat_cols: list[str],
    target: str,
    p_thresh: float = 0.05
) -> list[str]:
    """Chi-square test: keep categorical features associated with target."""
    keep = []
    for col in cat_cols:
        if col not in df.columns:
            continue
        try:
            ct = pd.crosstab(df[col].fillna("missing"), df[target])
            _, p, _, _ = chi2_contingency(ct)
            if p < p_thresh:
                keep.append(col)
        except Exception as e:
            log.debug(f"chi2 failed for {col}: {e}")
    return keep


def correlation_filter(
    df: pd.DataFrame,
    num_cols: list[str],
    target: str,
    p_thresh: float = 0.05,
    r_thresh: float = 0.03
) -> list[str]:
    """Point-biserial correlation: keep continuous features correlated with binary target."""
    keep = []
    for col in num_cols:
        if col not in df.columns:
            continue
        try:
            mask = df[[col, target]].dropna()
            r, p = pointbiserialr(mask[target], mask[col])
            if p < p_thresh and abs(r) > r_thresh:
                keep.append(col)
        except Exception as e:
            log.debug(f"correlation failed for {col}: {e}")
    return keep


def mutual_info_rank(
    df: pd.DataFrame,
    feature_cols: list[str],
    target: str,
    top_n: int = 30
) -> pd.DataFrame:
    """Rank features by mutual information with target."""
    X = df[feature_cols].copy()
    y = df[target].copy()

    mask = y.notna()
    X, y = X[mask], y[mask]

    # Simple median imputation for MI calculation
    X = X.fillna(X.median(numeric_only=True))

    mi_scores = mutual_info_classif(X, y, random_state=42)
    result = pd.DataFrame({"feature": feature_cols, "mi_score": mi_scores})
    return result.sort_values("mi_score", ascending=False).head(top_n)


def vif_filter(df: pd.DataFrame, cols: list[str], thresh: float = 10.0) -> list[str]:
    """Remove features with VIF > threshold (multicollinearity)."""
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    X = df[cols].dropna()
    if len(X) < 10:
        return cols

    keep = list(cols)
    while True:
        X_arr = X[keep].values.astype(float)
        vifs = [variance_inflation_factor(X_arr, i) for i in range(len(keep))]
        max_vif = max(vifs)
        if max_vif <= thresh:
            break
        worst = keep[vifs.index(max_vif)]
        log.info(f"VIF filter: removing {worst} (VIF={max_vif:.1f})")
        keep.remove(worst)
    return keep


def select_features(
    df: pd.DataFrame,
    target: str,
    additional_cols: list[str] | None = None,
    missing_thresh: float = 0.30,
    p_thresh: float = 0.05,
) -> list[str]:
    """
    Full three-layer feature selection pipeline.
    Returns list of selected feature column names.
    """
    log.info(f"Feature selection for target: {target}")
    log.info(f"Starting with {len(df.columns)} columns")

    # Layer 0: filter by missing rate
    valid_cols = filter_by_missing_rate(df, threshold=missing_thresh)
    df_valid = df[valid_cols]

    # Layer 1: domain knowledge features (always keep if available)
    domain_available = [f for f in DOMAIN_FEATURES if f in df_valid.columns]

    # Layer 2: statistical filter on remaining columns
    remaining = [c for c in df_valid.columns
                 if c not in domain_available
                 and c != target
                 and c not in ["seqn", "cycle", "survey_weight_2yr",
                                "survey_weight_pooled", "psu", "strata"]]

    cat_extra = [c for c in remaining if c in CATEGORICAL_FEATURES]
    num_extra = [c for c in remaining if c in CONTINUOUS_FEATURES]

    stat_cat = chi2_filter(df_valid, cat_extra, target, p_thresh)
    stat_num = correlation_filter(df_valid, num_extra, target, p_thresh)

    # Combine
    candidate_features = list(set(domain_available + stat_cat + stat_num))
    if additional_cols:
        candidate_features += [c for c in additional_cols if c in df.columns]
    candidate_features = [f for f in candidate_features if f in df.columns and f != target]

    # Layer 3: VIF filter (continuous only)
    num_candidates = [f for f in candidate_features if f in CONTINUOUS_FEATURES]
    num_keep = vif_filter(df_valid, num_candidates)
    cat_candidates = [f for f in candidate_features if f not in CONTINUOUS_FEATURES]

    final_features = list(set(num_keep + cat_candidates))
    log.info(f"Final feature set: {len(final_features)} features")
    return sorted(final_features)
