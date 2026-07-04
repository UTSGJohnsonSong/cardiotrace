"""
Generate the four analysis notebooks from a single source of truth.

Each notebook is a thin narrative layer over the tested functions in src/ — the
heavy logic lives in src/analysis.py and src/model.py, so notebooks stay
readable and never drift from the pipeline. Run:

    python scripts/build_notebooks.py     # writes notebooks/*.ipynb
    jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
"""

from pathlib import Path

import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

NB_DIR = Path(__file__).parent.parent / "notebooks"
NB_DIR.mkdir(exist_ok=True)

BOOT = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath('..'))\n"
    "from dotenv import load_dotenv; load_dotenv('../.env')\n"
    "import pandas as pd, numpy as np, matplotlib.pyplot as plt\n"
    "pd.set_option('display.width', 120); pd.set_option('display.max_columns', 40)\n"
    "from src.etl import get_engine\n"
    "engine = get_engine()\n"
    "df = pd.read_sql('SELECT * FROM mart.mart_cv_master', engine)\n"
    "print(f'mart_cv_master: {df.shape[0]:,} rows x {df.shape[1]} cols')"
)


def build(name, title, cells):
    nb = new_notebook()
    nb.cells = [new_markdown_cell(f"# {title}"), new_code_cell(BOOT)] + cells
    nb.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                   "language_info": {"name": "python"}}
    nbf.write(nb, NB_DIR / name)
    print("wrote", name)


build("01_eda.ipynb", "CardioTrace 01 — Exploratory Data Analysis", [
    new_markdown_cell("## Cohort overview\nAdults 20+, pooled 1999–2023. NHANES is a complex "
                      "probability sample, so every population estimate below is survey-weighted."),
    new_code_cell("df[['age','bmi','systolic_bp_avg','total_cholesterol','hba1c']].describe().round(1)"),
    new_code_cell("df.groupby('cycle')['seqn'].count().rename('n_adults').to_frame()"),
    new_markdown_cell("## Outcome prevalence (survey-weighted)"),
    new_code_cell("import src.analysis as A\n"
                  "for oc,label in A.CVD_OUTCOMES.items():\n"
                  "    t = A.weighted_prevalence(df, oc)\n"
                  "    print(f'{label:26s} {t[\"prevalence_pct\"].iloc[0]:5.2f}%  (n_cases={int(t[\"n_cases\"].iloc[0])})')"),
    new_markdown_cell("## Missingness by feature"),
    new_code_cell("(df.isna().mean()*100).sort_values(ascending=False).head(20).round(1)"),
])

build("02_variable_selection.ipynb", "CardioTrace 02 — Feature Selection", [
    new_markdown_cell("Three-layer funnel: **domain knowledge → statistical filtering "
                      "(chi-square / point-biserial) → VIF** to drop collinear features."),
    new_code_cell("import src.features as F\n"
                  "selected = F.select_features(df, 'has_any_cvd')\n"
                  "print(f'{len(selected)} features selected for has_any_cvd:')\n"
                  "selected"),
    new_markdown_cell("## Mutual information ranking"),
    new_code_cell("cols = [c for c in F.CONTINUOUS_FEATURES if c in df.columns]\n"
                  "F.mutual_info_rank(df.dropna(subset=['has_any_cvd']), cols, 'has_any_cvd', top_n=15)"),
])

build("03_modeling.ipynb", "CardioTrace 03 — Modeling", [
    new_markdown_cell("Logistic Regression (baseline) vs XGBoost for each CVD outcome. "
                      "Class imbalance (~20:1) handled with `class_weight`/`scale_pos_weight` — "
                      "**no SMOTE**, which would distort epidemiological prevalence. Evaluation "
                      "uses PR-AUC and ROC-AUC (accuracy is meaningless at 5% prevalence)."),
    new_code_cell("import src.model as M, src.analysis as A\n"
                  "from run_pipeline import NUM_FEATURES, CAT_FEATURES\n"
                  "feats = [f for f in NUM_FEATURES+CAT_FEATURES if f in df.columns]\n"
                  "cat = [f for f in CAT_FEATURES if f in df.columns]\n"
                  "res = M.train_target(df, 'has_any_cvd', feats, cat)\n"
                  "pd.DataFrame([r['metrics'] for r in res.values()])"),
])

build("04_shap_analysis.ipynb", "CardioTrace 04 — SHAP Interpretability", [
    new_markdown_cell("SHAP (TreeExplainer) attributes each prediction to its drivers — the "
                      "global summary shows which risk factors matter most across the population."),
    new_code_cell("import shap, src.model as M, src.analysis as A\n"
                  "from run_pipeline import NUM_FEATURES, CAT_FEATURES\n"
                  "feats = [f for f in NUM_FEATURES+CAT_FEATURES if f in df.columns]\n"
                  "cat = [f for f in CAT_FEATURES if f in df.columns]\n"
                  "res = M.train_target(df, 'has_any_cvd', feats, cat)\n"
                  "pipe = res['xgboost']['pipeline']\n"
                  "X = df.loc[df['has_any_cvd'].notna(), feats].sample(2000, random_state=42)\n"
                  "Xt = pipe.named_steps['prep'].transform(X)\n"
                  "names = [f.split('__')[-1] for f in pipe.named_steps['prep'].get_feature_names_out()]\n"
                  "sv = shap.TreeExplainer(pipe.named_steps['model']).shap_values(Xt)\n"
                  "shap.summary_plot(sv, Xt, feature_names=names, max_display=12)"),
])

print("done")
