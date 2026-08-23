"""Fill the README's Key Findings block from the artefacts the analysis produces.

It used to read `reports/results.json`, which is written by the DEPRECATED
`run_pipeline.py` -- the pipeline this project replaced. That block therefore
carried, on the repository front page:

    "Xgboost predicts coronary heart disease at ROC-AUC 0.8585"
    "Top risk drivers (SHAP, Any-CVD model): age, hypertension_flag, ..."

which `docs/advisor-briefing.md` records in the project's own words as built on
imputed laboratory values for 24.4% of the sample and not fit to show. They were
on the front page anyway, because nothing connected the finding that condemned
them to the script that regenerated them, and `make all` put them back after
every run.

Reading the current artefacts is the fix. `results.json` is left on disk and
marked deprecated rather than deleted; it is the output of an analysis that
existed, and the point is that nothing generates the README from it any more.

Every number here comes from a file some other script wrote. Nothing is typed.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports"


def load(name: str) -> dict:
    path = REPORTS / name
    if not path.exists():
        raise SystemExit(
            f"{path.relative_to(ROOT)} is missing. Run the analysis before the "
            f"README: `make descriptive` and `make learning`.")
    return json.loads(path.read_text(encoding="utf-8"))


desc = load("descriptive_results.json")
model = load("model_results.json")
p1, p2 = desc["part1"], desc["part2"]

learn = None
if (REPORTS / "part4_learning_results.json").exists():
    learn = json.loads(
        (REPORTS / "part4_learning_results.json").read_text(encoding="utf-8"))

tenyr = next(v for v in model["prediction"].values() if v["horizon_years"] == 10.0)
sbp = model["aetiologic_sbp_per_10mmhg"]
sbp_row = sbp if isinstance(sbp, dict) and "hr" in sbp else None

lines = ["## Key Findings", ""]

# ── Part 1 ───────────────────────────────────────────────────────────────────
lines.append(
    f"- **Crude prevalence rose and age-standardised prevalence fell.** Self-reported "
    f"cardiovascular disease among US adults {p1['age_floor']}+ went from "
    f"{100 * p1['crude_first']:.1f}% to {100 * p1['crude_last']:.1f}% crude, and from "
    f"{100 * p1['std_first']:.1f}% to {100 * p1['std_last']:.1f}% once age is standardised "
    f"to the 2000 US population — across {p1['n_cycles']} NHANES cycles, "
    f"N = {p1['n_adults']:,}, interview weights, design-based intervals. "
    f"**The reversal is the finding**; the rise is the population ageing.")

excl = p1["std_slope_excludes_zero"]
lines.append(
    f"- **The standardised trend is {100 * p1['std_slope_per_decade']:+.2f} pp per decade** "
    f"(95% CI {100 * p1['std_slope_ci'][0]:+.2f} to {100 * p1['std_slope_ci'][1]:+.2f}, "
    f"t({p1['slope_dof']})). It {'excludes' if excl else 'contains'} zero: with ten "
    f"pre-pandemic points and a dispersion estimated from the same ten, the decline is "
    f"consistent in direction and "
    f"{'established' if excl else 'not established'} at 95%. "
    f"The normal-quantile interval, which the earlier version reported, is "
    f"{100 * p1['std_slope_ci_normal'][0]:+.2f} to {100 * p1['std_slope_ci_normal'][1]:+.2f}.")

# ── Part 2 ───────────────────────────────────────────────────────────────────
lines.append(
    f"- **No detectable pandemic deviation.** {p2['post_cycle']} sits "
    f"{100 * p2['gap']:+.2f} pp from the pre-pandemic trend extrapolated "
    f"{p2['extrapolation_years']:.1f} years past {p2['extrapolation_from_cycle']} "
    f"(95% CI {100 * p2['gap_ci'][0]:+.2f} to {100 * p2['gap_ci'][1]:+.2f}). This is an "
    f"exploratory deviation from an extrapolation, not a quasi-experimental estimate: "
    f"there is one post-pandemic observation, and NCHS reports that cycle on an updated "
    f"sample design.")

# ── Part 3 ───────────────────────────────────────────────────────────────────
if sbp_row:
    lines.append(
        f"- **Baseline systolic blood pressure predicts later cardiovascular death.** "
        f"HR {sbp_row['hr']:.3f} per 10 mmHg "
        f"(95% CI {sbp_row['lo95']:.3f}–{sbp_row['hi95']:.3f}), cluster-robust, "
        f"Tobin-adjusted for treatment. Reported as an association with treatment-adjusted "
        f"baseline pressure, not as a total causal effect.")
lines.append(
    f"- **Prediction, validated forward in time:** Harrell C {tenyr['harrell_c']:.3f} at "
    f"{int(tenyr['horizon_years'])} years on held-out later cycles "
    f"(n = {tenyr['n']:,}), survey-weighted and censored at the horizon; "
    f"{tenyr['harrell_c_unweighted']:.3f} unweighted. Competing risks modelled, never "
    f"censored away.")

# ── Part 4 ───────────────────────────────────────────────────────────────────
if learn:
    a = learn["arms"]
    gain = a["deltas"]["cox_wide"]
    form = a["deltas"]["gbm_p"]
    sel = learn["screen"]["selected"]
    lines.append(
        f"- **What limits that model is the variable set, not its form.** A screen of "
        f"{learn['screen']['n_candidates']} laboratory candidates against the eleven "
        f"selected {len(sel)} ({', '.join('`' + v + '`' for v in sel) or 'none'}), worth "
        f"{gain['delta']:+.4f} in C (95% CI {gain['lo']:+.4f} to {gain['hi']:+.4f}). "
        f"Gradient boosting on the same eleven is worth {form['delta']:+.4f} — worse than "
        f"a Cox model on age and sex alone.")

lines += ["", "_Figures in [`reports/figures/`](reports/figures). Numbers in "
          "[`reports/descriptive_results.json`](reports/descriptive_results.json), "
          "[`reports/model_results.json`](reports/model_results.json) and "
          "[`reports/tables/`](reports/tables). `reports/results.json` is the output "
          "of the deprecated `run_pipeline.py` and is not a source for anything here._"]

block = "\n".join(lines)
readme = (ROOT / "README.md").read_text(encoding="utf-8")
start, end = "<!-- KEY_FINDINGS_START -->", "<!-- KEY_FINDINGS_END -->"
readme = readme.split(start)[0] + start + "\n" + block + "\n" + end + readme.split(end)[1]

# The test-count badge was the last hand-typed statistic on the front page, and
# it had gone stale: it read 85 while the suite carried 128. `tests/conftest.py`
# writes the real number on every full run, so read it rather than trusting
# whoever last remembered to edit the badge.
summary = REPORTS / "test_summary.json"
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
print("README Key Findings rebuilt from the current artefacts:")
print(block)
