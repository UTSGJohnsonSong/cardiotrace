"""
Fill the README's Key Findings block from reports/results.json so the headline
numbers can never drift from the actual pipeline output. Run after run_pipeline.py:

    python scripts/render_readme.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
res = json.loads((ROOT / "reports" / "results.json").read_text())

prev = res["prevalence"]
first, last = prev["any_cvd_first"], prev["any_cvd_last"]
equity = res.get("equity", {})
covid = res.get("covid", {})
models = res.get("models", {})

# Best-performing outcome by PR-AUC
best = models.get("best_by_outcome", {})
LABEL = {"has_heart_failure": "heart failure", "has_mi": "heart attack",
         "has_chd": "coronary heart disease", "has_angina": "angina",
         "has_stroke": "stroke", "has_any_cvd": "any CVD"}
top_outcome = max(best, key=lambda o: best[o]["roc_auc"]) if best else None

lines = ["## Key Findings", ""]

lines.append(f"- **Any-CVD prevalence, survey-weighted:** {first['pct']}% of US adults in "
             f"{first['cycle']} → {last['pct']}% in {last['cycle']} "
             f"(pooled N = {prev['total_n']:,} adults across 11 cycles).")

if top_outcome:
    b = best[top_outcome]
    lines.append(f"- **Best model:** {b['model'].replace('_',' ').title()} predicts "
                 f"{LABEL.get(top_outcome, top_outcome)} at ROC-AUC {b['roc_auc']} / "
                 f"PR-AUC {b['pr_auc']} (5-fold cross-validated, survey design retained).")

if models.get("shap_top_features"):
    tops = ", ".join(f["feature"] for f in models["shap_top_features"][:3])
    lines.append(f"- **Top risk drivers (SHAP, Any-CVD model):** {tops}.")

if equity.get("latest_by_race"):
    ranked = sorted(equity["latest_by_race"].items(), key=lambda kv: (kv[1] is None, -(kv[1] or 0)))
    hi, lo = ranked[0], ranked[-1]
    lines.append(f"- **Health equity ({equity.get('latest_cycle','latest cycle')}):** "
                 f"Any-CVD prevalence ranges from {hi[1]}% ({hi[0]}) to {lo[1]}% ({lo[0]}).")

if "pre_pandemic" in covid and "post_pandemic" in covid:
    pre, post = covid["pre_pandemic"], covid["post_pandemic"]
    lines.append(f"- **Pre vs post-COVID:** Any-CVD {pre['pct_any_cvd']}% → {post['pct_any_cvd']}%; "
                 f"mean HbA1c {pre['mean_hba1c']} → {post['mean_hba1c']}%; "
                 f"mean BMI {pre['mean_bmi']} → {post['mean_bmi']}.")

lines += ["", "_Figures in [`reports/figures/`](reports/figures); "
          "full numbers in [`reports/results.json`](reports/results.json)._"]

block = "\n".join(lines)
readme = (ROOT / "README.md").read_text(encoding="utf-8")
start, end = "<!-- KEY_FINDINGS_START -->", "<!-- KEY_FINDINGS_END -->"
pre_txt = readme.split(start)[0] + start + "\n"
post_txt = "\n" + end + readme.split(end)[1]
readme = pre_txt + block + post_txt

# The test-count badge was the last hand-typed statistic on the front page, and
# it had gone stale: it read 85 while the suite carried 114. `tests/conftest.py`
# writes the real number on every full run, so read it rather than trusting
# whoever last remembered to edit the badge.
summary = ROOT / "reports" / "test_summary.json"
if summary.exists():
    t = json.loads(summary.read_text(encoding="utf-8"))
    if t["failed"] == 0 and t["exit_status"] == 0:
        readme = re.sub(r"badge/tests-\d+%20passing-brightgreen",
                        f"badge/tests-{t['collected']}%20passing-brightgreen",
                        readme, count=1)
        print(f"test badge: {t['collected']} passing")
    else:
        print(f"test badge NOT updated: last full run had {t['failed']} failure(s)")
else:
    print("test badge NOT updated: no reports/test_summary.json; run the suite")

(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README Key Findings updated:")
print(block)
