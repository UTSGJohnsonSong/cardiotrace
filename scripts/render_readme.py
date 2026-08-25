"""Fill the README's Key Findings block from the artefacts the analysis produces.

It used to read `reports/results.json`, which is written by the DEPRECATED
`run_pipeline.py` -- the pipeline this project replaced, now in
`legacy-invalid/`. That block therefore
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
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports"

# Defined as a raw string at module scope, not inline: written inline it was
# escaped twice on the way into the file and the leading word boundary
# became a literal backspace, so the pattern matched nothing and the sync
# reported "0 mentions" instead of failing.
TEST_COUNT_IN_PROSE = re.compile(r"\b\d+ (tests|regressions)\b")

# Matches the badge in ANY state it can be written into, not just the green one.
# All three branches below used to match `tests-\d+%20passing-brightgreen` while
# writing three different values, so the first red run made the badge
# `tests-3%20failing-red` -- which none of the three patterns can match again. A
# later green run left it red, a later red run left the old failure count, and
# re.sub reports nothing when it matches nothing. A one-way trapdoor, in the one
# routine whose entire job is to stop the front page asserting something stale.
BADGE = re.compile(r"badge/tests-[^)\s]+")


def _set_badge(readme: str, value: str) -> str:
    """Write the test badge, whatever state it is currently in.

    Raises rather than returning the text unchanged: a substitution that matches
    nothing is indistinguishable from one that had nothing to do, and that is
    exactly how the badge could get stuck. If the badge markup is ever reworded,
    this should stop the build, not quietly leave the old claim on the page.
    """
    out, n = BADGE.subn(f"badge/tests-{value}", readme, count=1)
    if n == 0:
        raise SystemExit(
            "no test badge found in README.md. Either it was removed or its "
            "markup changed; BADGE in this file has to match it, because a "
            "badge nobody can rewrite is a permanent assertion.")
    return out


sys.path.insert(0, str(ROOT))


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

# Part 3's primary inference is the DESIGN-BASED fit, and the README has to say
# the same thing the report says. The loader carries every scale guard; see
# scripts/render_report.py::design_based_exposure.
import pandas as pd  # noqa: E402

from scripts.render_report import design_based_exposure  # noqa: E402

_xc = REPORTS / "tables" / "crosscheck_part3.csv"
if not _xc.exists():
    raise SystemExit(
        f"{_xc.relative_to(ROOT)} is missing; Part 3's primary interval comes "
        f"from it. Run scripts/crosscheck_survey.py (needs R with `survey`).")
sbp_row = design_based_exposure(pd.read_csv(_xc))

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
        f"(95% CI {sbp_row['lo95']:.3f}–{sbp_row['hi95']:.3f}), survey-design-based on the "
        f"stratified PSU design via R `survey::svycoxph`, Tobin-adjusted for treatment. "
        f"Reported as an association with treatment-adjusted baseline pressure, not as a "
        f"total causal effect.")
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
          "[`reports/tables/`](reports/tables). The superseded pipeline and everything it "
          "produced are in [`legacy-invalid/`](legacy-invalid), which no build target "
          "reaches._"]

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
        readme = _set_badge(readme, f"{t['collected']}%20passing-brightgreen")
        # The badge was not the only place the count appeared. Three sentences
        # of prose carried a hand-typed 85 while the badge said 128, so fixing
        # only the badge would have left the front page disagreeing with itself
        # in three places instead of four. Every occurrence of "<n> tests" and
        # "<n> regressions" now comes from the same run that wrote the badge.
        readme, n_prose = re.subn(TEST_COUNT_IN_PROSE,
                                  lambda m: f"{t['collected']} {m.group(1)}",
                                  readme)
        if n_prose == 0:
            # A substitution that matches nothing looks exactly like a
            # substitution that had nothing to do. That is how the pattern above
            # stayed broken: it reported "0 mentions" while three sentences on
            # the front page carried a stale count.
            raise SystemExit(
                "the test count was not found anywhere in the README prose. "
                "Either the three sentences that carry it were reworded, or "
                "TEST_COUNT_IN_PROSE no longer matches them. Fix one or the "
                "other rather than shipping a badge that disagrees with the "
                "body text.")
        print(f"test badge: {t['collected']} passing "
              f"({n_prose} prose mention(s) synced)")
    else:
        # Leaving the old badge in place asserts a green count over a red suite,
        # which is a stale POSITIVE claim rather than a missing one. Neutralise
        # it instead: the front page should not say "passing" when the last full
        # run did not.
        readme = _set_badge(readme, f"{t['failed']}%20failing-red")
        print(f"test badge set to FAILING: last full run had {t['failed']} failure(s)")
else:
    readme = _set_badge(readme, "not%20run-lightgrey")
    print("test badge set to 'not run': no reports/test_summary.json")

(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README Key Findings rebuilt from the current artefacts:")
print(block)
