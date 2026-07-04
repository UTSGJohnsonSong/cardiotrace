"""
Modeling pipeline for CardioTrace.
Trains Logistic Regression + XGBoost for each CVD outcome.
Outputs metrics, SHAP values, and risk scores.
"""

import pandas as pd
import numpy as np
import shap
import joblib
import logging
from pathlib import Path

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    f1_score, classification_report, confusion_matrix
)
from xgboost import XGBClassifier

log = logging.getLogger(__name__)

CVD_TARGETS = [
    "has_heart_failure",
    "has_mi",
    "has_chd",
    "has_angina",
    "has_stroke",
    "has_any_cvd",
]

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)


def build_preprocessor(cat_cols: list[str], num_cols: list[str]) -> ColumnTransformer:
    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    return ColumnTransformer([
        ("num", num_pipe, num_cols),
        ("cat", cat_pipe, cat_cols),
    ], remainder="drop")


def get_models(scale_pos_weight: float = 1.0) -> dict:
    """Model zoo. `scale_pos_weight` is computed per target as neg/pos to
    correct the ~20:1 class imbalance in the loss function itself (no SMOTE —
    synthetic minority oversampling would distort epidemiological prevalence)."""
    return {
        "logistic_regression": LogisticRegression(
            class_weight="balanced",
            max_iter=2000,
            C=0.1,
            random_state=42,
        ),
        "xgboost": XGBClassifier(
            scale_pos_weight=scale_pos_weight,
            n_estimators=400,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            reg_lambda=1.0,
            eval_metric="aucpr",
            random_state=42,
            n_jobs=-1,
        ),
    }


def find_best_threshold(y_true, y_prob) -> float:
    """Find probability threshold that maximizes F1."""
    from sklearn.metrics import precision_recall_curve
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)
    f1s = np.where(
        (precisions + recalls) > 0,
        2 * precisions * recalls / (precisions + recalls),
        0
    )
    return float(thresholds[np.argmax(f1s[:-1])])


def evaluate(y_true, y_prob, threshold: float = 0.5) -> dict:
    y_pred = (y_prob >= threshold).astype(int)
    return {
        "roc_auc":    round(roc_auc_score(y_true, y_prob), 4),
        "pr_auc":     round(average_precision_score(y_true, y_prob), 4),
        "f1":         round(f1_score(y_true, y_pred, zero_division=0), 4),
        "threshold":  round(threshold, 3),
        "n_positive": int(y_true.sum()),
        "n_total":    int(len(y_true)),
        "prevalence": round(y_true.mean(), 4),
    }


def train_target(
    df: pd.DataFrame,
    target: str,
    feature_cols: list[str],
    cat_cols: list[str],
    cv_folds: int = 5,
) -> dict:
    """Train all models for one CVD target. Returns metrics + SHAP values."""

    mask = df[target].notna()
    X = df.loc[mask, feature_cols]
    y = df.loc[mask, target].astype(int)

    log.info(f"\n{'='*50}")
    log.info(f"Target: {target} | N={len(y)} | Prevalence={y.mean():.2%}")

    num_cols = [c for c in feature_cols if c not in cat_cols]
    preprocessor = build_preprocessor(cat_cols, num_cols)

    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    spw = (n_neg / n_pos) if n_pos else 1.0

    results = {}
    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)

    for model_name, clf in get_models(scale_pos_weight=spw).items():
        pipe = Pipeline([
            ("prep",  preprocessor),
            ("model", clf),
        ])

        y_prob = cross_val_predict(pipe, X, y, cv=skf, method="predict_proba")[:, 1]
        threshold = find_best_threshold(y, y_prob)
        metrics = evaluate(y, y_prob, threshold)
        metrics["model"] = model_name
        metrics["target"] = target

        log.info(f"  {model_name}: ROC-AUC={metrics['roc_auc']} | PR-AUC={metrics['pr_auc']} | F1={metrics['f1']}")

        # Save the final model (trained on full data)
        pipe.fit(X, y)
        model_path = MODELS_DIR / f"{target}_{model_name}.joblib"
        joblib.dump(pipe, model_path)

        results[model_name] = {
            "metrics": metrics,
            "pipeline": pipe,
            "y_prob": y_prob,
            "threshold": threshold,
        }

    return results


def compute_shap(
    pipeline: Pipeline,
    X: pd.DataFrame,
    cat_cols: list[str],
    model_name: str = "xgboost",
    sample_n: int = 2000,
) -> tuple[np.ndarray, list[str]]:
    """Compute SHAP values for tree-based models."""
    preprocessor = pipeline.named_steps["prep"]
    model = pipeline.named_steps["model"]

    X_transformed = preprocessor.transform(X)
    feature_names = (
        pipeline.named_steps["prep"]
        .get_feature_names_out()
        .tolist()
    )

    # Sample for speed
    idx = np.random.choice(len(X_transformed), min(sample_n, len(X_transformed)), replace=False)
    X_sample = X_transformed[idx]

    if model_name in ("xgboost", "random_forest"):
        explainer = shap.TreeExplainer(model)
    else:
        explainer = shap.LinearExplainer(model, X_sample)

    shap_values = explainer.shap_values(X_sample)
    if isinstance(shap_values, list):
        shap_values = shap_values[1]  # class 1 for binary

    return shap_values, feature_names


def compute_risk_score(y_prob: np.ndarray) -> np.ndarray:
    """Scale predicted probabilities to 0-100 risk score."""
    return np.round(y_prob * 100, 1)


def run_all_targets(
    df: pd.DataFrame,
    feature_cols: list[str],
    cat_cols: list[str],
    targets: list[str] | None = None,
) -> pd.DataFrame:
    """Train all CVD targets and return a summary metrics DataFrame."""
    targets = targets or CVD_TARGETS
    all_metrics = []

    for target in targets:
        if target not in df.columns:
            log.warning(f"Target {target} not in DataFrame, skipping")
            continue
        results = train_target(df, target, feature_cols, cat_cols)
        for model_name, res in results.items():
            all_metrics.append(res["metrics"])

    return pd.DataFrame(all_metrics)
