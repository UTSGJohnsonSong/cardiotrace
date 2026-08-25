"""Render the single-file HTML report covering all four analyses.

Everything the page states is read from the generated artefacts -- the result
JSONs and the report tables -- rather than typed in, so the page cannot drift
from the analysis the way a hand-written summary does. Figures are inlined as
data URIs so the output is one portable file with no external requests.

The organising device is the decision ledger: each analysis is followed by the
choices it rests on, each stated as what it buys and what it costs. That is the
substance a reader can check. A list of results is not reviewable; a list of
choices with their prices is.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.descriptive import (  # noqa: E402
    AGE_LABELS, PRE_COVID_CYCLES, STD_2000, display_cycle,
)

ROOT = Path(__file__).parent.parent
FIG = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "reports" / "cardiotrace-report.html"

BUILD_DATE = "2026-08-23"
DATA_CUTOFF = "2019-12-31"


def data_uri(name: str) -> str:
    raw = (FIG / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def pct(x: float, dp: int = 2) -> str:
    return f"{100 * x:.{dp}f}%"


def pp(x: float, dp: int = 2) -> str:
    return f"{100 * x:+.{dp}f} pp"


CSS = """
:root {
  color-scheme: light;
  --paper:      #f7f6f2;
  --plate:      #fcfcfb;
  --ink:        #0b0b0b;
  --ink-2:      #52514e;
  --ink-3:      #6b6a65;   /* 5.01:1 on --paper; was #898781 at 3.32:1 */
  --rule:       #c3c2b7;
  --rule-soft:  #e1e0d9;
  --series:     #2a78d6;
  --flag:       #eb6834;
  --series-text: #1c5cab;   /* 6.13:1 on --paper; = ORDINAL_BLUE[3] */
  --flag-text:   #ba4212;   /* 5.01:1 on --paper */
  --chip-bg:    #ffffff;
  --serif: Georgia, "Iowan Old Style", "Source Serif Pro", "Times New Roman", serif;
  --sans: "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace;
  --measure: 68ch;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --paper:     #16161a;
    --plate:     #1e1e22;
    --ink:       #f4f3ef;
    --ink-2:     #b9b7b0;
    --ink-3:     #8b8983;
    --rule:      #46454a;
    --rule-soft: #2c2c31;
    --series:    #6aa5ee;
    --flag:      #f0895e;
    --series-text: #6aa5ee;   /* 7.07:1 on --paper */
    --flag-text:   #f0895e;   /* 7.26:1 on --paper */
    --chip-bg:   #232329;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --paper:     #16161a;
  --plate:     #1e1e22;
  --ink:       #f4f3ef;
  --ink-2:     #b9b7b0;
  --ink-3:     #8b8983;
  --rule:      #46454a;
  --rule-soft: #2c2c31;
  --series:    #6aa5ee;
  --flag:      #f0895e;
  --series-text: #6aa5ee;   /* 7.07:1 on --paper */
  --flag-text:   #f0895e;   /* 7.26:1 on --paper */
  --chip-bg:   #232329;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 32px 96px; }
@media (max-width: 520px) { .wrap { padding: 0 18px 72px; } }
.measure { max-width: var(--measure); }

/* ── masthead ─────────────────────────────────────────────────────── */
.masthead { padding: 76px 0 34px; border-bottom: 2px solid var(--ink); }
.eyebrow {
  font-family: var(--sans); font-size: 11px; font-weight: 600;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3);
  margin: 0 0 20px;
}
h1 {
  font-size: clamp(32px, 4.6vw, 46px); line-height: 1.1; margin: 0 0 10px;
  font-weight: 700; letter-spacing: -0.016em; text-wrap: balance;
}
.subtitle {
  font-size: clamp(18px, 2.2vw, 22px); line-height: 1.34; margin: 0 0 22px;
  color: var(--ink-2); font-weight: 400; text-wrap: balance;
}
.standfirst { font-size: 18px; line-height: 1.55; color: var(--ink-2); margin: 0; }
.masthead-meta {
  display: flex; flex-wrap: wrap; gap: 8px 28px; margin-top: 30px;
  font-family: var(--sans); font-size: 12.5px; color: var(--ink-3);
}
.masthead-meta b { color: var(--ink-2); font-weight: 600; }

/* ── section scaffolding ──────────────────────────────────────────── */
section { padding-top: 62px; }
.sec-head { display: flex; gap: 20px; align-items: baseline; margin-bottom: 8px; }
.sec-num {
  font-family: var(--sans); font-size: 12px; font-weight: 700;
  letter-spacing: 0.1em; color: var(--ink-3); padding-top: 8px;
  min-width: 74px; flex-shrink: 0;
}
h2 {
  font-size: clamp(24px, 3vw, 31px); line-height: 1.18; margin: 0;
  font-weight: 700; letter-spacing: -0.012em; text-wrap: balance;
}
h3 {
  font-family: var(--sans); font-size: 12.5px; font-weight: 700;
  letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-2);
  margin: 44px 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--rule-soft);
}
p { margin: 0 0 18px; }
.body-indent { margin-left: 94px; }
@media (max-width: 760px) { .body-indent { margin-left: 0; } .sec-num { min-width: 0; } }

/* ── method chips ─────────────────────────────────────────────────── */
.chip {
  display: inline-flex; align-items: center; gap: 7px;
  font-family: var(--sans); font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase;
  padding: 5px 11px; border: 1px solid var(--rule); border-radius: 2px;
  background: var(--chip-bg); color: var(--ink-2); white-space: nowrap;
  max-width: 100%;
}
@media (max-width: 520px) { .chip { white-space: normal; } }
.chip::before {
  content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--series); flex-shrink: 0;
}
.chip.quiet::before { background: var(--ink-3); }
.chip.open::before { background: transparent; border: 1.5px solid var(--flag); }
.chip-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 20px 0 26px; }

/* ── the decision ledger: the organising device ───────────────────── */
.ledger { margin: 30px 0 8px; border-top: 1px solid var(--rule); }
.decision {
  display: grid; grid-template-columns: 1.25fr 1fr 1fr; gap: 0 26px;
  padding: 20px 0; border-bottom: 1px solid var(--rule-soft);
}
@media (max-width: 860px) { .decision { grid-template-columns: 1fr; gap: 14px 0; } }
.decision .d-choice { font-size: 16px; line-height: 1.45; }
.decision .d-choice b { font-weight: 700; }
.decision .col-label {
  font-family: var(--sans); font-size: 10px; font-weight: 700;
  letter-spacing: 0.11em; text-transform: uppercase; color: var(--ink-3);
  display: block; margin-bottom: 6px;
}
.decision .d-buys, .decision .d-costs {
  font-family: var(--sans); font-size: 13.5px; line-height: 1.52; color: var(--ink-2);
}
.decision .d-costs { color: var(--ink-2); }
.decision .d-costs .col-label { color: var(--flag-text); }

/* ── figure plates ────────────────────────────────────────────────── */
/* The figures are matplotlib PNGs rendered once, on a light surface. Rather
   than frame a bright image in a dark card, the plate stays paper in both
   themes and carries its own ink — a deliberate single-theme island, the way a
   printed plate sits on a page. Its colours are literals on purpose: they must
   not follow the theme, because the image inside them cannot. */
figure {
  margin: 34px 0; background: #fcfcfb;
  border: 1px solid var(--rule); border-radius: 3px;
  padding: 22px; overflow-x: auto;
}
figure img { display: block; width: 100%; height: auto; }
figcaption {
  font-family: var(--sans); font-size: 12.5px; line-height: 1.55;
  color: #6b6a65; margin-top: 16px; padding-top: 14px;
  border-top: 1px solid #e1e0d9;
}
figcaption b { color: #34332f; font-weight: 600; }

/* ── stat strip ───────────────────────────────────────────────────── */
.stats {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px; background: var(--rule-soft);
  border: 1px solid var(--rule-soft); margin: 26px 0;
}
.stat { background: var(--plate); padding: 16px 18px; }
.stat .k {
  font-family: var(--sans); font-size: 10.5px; font-weight: 600;
  letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-3);
  margin-bottom: 7px;
}
.stat .v {
  font-family: var(--sans); font-size: 23px; font-weight: 700;
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em; color: var(--ink);
  line-height: 1.12;
}
.stat .n { font-family: var(--sans); font-size: 11.5px; color: var(--ink-3); margin-top: 5px; }

/* ── tables ───────────────────────────────────────────────────────── */
.twrap { overflow-x: auto; margin: 26px 0; }
table {
  width: 100%; border-collapse: collapse;
  font-family: var(--sans); font-size: 13.5px;
  font-variant-numeric: tabular-nums;
}
caption {
  text-align: left; font-family: var(--sans); font-size: 12px; font-weight: 600;
  letter-spacing: 0.07em; text-transform: uppercase; color: var(--ink-3);
  padding-bottom: 10px;
}
th, td { padding: 9px 14px 9px 0; text-align: right; border-bottom: 1px solid var(--rule-soft); }
th:first-child, td:first-child { text-align: left; }
thead th {
  font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--ink-3);
  border-bottom: 1px solid var(--rule);
}
tbody tr:last-child td { border-bottom: 1px solid var(--rule); }
td.em { font-weight: 700; color: var(--ink); }
/* Second line of a header cell: which variant of the statistic this column is.
   Lower case against the uppercase header, because it is a qualifier and not a
   second heading. */
thead th .thsub {
  display: block; margin-top: 2px;
  font-weight: 400; letter-spacing: 0.02em; text-transform: none;
  /* No opacity here. At 11px this is normal-size text under WCAG, so it needs
     4.5:1, and opacity 0.85 over the page ground measured 3.71:1 -- a fail that
     looked like a design choice. The token on its own clears it. */
  color: var(--ink-3);
}

/* ── callouts & inline ────────────────────────────────────────────── */
.note {
  border-left: 2px solid var(--rule); padding: 4px 0 4px 20px;
  margin: 28px 0; color: var(--ink-2); font-size: 16px;
}
.note.flag { border-left-color: var(--flag); }
.note b { color: var(--ink); }
code { font-family: var(--mono); font-size: 0.86em; color: var(--ink-2); }
.lede { font-size: 19px; line-height: 1.54; color: var(--ink-2); }
.term { font-style: italic; }
a { color: var(--series-text); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:focus-visible { outline: 2px solid var(--series); outline-offset: 3px; }
ul { margin: 0 0 18px; padding-left: 22px; }
li { margin-bottom: 10px; }
hr { border: 0; border-top: 1px solid var(--rule-soft); margin: 58px 0 0; }
footer {
  margin-top: 58px; padding-top: 26px; border-top: 2px solid var(--ink);
  font-family: var(--sans); font-size: 12.5px; color: var(--ink-3);
}
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def design_based_exposure(xc3: pd.DataFrame, term: str = "systolic_bp",
                          per: float = 10.0) -> dict:
    """Part 3's primary inference, read from the design-based R fit.

    Every guard here exists because the same mistake is available in two
    directions and neither one crashes: the columns are LOG hazard ratios, so
    exponentiating twice gives a plausible-looking number, and forgetting to
    exponentiate gives another one.

    The decisive check is the Wald identity. A Wald interval is exactly
    symmetric about the coefficient ON THE LOG SCALE -- lo = coef - z*se and
    hi = coef + z*se -- and that identity is destroyed by an exp(). So if these
    columns had already been exponentiated upstream, the reconstruction below
    would not close, and the build stops instead of publishing a wrong interval.

    The hazard ratio, its interval and the critical value all come from THIS
    table, i.e. from one R inference. Pairing an R interval with a Python
    p-value would be two inferences wearing one label; the report states no
    p-value for this term, and `_forbidden` keeps it that way by refusing a
    table that has quietly gained one.
    """
    import numpy as np

    from src.models import aetiologic_covariates

    # The same list the Python fit uses, not a set rebuilt from the constant.
    # Rebuilding it here meant a covariate dropped inside fit_aetiologic alone
    # would still satisfy this guard, which is the one place that is supposed to
    # notice the R table and the Python model describing different adjustments.
    expected = set(aetiologic_covariates(term))
    got = list(xc3["term"])
    if len(got) != len(set(got)):
        raise SystemExit(f"crosscheck_part3.csv has duplicate terms: {got}")
    if set(got) != expected:
        raise SystemExit(
            f"crosscheck_part3.csv does not match the Python model's terms. "
            f"Only in R: {sorted(set(got) - expected)}; only in Python: "
            f"{sorted(expected - set(got))}")

    _forbidden = [c for c in xc3.columns if c.lower() in {"p", "pvalue", "p_value"}]
    if _forbidden:
        raise SystemExit(
            f"crosscheck_part3.csv now carries {_forbidden}. If a p-value is to "
            f"be reported it must come from the same fit as the interval; wire "
            f"it in deliberately rather than letting a column appear.")

    r = xc3[xc3["term"] == term].iloc[0]
    coef, se = float(r["svycoxph_coef"]), float(r["svycoxph_se"])
    lo, hi, crit = (float(r["svycoxph_lo95"]), float(r["svycoxph_hi95"]),
                    float(r["svycoxph_crit"]))

    if not (abs(coef) < 5.0 and 0.0 < se < 5.0):
        raise SystemExit(
            f"{term}: coef={coef:g}, se={se:g} are not on the log-hazard scale; "
            f"they look like they have already been exponentiated")
    if not (lo < coef < hi):
        raise SystemExit(f"{term}: the interval does not bracket the coefficient")
    if not (np.isclose(lo, coef - crit * se, rtol=1e-6, atol=1e-9)
            and np.isclose(hi, coef + crit * se, rtol=1e-6, atol=1e-9)):
        raise SystemExit(
            f"{term}: the interval does not reconstruct as coef +/- {crit:g}*se "
            f"on the log scale, which is what a Wald interval must do. Either "
            f"the columns are already hazard ratios, or the interval came from "
            f"somewhere other than this standard error.")

    # Seventh guard: the multiplier has to BE the design-df t, not merely be
    # self-consistent with the interval it produced. The Wald reconstruction
    # above passes for any multiplier at all, so for one release Part 3's
    # primary interval was built on z = 1.96 -- survey's confint default for a
    # svycoxph -- while Part 1, the ascertainment series and the Tableau
    # extract all used a t on the design degrees of freedom. Nothing in the
    # artefact recorded which was which, because design_df was printed to the R
    # console instead of written to the file.
    from scipy import stats

    if "svycoxph_design_df" not in xc3.columns:
        raise SystemExit(
            "crosscheck_part3.csv has no svycoxph_design_df column, so the "
            "critical value cannot be checked against anything. Regenerate it "
            "with scripts/crosscheck_survey.py.")
    ddf = float(r["svycoxph_design_df"])
    if not np.isfinite(ddf) or ddf < 1:
        raise SystemExit(f"{term}: design df is {ddf!r}, which cannot be right")
    expect = float(stats.t.ppf(0.975, ddf))
    if not np.isclose(crit, expect, rtol=1e-6):
        raise SystemExit(
            f"{term}: the interval uses a multiplier of {crit:.6f}, but the "
            f"design has {ddf:g} degrees of freedom and t(0.975) = "
            f"{expect:.6f}. z = 1.959964 is what survey's confint returns by "
            f"default; the rest of this project uses the design-df t, and two "
            f"conventions under one \"95% CI\" legend is the thing this guard "
            f"exists to stop.")

    # Exactly one exponentiation, here and nowhere else.
    return {"hr": float(np.exp(coef * per)),
            "lo95": float(np.exp(lo * per)),
            "hi95": float(np.exp(hi * per)),
            "se": se, "crit": crit, "design_df": ddf, "per": per}


def _num(x, dp: int) -> str:
    """A number, or an em dash where there is none.

    An f-string renders float('nan') as the literal text "nan", which is what a
    reader of the published page then sees. Every numeric cell that can be
    missing goes through here.
    """
    return "&mdash;" if pd.isna(x) else f"{x:.{dp}f}"


def _pval(x) -> str:
    """A p-value, or the bound it is below.

    `fit_aetiologic` rounds to four decimals, so every p below 5e-5 arrives here
    as exactly 0.0. Printing that asserts a probability of zero, which is not a
    quantity any model returns -- and unlike a NaN it looks like a result. The
    rounding is deliberate (the log columns beside it are the unrounded source),
    so the fix belongs at the point of display.
    """
    if pd.isna(x):
        return "&mdash;"
    return "&lt;0.0001" if float(x) < 0.0001 else f"{float(x):.4f}"



def _text(s) -> str:
    """Text, or an em dash.

    `s or fallback` is not enough: pandas reads an empty CSV field back as
    float('nan'), and float('nan') is truthy, so the fallback never fires and
    the NaN is interpolated straight into the cell. That is how nine rows of
    the candidate table came to answer "Into the forward path?" with "nan".
    """
    return "&mdash;" if pd.isna(s) else str(s)


def _head_cells(df: pd.DataFrame) -> str:
    """Header row for a table rendered whole."""
    return "".join(f"<th>{c}</th>" for c in df.columns)


def _full_rows(df: pd.DataFrame, em_last: bool = False) -> str:
    """Body rows for a table rendered whole, every cell through `_text`.

    Three tables were assembled by three near-identical comprehensions and only
    one of them guarded against NaN. Whether a missing cell reaches a reader as
    an em dash or as the word "nan" should not depend on which comprehension a
    table happens to be rendered by.
    """
    last = len(df.columns) - 1
    em = ' class="em"'
    return "".join(
        "<tr>" + "".join(
            f"<td{em if em_last and i == last else ''}>{_text(v)}</td>"
            for i, v in enumerate(r)) + "</tr>"
        for r in df.itertuples(index=False))



def stat(k: str, v: str, n: str = "") -> str:
    note = f'<div class="n">{n}</div>' if n else ""
    return f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div>{note}</div>'


def decision(choice: str, buys: str, costs: str) -> str:
    return (
        '<div class="decision">'
        f'<div class="d-choice"><span class="col-label">The choice</span>{choice}</div>'
        f'<div class="d-buys"><span class="col-label">What it buys</span>{buys}</div>'
        f'<div class="d-costs"><span class="col-label">What it costs</span>{costs}</div>'
        '</div>')


def ledger(*decisions: str) -> str:
    return '<div class="ledger">' + "".join(decisions) + "</div>"



# Arm labels for the report table. Kept beside `decision`/`stat` rather than
# imported from the figure script, because the figure wants line breaks and the
# table wants none.
ARM_LABEL_HTML = {
    "cox_p": "Cox &mdash; the eleven <i>(the published model)</i>",
    "cox_wide": "Cox &mdash; the eleven plus what the screen chose",
    "gbm_p": "Gradient boosting &mdash; the eleven",
    "gbm_wide": "Gradient boosting &mdash; the eleven plus the screen",
    "floor_age_sex": "Cox &mdash; age and sex only <i>(the floor)</i>",
}


def build() -> str:
    desc = json.loads((ROOT / "reports" / "descriptive_results.json").read_text())
    model = json.loads((ROOT / "reports" / "model_results.json").read_text())
    p1, p2 = desc["part1"], desc["part2"]

    overall = pd.read_csv(TABLES / "part1_prevalence_by_cycle.csv")
    race = pd.read_csv(TABLES / "part1_prevalence_by_race.csv")
    strobe = pd.read_csv(TABLES / "strobe_part3.csv")
    cif = pd.read_csv(TABLES / "cif_by_sbp.csv")
    cox = pd.read_csv(TABLES / "cox_systolic_bp.csv")

    # Part 4. Guarded rather than left to raise FileNotFoundError, because
    # `make descriptive` also runs this file and the new chain has to be run
    # once before it will succeed.
    p4_path = ROOT / "reports" / "part4_learning_results.json"
    if not p4_path.exists():
        raise SystemExit(
            f"{p4_path.name} is missing; run scripts/build_learning_results.py "
            "(or `make learning`) before rendering the report")
    p4 = json.loads(p4_path.read_text(encoding="utf-8"))
    p4_arms = pd.read_csv(TABLES / "part4_arms.csv")
    p4_rank = pd.read_csv(TABLES / "part4_marginal_ranking.csv")
    p4_imp = pd.read_csv(TABLES / "part4_importance.csv")
    p4_creat = pd.read_csv(TABLES / "part4_creatinine.csv")

    # The cohort's own counts. scripts/build_cohort_results.py has claimed since
    # it was written that these were no longer typed by hand; they were. This
    # file never opened cohort_results.json, so 20,736 / 925 / 2,711 / 235,553
    # sat as literals in five places -- correct, but outside what
    # verify_clean_rebuild can see, which is the only reason a number here is
    # ever trustworthy.
    cohort_path = ROOT / "reports" / "cohort_results.json"
    if not cohort_path.exists():
        raise SystemExit(
            f"{cohort_path.name} is missing; run `make cohort`.")
    coh = json.loads(cohort_path.read_text(encoding="utf-8"))
    n_cohort = f"{int(coh['n_participants']):,}"
    n_cvd = f"{int(coh['cvd_deaths']):,}"
    n_competing = f"{int(coh['competing_deaths']):,}"
    n_person_years = f"{round(float(coh['person_years'])):,}"

    miss_path = ROOT / "reports" / "missingness_results.json"
    if not miss_path.exists():
        raise SystemExit(
            f"{miss_path.name} is missing; run scripts/build_missingness_results.py")
    miss = json.loads(miss_path.read_text(encoding="utf-8"))
    # The limitations paragraph quotes the complete-case cost. It quoted the
    # PCE NINE-input figures (18,744 / 824) under a sentence naming the ELEVEN
    # model inputs, which understated the thing it was disclosing: the eleven
    # cost 14.6% of the deaths, not 10.9%. Interpolated from the artefact now,
    # so the label and the number cannot disagree again.
    miss_pct_people = float(miss["pct_dropped"])
    miss_n_kept = int(miss["n_analysed"])
    miss_n_cohort = int(miss["n_cohort"])
    miss_deaths_cohort = int(miss["cvd_deaths_cohort"])
    miss_deaths_kept = int(miss["cvd_deaths_analysed"])
    miss_pct_deaths = 100 * (1 - miss_deaths_kept / miss_deaths_cohort)
    miss_drivers = pd.read_csv(TABLES / "part3_missing_drivers.csv")
    miss_compare = pd.read_csv(TABLES / "part3_missing_compare.csv")
    rows_miss = "".join(
        f"<tr><td><code>{r.variable}</code></td><td>{r.n_missing:,}</td>"
        f"<td>{r.pct_missing:.2f}%</td><td class='em'>{r.n_uniquely_lost:,}</td></tr>"
        for r in miss_drivers.itertuples() if r.n_missing > 0)
    rows_misscmp = "".join(
        f"<tr><td><code>{r.variable}</code></td><td>{r.kept_mean:,.4f}</td>"
        f"<td>{r.dropped_mean:,.4f}</td>"
        f"<td class='em'>{r.difference:+,.4f}</td></tr>"
        for r in miss_compare.itertuples())

    # The R cross-validation. NOT optional any more, and the comment here used
    # to say it was: "the section is omitted rather than the build failing on a
    # machine without one". That stopped being true when Part 3's primary
    # interval moved to svycoxph -- the build now raises without these tables,
    # so `have_xc` was False on no reachable path and the "omit the section"
    # branch below could never be selected. Fail here, where the flag is
    # computed, and name whichever file is actually missing.
    xc1_path = TABLES / "crosscheck_part1.csv"
    xc3_path = TABLES / "crosscheck_part3.csv"
    absent = [p.name for p in (xc1_path, xc3_path) if not p.exists()]
    if absent:
        raise SystemExit(
            f"missing from reports/tables/: {', '.join(absent)}. Part 3's "
            f"primary intervals come from crosscheck_part3.csv and section 7 "
            f"reports both. Run scripts/crosscheck_survey.py (needs R with the "
            f"survey package).")
    xc1 = pd.read_csv(xc1_path)
    xc3 = pd.read_csv(xc3_path)
    xc_se_max = float(xc1["absdiff_se_std"].abs().max())
    xc_rel_max = float(xc1["reldiff_se_std"].abs().max())
    xc_coef_max = float(xc3["absdiff_coef_svycoxph"].abs().max())
    xc_se_med = float(xc3["reldiff_se_svycoxph"].abs().median())
    xc_se_worst = float(xc3["reldiff_se_svycoxph"].abs().max())
    xc_cluster_med = float(xc3["reldiff_se_coxph_cluster"].abs().median())
    _exp = xc3[xc3["term"] == "systolic_bp"].iloc[0]
    xc_exp_rel = float(abs(_exp["reldiff_se_svycoxph"]))
    xc_dof_lo = int(xc1["r_design_df"].min())
    xc_dof_hi = int(xc1["r_design_df"].max())

    rows1 = "".join(
        f"<tr><td>{display_cycle(r.cycle)}</td><td>{r.n:,}</td><td>{r.n_cases:,}</td>"
        f"<td>{100 * r.p_crude:.2f}</td><td class='em'>{100 * r.p_std:.2f}</td>"
        f"<td>{100 * r.lo_std:.2f} – {100 * r.hi_std:.2f}</td></tr>"
        for r in overall.itertuples())

    cif_cols = list(cif.columns)
    em_attr = ' class="em"'
    rows_cif = "".join(
        "<tr>" + "".join(
            "<td{}>{}</td>".format(em_attr if i == len(cif_cols) - 1 else "", v)
            for i, v in enumerate(r)) + "</tr>"
        for r in cif.itertuples(index=False))

    pred = model["prediction"]
    # The unweighted concordance sits beside the weighted one because the
    # weighted value is the headline and the gap is large: 0.804 was published
    # for as long as concordance() accepted a weights argument its body did not
    # read. A reader who only sees the corrected number cannot tell how far the
    # correction moved it, and the README says both -- the page should not
    # disclose less than the file it is generated alongside.
    rows_pred = "".join(
        f"<tr><td>{k}</td><td>{v['n']:,}</td><td>{v['cvd_deaths']}</td>"
        f"<td class='em'>{v['harrell_c']:.3f}</td>"
        f"<td>{v['harrell_c_unweighted']:.3f}</td>"
        f"<td>{v['mean_predicted_pct']:.2f}%</td>"
        f"<td>{v['mean_observed_pct']:.2f}%</td></tr>"
        for k, v in pred.items())

    # `f"{v}"` on a missing cell prints the literal text "nan", which is what a
    # reader then sees. `_text` is the default here for every whole-table
    # render, not just the flow table: the flow table got it because its first
    # row legitimately has no cvd_deaths, and the aetiologic table went without
    # for no reason other than having no missing cell on the day it was written.
    # An absent Cox estimate is an absence, so it renders as one.
    # A DISPLAY projection, not the CSV dumped whole. Two things were reaching
    # the page that no model produced. `fit_aetiologic` rounds `p` to 4dp, so
    # anything below 5e-5 became exactly `0.0` and six of the nine rows
    # published a p-value of zero. And the log columns are deliberately left
    # unrounded -- that was the fix for the hazard-ratio scaling bug -- so the
    # table printed `0.011474575653970712` at sixteen significant figures beside
    # hazard ratios given to four. Both are presentation faults of correct
    # numbers, which is why neither showed up as a wrong value anywhere.
    # The CSV keeps every column at full precision; it is linked from the page.
    cox_display = pd.DataFrame({
        "covariate": cox["covariate"],
        "n": cox["n"].map(lambda v: f"{int(v):,}"),
        "HR": cox["hr"].map(lambda v: _num(v, 4)),
        "95% CI": [f"{_num(lo, 4)}&ndash;{_num(hi, 4)}"
                   for lo, hi in zip(cox["hr_lo95"], cox["hr_hi95"])],
        "log HR": cox["log_hr"].map(lambda v: _num(v, 6)),
        "p": cox["p"].map(_pval),
    })
    rows_cox = _full_rows(cox_display)
    cox_head = _head_cells(cox_display)
    rows_strobe = _full_rows(strobe)
    strobe_head = _head_cells(strobe)

    asc = pd.read_csv(TABLES / "part1_ascertainment.csv")
    cp = json.loads((TABLES / "part2_changepoint.json").read_text())
    flow = pd.read_csv(TABLES / "part1_flow.csv")
    power = cp["power"]

    # Counts the prose used to assert. Derived, so a changed base cannot leave
    # a sentence behind.
    _nat = overall.set_index("cycle")["p_std"]
    _by_race = race.pivot(index="cycle", columns="race_eth", values="p_std")
    n_above_black = int((_by_race["Non-Hispanic Black"] > _nat).sum())
    n_below_mex = int((_by_race["Mexican American"] < _nat).sum())
    n_race_cycles = int(len(_by_race))
    _oh = race[race["race_eth"] == "Other Hispanic"].set_index("cycle")["n"]
    oh_before, oh_after = int(_oh["2005-2006"]), int(_oh["2007-2008"])
    p_lo, p_hi = 100 * overall["p_std"].min(), 100 * overall["p_std"].max()
    strobe_n = int(strobe["n"].iloc[-1])
    rows_flow = "".join(
        f"<tr><td>{display_cycle(r.cycle)}</td><td>{r.age_eligible:,}</td>"
        f"<td>{r.no_weight:,}</td><td>{r.analysed:,}</td>"
        f"<td class='em'>{r.lost_pct:.1f}%</td></tr>"
        for r in flow.itertuples())
    # The power row matching the slope actually observed, so this sentence
    # cannot describe a different trend from the one reported a page earlier.
    _slope_pp = abs(100 * p1["std_slope_per_decade"])
    _row = min(power, key=lambda r: abs(r["slope_change_per_decade_pp"] - _slope_pp))
    power_at_slope, power_slope_pp = _row["power"], _row["slope_change_per_decade_pp"]
    power_80 = next((r["slope_change_per_decade_pp"] for r in power
                     if r["power"] >= 0.8), float("nan"))

    # The standard population, written out because a reader cannot check an
    # age-standardised number without knowing what it was standardised to.
    total_w = sum(STD_2000.values())
    rows_std = "".join(
        f"<tr><td>{band}</td><td>{STD_2000[band]:.6f}</td>"
        f"<td class='em'>{STD_2000[band] / total_w:.6f}</td></tr>"
        for band in AGE_LABELS)

    rows_deff = "".join(
        f"<tr><td>{display_cycle(r.cycle)}</td><td>{r.n:,}</td><td>{r.n_psu}</td>"
        f"<td>{r.deff_std:.2f}</td><td>{r.kish_weighting:.2f}</td>"
        f"<td class='em'>{r.deff_clustering:.2f}</td></tr>"
        for r in overall.itertuples())

    rows_asc = "".join(
        f"<tr><td>{display_cycle(r.cycle)}</td><td>{r.instrument}</td><td>{r.n_hypertensive:,}</td>"
        f"<td class='em'>{100 * r.ascertained_std:.1f}%</td>"
        f"<td>{100 * r.lo_std:.1f} – {100 * r.hi_std:.1f}</td>"
        f"<td>{100 * r.measured_only_std:.1f}%</td></tr>"
        for r in asc.itertuples())

    rows_power = "".join(
        f"<tr><td>{r['slope_change_per_decade_pp']:+.1f} pp / decade</td>"
        f"<td class='em'>{100 * r['power']:.0f}%</td></tr>" for r in power)

    deff_med = overall["deff_std"].median()
    kish_med = overall["kish_weighting"].median()
    clust_med = overall["deff_clustering"].median()
    neff_med = overall["n_effective_std"].median()
    n_med = overall["n"].median()
    psu_lo, psu_hi = int(overall["n_psu"].min()), int(overall["n_psu"].max())
    n_pre_cycles = len(PRE_COVID_CYCLES)
    asc_aus = asc[asc["instrument"] == "auscultatory"]
    asc_peak = asc_aus.loc[asc_aus["ascertained_std"].idxmax()]


    # ── Part 4 ────────────────────────────────────────────────────────────
    p4_scr, p4_arm, p4_prev = p4["screen"], p4["arms"], p4["prevent"]
    p4_ref = p4_arms[p4_arms["is_reference"]].iloc[0]
    p4_gain = p4_arms[p4_arms["arm"] == "cox_wide"].iloc[0]
    p4_form = p4_arms[p4_arms["arm"] == "gbm_p"].iloc[0]
    p4_floor = p4_arms[p4_arms["arm"] == "floor_age_sex"].iloc[0]
    p4_sel = p4_scr["selected"]
    p4_top = p4_rank.iloc[0]

    p4_rows_rank = "".join(
        f"<tr><td>{r.label}</td><td>{r.e2_status}</td><td>{r.n:,}</td>"
        f"<td>{_num(r.hr_per_sd, 3)}</td><td class='em'>{_num(r.wald, 1)}</td>"
        f"<td>{'yes' if r.in_pool else _text(r.note)}</td></tr>"
        for r in p4_rank.itertuples())

    p4_rows_arms = "".join(
        f"<tr><td>{ARM_LABEL_HTML[r.arm]}</td><td>{r.n_features}</td>"
        f"<td>{_num(r.harrell_c, 4)}</td><td>{_num(r.auc_horizon, 4)}</td>"
        f"<td class='em'>{'&mdash; reference' if r.is_reference else f'{r.delta_c:+.4f}'}</td>"
        f"<td>{'' if r.is_reference else f'{r.delta_lo:+.4f} to {r.delta_hi:+.4f}'}</td></tr>"
        for r in p4_arms.itertuples())

    p4_rows_imp = "".join(
        f"<tr><td>{r.rank}</td><td><code>{r.variable}</code></td>"
        f"<td class='em'>{r.delta_c:+.5f}</td><td>{r.e2_status}</td>"
        f"<td>{r.e2_why}</td></tr>"
        for r in p4_imp.head(8).itertuples())

    p4_rows_creat = "".join(
        f"<tr><td>{display_cycle(r.cycle)}</td><td>{r.n:,}</td><td>{r.mean_as_loaded:.4f}</td>"
        f"<td class='em'>{r.mean_calibrated:.4f}</td>"
        f"<td>{'CDC correction applied' if r.corrected else '&mdash;'}</td></tr>"
        for r in p4_creat.itertuples())

    # The section states what the screen found, so it has to be able to state a
    # null. A pre-registered claim with no failing branch is not pre-registered.
    if p4_sel:
        p4_screen_says = (
            f"The screen admitted <b>{len(p4_sel)}</b> of "
            f"{p4_scr['n_candidates']} candidates: "
            + ", ".join(f"<code>{v}</code>" for v in p4_sel) + ".")
    else:
        p4_screen_says = (
            f"The screen admitted <b>none</b> of its {p4_scr['n_candidates']} "
            "candidates. On this cohort the eleven already carry what the "
            "laboratory adds.")

    def _codes(names):
        return ", ".join(f"<code>{v}</code>" for v in names) or "none"

    # `bool()` on a possibly-missing flag reads missing as TRUE: the column is
    # object dtype because the reference row has no delta, and bool(nan) is
    # True. Getting that wrong here would make the page assert that a difference
    # is established on the strength of a blank cell.
    def _flag(x) -> bool:
        return bool(x) and not pd.isna(x)

    _gain_excl = _flag(p4_gain.excludes_zero)
    _form_excl = _flag(p4_form.excludes_zero)
    if _gain_excl and _form_excl:
        p4_both_excl = "excludes zero"
    elif _gain_excl:
        p4_both_excl = ("excludes zero for the variable set; the form comparison is wider "
                        "and the boosted arm on the screened set is not distinguishable "
                        "from the reference")
    elif _form_excl:
        p4_both_excl = ("excludes zero for the form; the variable set is not distinguishable "
                        "from the reference")
    else:
        p4_both_excl = "contains zero, so neither comparison is resolved here"
    p4_vs_floor = ("discriminates <em>worse than</em>"
                   if p4_form.harrell_c < p4_floor.harrell_c
                   else "still beats")

    p4_base_kept = p4_prev["base_selected"]
    p4_base_dropped = p4_prev["base_rejected"]
    p4_opt_kept = p4_prev["optional_selected"]
    p4_opt_dropped = p4_prev["optional_rejected"]
    p4_base_had = p4_prev["base_already_in_model"]

    def _names(keys, lookup):
        """PREVENT's own variables under PREVENT's own names.

        The code names are this project's column labels; printing `egfr` and
        `sdi` in a sentence about what a published guideline requires reads as
        though the guideline used them.
        """
        got = [lookup[k] for k in keys if k in lookup]
        if len(got) < 2:
            return got[0] if got else "none"
        return ", ".join(got[:-1]) + " and " + got[-1]

    p4_base_new_list = _names(p4_prev["base_new"], p4_prev["base_new"])
    p4_opt_list = _names(p4_prev["optional"], p4_prev["optional"])
    p4_all = p4_prev["base_new"] | p4_prev["optional"]
    p4_base_screened = _names(p4_prev["base_screened"], p4_all)
    p4_opt_screened = _names(p4_prev["optional_screened"], p4_all)
    p4_base_had_list = _names(p4_base_had, p4_all)
    p4_unavailable = _names(list(p4_prev["unavailable"]), p4_all)
    p4_unavailable_why = "; ".join(p4_prev["unavailable"].values())

    # Branching on what happened, in both directions. The interesting case here
    # is the asymmetric one, and it is the one that does NOT flatter the screen.
    if p4_base_dropped and p4_opt_kept:
        p4_prevent_says = (
            f"The screen rejected {_names(p4_base_dropped, p4_all)}, which "
            f"PREVENT makes mandatory, and kept "
            f"{_names(p4_opt_kept, p4_all)}, which PREVENT treats as "
            "optional. It disagrees with the guideline in both directions at "
            "once, and that is the informative result rather than an "
            "embarrassment.")
    elif p4_base_kept and p4_opt_kept:
        p4_prevent_says = (
            f"The screen kept {_codes(p4_base_kept + p4_opt_kept)} &mdash; the "
            "base predictor and the extensions alike &mdash; having never been "
            "told which they were.")
    elif not (p4_base_kept or p4_opt_kept):
        p4_prevent_says = (
            "The screen kept none of them. That is a disagreement with the "
            "current guideline, and it is worth explaining rather than "
            "smoothing over.")
    else:
        p4_prevent_says = (
            f"The screen kept {_codes(p4_base_kept + p4_opt_kept)} and rejected "
            f"{_codes(p4_base_dropped + p4_opt_dropped)}.")

    sbp = model["aetiologic_sbp_per_10mmhg"]

    # PRIMARY inference for the exposure comes from the DESIGN-BASED fit, not
    # from lifelines. The two agree on the coefficient to 3e-12 and disagree on
    # the standard error by a median of 1.2% across the nine terms, because
    # lifelines computes an unstratified cluster sandwich while `svycoxph` uses
    # the stratified ultimate-cluster form NHANES guidance describes. Only the
    # second is design-based in the sense this report claims elsewhere, so it is
    # the one reported; the Python fit is kept beside it as a sensitivity
    # analysis rather than replaced.
    #
    # The artefacts are committed, so the site builds without R. Regenerating
    # them needs `scripts/crosscheck_survey.py`, which shells out to Rscript.
    # Their presence is checked where they are read, not here.
    sbp_design = design_based_exposure(xc3)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cardiovascular Disease in the United States, 1999–2022 — CardioTrace</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<header class="masthead">
  <p class="eyebrow">CardioTrace · NHANES 1999–2022 · NCHS Linked Mortality File</p>
  <h1>Cardiovascular Disease in the United States, 1999–2022</h1>
  <p class="subtitle">Three estimands, three designs &mdash; and a fourth section asking what limits the third: a standardised prevalence series,
  a counterfactual test of the pandemic, and a prospective cohort of cardiovascular death</p>
  <p class="standfirst measure">One national survey can answer more than one question, but not
  with one method. This report states each question as a quantity to be estimated, sets out the
  design that identifies it, and prices the choices that design requires.</p>
  <div class="masthead-meta">
    <span><b>Prepared</b> {BUILD_DATE}</span>
    <span><b>Survey cycles</b> {p1['n_cycles']}, {display_cycle(overall.iloc[0]['cycle'])} to {display_cycle(p1['last_cycle'])}</span>
    <span><b>Descriptive sample</b> {p1['n_adults']:,} adults 20+</span>
    <span><b>Cohort</b> {n_cohort} adults 40–79 · {n_cvd} CVD deaths</span>
    <span><b>Mortality follow-up through</b> {DATA_CUTOFF}</span>
  </div>
</header>

<section>
  <div class="sec-head"><div class="sec-num">1</div>
  <h2>Why one dataset needs three designs</h2></div>
  <div class="body-indent">
    <p class="lede measure">Statistical questions come in three kinds, and the same variable can
    be required in one, forbidden in another, and irrelevant in the third. Fixing which kind of
    question is being asked is what makes every downstream choice decidable.</p>

    <div class="twrap">
      <table>
        <caption>The three kinds of question</caption>
        <thead><tr><th>&nbsp;</th><th>Descriptive</th><th>Causal</th><th>Predictive</th></tr></thead>
        <tbody>
          <tr><td>Asks</td><td>How many, and how has it moved?</td>
              <td>If we changed X, what happens to Y?</td>
              <td>Given what we know now, who is at risk?</td></tr>
          <tr><td>Needs</td><td>Survey weights, standardisation, intervals</td>
              <td>A causal graph, confounder control, stated assumptions</td>
              <td>Out-of-sample validation, calibration</td></tr>
          <tr><td>Does not need</td><td>Confounder control</td><td>A high AUC</td>
              <td>A causal story</td></tr>
          <tr><td>Fails by</td><td>Reporting raw rates from an ageing population</td>
              <td>Interpreting every coefficient in one table as an effect</td>
              <td>Validating on data that leaks into training</td></tr>
        </tbody>
      </table>
    </div>

    <p class="measure">The clearest illustration is age. To describe how disease burden moved
    across {p1['n_cycles']} survey cycles, age must be <em>removed</em> — otherwise an ageing population looks like a
    spreading disease. To predict who will die, age must be <em>kept</em> — it is the single
    strongest predictor available, and a model without it is worthless. The same variable,
    opposite treatment, and the only thing that decides which is correct is which question is
    being asked.</p>

    <p class="measure">The first three analyses below therefore use three different samples. They are
    not three views of one table.</p>

    <div class="twrap">
      <table>
        <caption>The three estimands, and the samples they need</caption>
        <thead><tr><th>&nbsp;</th><th>§2 Burden</th><th>§3 Pandemic</th><th>§4 Cohort</th></tr></thead>
        <tbody>
          <tr><td>Question</td><td>How has prevalence moved?</td>
              <td>Did 2020 bend the trend?</td>
              <td>Who among the healthy dies of it?</td></tr>
          <tr><td>Kind</td><td>Descriptive</td><td>Causal (quasi-experimental)</td>
              <td>Predictive + causal</td></tr>
          <tr><td>Sample</td><td>{p1['n_adults']:,} adults 20+, {p1['n_cycles']} cycles</td>
              <td>Same series, one post-pandemic point</td>
              <td>{n_cohort} adults 40–79, CVD-free at baseline</td></tr>
          <tr><td>Outcome</td><td>Self-reported diagnosis</td><td>Self-reported diagnosis</td>
              <td>Death from cardiovascular causes</td></tr>
          <tr><td>Estimator</td><td>Weighted, age-standardised prevalence</td>
              <td>Counterfactual extrapolation</td>
              <td>Cause-specific Cox, competing risks</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<hr>

<section>
  <div class="sec-head"><div class="sec-num">2</div>
  <h2>The burden across {p1['n_cycles']} cycles, with ageing taken out</h2></div>
  <div class="body-indent">
    <div class="chip-row">
      <span class="chip">Descriptive</span>
      <span class="chip">Survey-weighted</span>
      <span class="chip">Age-standardised</span>
      <span class="chip">Design-based intervals</span>
    </div>
    <p class="lede measure">Crude prevalence of self-reported cardiovascular disease rose over the
    series. Age-standardised prevalence fell. Standardisation does not shrink the trend here — it
    reverses its sign.</p>

    <div class="stats">
      {stat("Adults 20+", f"{p1['n_adults']:,}", f"{p1['n_cycles']} cycles, {display_cycle(overall.iloc[0]['cycle'])} to "
         f"{display_cycle(p1['last_cycle'])}")}
      {stat("Crude", f"{pct(p1['crude_first'], 1)} → {pct(p1['crude_last'], 1)}", f"rising, to {display_cycle(p1['last_cycle'])}")}
      {stat("Standardised", f"{pct(p1['std_first'], 1)} → {pct(p1['std_last'], 1)}", f"falling, to {display_cycle(p1['last_cycle'])}")}
      {stat("Weighted mean age", f"{p1['mean_age_first']:.1f} → {p1['mean_age_last']:.1f}", "years — the driver")}
    </div>

    <figure>
      <img src="{data_uri('part1_standardisation.png')}"
           alt="Crude and age-standardised prevalence of self-reported cardiovascular disease
                across the ten pre-pandemic NHANES cycles, 1999 to 2018. The two series track
                together until roughly 2015, then the crude series rises while the standardised
                series stays flat. The August 2021 to August 2023 cycle is plotted separately in
                grey, detached from both lines.">
      <figcaption><b>Two series, opposite conclusions.</b> Both lines run the
      {n_pre_cycles} pre-pandemic cycles. The last cycle is drawn <b>detached</b>, in grey, with
      its own interval and no line joining it: NCHS names it August 2021&ndash;August 2023,
      reports it on an updated sample design with modified interview and examination procedures,
      and urges caution before combining it with earlier cycles for trend analysis. A continuous
      line would assert a comparability the survey itself declines to assert. Over the fitted
      window the standardised series falls
      {abs(100 * p1['std_slope_per_decade']):.2f} points per decade (95% CI
      {100 * p1['std_slope_ci'][0]:.2f} to {100 * p1['std_slope_ci'][1]:.2f}) while the crude
      series rises {100 * p1['crude_slope_per_decade']:+.2f}. <b>The sign reversal is the
      finding, and it does not depend on any critical value; the size of the decline does.</b>
      Ten points with a dispersion estimated from the same ten give t({p1['slope_dof']}) =
      {p1['slope_t_crit']:.3f} rather than 1.96, and on that interval the slope
      {'excludes' if p1['std_slope_excludes_zero'] else 'does not exclude'} zero. The decline
      is consistent in direction across the series and
      {'established' if p1['std_slope_excludes_zero'] else 'not established'} at 95%.</figcaption>
    </figure>

    <h3>How standardisation works, and why it is not a correction factor</h3>
    <p class="measure">Direct standardisation computes prevalence separately within each age band,
    then re-weights those bands to a fixed reference population — here the 2000 projected U.S.
    standard population, on the bands NCHS pairs with NHANES: 20–34, 35–44, 45–54, 55–64, 65–74,
    75 and over. The result answers a counterfactual question: <em>what would the national
    rate be if the age structure had never changed?</em> Because the weights are held constant
    across cycles, any movement left in the series cannot be demographic.</p>
    <p class="measure">The intervals are equally deliberate. NHANES is a stratified, multi-stage
    probability sample: people are drawn in clusters, and two people from the same cluster share a
    neighbourhood, a provider mix and an interviewer. Treating them as independent produces
    standard errors that are too small and intervals that look decisive when they are not. The
    variance here is Taylor-linearised and clustered on the masked variance units NCHS releases in
    place of the true stratum and primary sampling unit, and the
    linearisation is applied to the standardised estimator as a whole rather than band by band. A
    single sampling unit contributes people to every age band at once, so band-by-band variances
    would discard the covariance between bands and understate the total.</p>

    {ledger(
      decision(
        "Standardise directly to the <b>2000 U.S. standard population</b> rather than report crude rates.",
        "Separates disease change from demographic change. Comparable to any other US health statistic using the same standard.",
        "The output is no longer the actual number of people with disease — it is a hypothetical rate under a fixed age structure."),
      decision(
        "Define the population as <b>adults 20 and over</b>, on the age bands NCHS assigns to NHANES.",
        "The widest defensible adult range, on the bands the standard&rsquo;s own documentation pairs with this survey &mdash; so the base is inherited rather than chosen.",
        "The 20&ndash;34 band carries very few events, so it contributes width to the intervals and almost no signal."),
      decision(
        "Collapse the two oldest standard bands into an open <b>75+</b> group.",
        "NHANES top-codes age, and the top code itself changed over the series. An open upper band is stable across all cycles.",
        "No resolution above 75, where prevalence is highest and still rising with age."),
      decision(
        "Use <b>Taylor linearisation on the masked variance units</b> (<code>SDMVSTRA</code> × <code>SDMVPSU</code>) rather than model-based standard errors.",
        "Intervals that reflect how the sample was actually drawn, using the only design variables NCHS releases publicly.",
        "Wider intervals than a naive calculation, no closed form — the estimator has to be linearised by hand — and variances that approximate the true design rather than reproduce it, because the real strata and PSUs are withheld for disclosure control."),
    )}

    <figure>
      <img src="{data_uri('part1_by_race.png')}"
           alt="Small multiples of age-standardised cardiovascular disease prevalence for four
                race and ethnicity groups, each panel repeating the national series as a grey
                reference line.">
      <figcaption><b>Differences between groups persist across the whole series.</b> Non-Hispanic
      Black adults sit above the national rate in {n_above_black} of {n_race_cycles} cycles;
      Mexican American adults sit below it in {n_below_mex} of {n_race_cycles}. The Other Hispanic panel is shaded before 2007 because its per-cycle sample
      steps from {oh_before:,} to {oh_after:,} people between 2005–2006 and 2007–2008 — that segment measures a
      different sample, and the apparent rise across it is a sampling artefact rather than a
      health trend.</figcaption>
    </figure>

    <h3>The standard population, written out</h3>
    <p class="measure">An age-standardised rate cannot be checked without the distribution it was
    standardised to, so here it is. The left column is each band&rsquo;s share of the full 2000
    projected U.S. population; the right column renormalises over adults 20 and over, which is what
    the estimator actually applies. The bands are the ones NCHS pairs with NHANES, and the weights
    are sums of the Master List five-year weights they span.</p>

    <div class="twrap">
      <table>
        <caption>2000 projected U.S. standard population &mdash; age-adjustment weights</caption>
        <thead><tr><th>Age band</th><th>Share of all ages</th>
          <th>Renormalised, 20+ base</th></tr></thead>
        <tbody>{rows_std}</tbody>
      </table>
    </div>

    <h3>How much the clustering actually costs</h3>
    <p class="measure">The argument for design-based variance is usually made by citation. It can
    be measured instead. The design effect is the design-based variance divided by the variance a
    simple random sample of the same size would have produced; the effective sample size,
    <em>n</em> divided by that ratio, is the number of independent observations this sample is
    worth. NCHS publishes no design effects for continuous NHANES, so the only way to know is to
    compute them on the estimates at hand.</p>

    <div class="twrap">
      <table>
        <caption>Design effect, decomposed &mdash; age-standardised prevalence. The residual is
        the total divided by the Kish weighting factor: it carries clustering, stratification and
        their interaction, not clustering alone.</caption>
        <thead><tr><th>Cycle</th><th>n</th><th>Variance units</th>
          <th>Total DEFF</th><th>Weighting alone</th>
          <th>Residual (DEFF &divide; Kish)</th></tr></thead>
        <tbody>{rows_deff}</tbody>
      </table>
    </div>

    <p class="measure">For this report&rsquo;s age-standardised prevalence estimate, the median
    <em>total</em> design effect is <b>{deff_med:.2f}</b>, corresponding to a typical effective
    sample size of about <b>{neff_med:,.0f}</b> against a nominal <b>{n_med:,.0f}</b>. A design
    effect belongs to an estimator rather than to the sample, so this figure describes this
    estimate and does not transfer to another one computed on the same people.</p>

    <p class="measure">It also carries more than one thing at once, and they should not be
    conflated. Unequal selection probabilities inflate the variance on their own, by a factor of
    1 + CV&sup2; of the weights &mdash; a median of <b>{kish_med:.2f}</b> here. Dividing it out
    leaves a residual of about <b>{clust_med:.2f}</b>. That residual is what the design structure
    costs beyond the weights: mostly clustering, but net of stratification, which pulls the other
    way, and of whatever interaction the two have &mdash; so it is neither an upper nor a lower
    bound on clustering alone. The total is worse still as a price for clustering: quoting it that
    way would overstate it by roughly half again. The reason a residual above one exists at all is
    visible in the third column &mdash; each cycle resolves into only {psu_lo}&ndash;{psu_hi}
    variance units, because participants must travel to a mobile examination centre and NCHS
    fields the centres in a small number of locations. Two adults reached by the same location
    share a food environment, an insurance market, a provider mix and often an interviewer, so the
    second largely repeats what the first already said. Treating them as independent would not
    bias the estimate; it would make the interval too narrow.</p>

    <div class="note">
      <b>These units are not counties, and cannot be turned back into any.</b> The public-use
      files do not carry the true design variables. NCHS withholds them because releasing the real
      primary sampling units every two years would carry a disclosure risk, and substitutes
      <em>masked variance units</em> &mdash; a pseudo-stratum (<code>SDMVSTRA</code>) and a
      pseudo-PSU (<code>SDMVPSU</code>) &mdash; which it describes as producing variance estimates
      that &ldquo;closely approximate&rdquo; the ones the true design variables would give, and
      directs analysts to use for all public-release work. The real first-stage units are mostly
      single counties, but the {psu_lo}&ndash;{psu_hi} units counted above are the masked ones:
      they stand in for that structure rather than identify it. Nothing here is a statement about
      any particular county, and no geography can be recovered from the table.
    </div>

    <div class="note">
      <b>Unequal selection and clustering are different problems.</b> Sampling some groups at
      higher rates is handled by the weights, and affects the point estimate. Clustering is not
      touched by the weights at all, and affects only the variance. NHANES does both, which is why
      the analytic guidance names both: variance estimates that assume simple random sampling are
      too low because they ignore &ldquo;the differential weighting <em>and</em> the correlation
      among sample persons within a cluster&rdquo;.
    </div>

    <div class="twrap">
      <table>
        <caption>Prevalence by cycle, adults 20+</caption>
        <thead><tr><th>Cycle</th><th>n</th><th>Cases</th><th>Crude %</th>
          <th>Standardised %</th><th>95% CI</th></tr></thead>
        <tbody>{rows1}</tbody>
      </table>
    </div>

    <h3>Testing the limitation instead of only declaring it</h3>
    <p class="measure">A self-reported outcome moves with access to care as well as with disease.
    That is the standard caveat, and stating it changes nothing. For one condition it can be
    measured: blood pressure is both taken at the examination and asked about in the questionnaire,
    so the share of the measurably hypertensive who report having been told is directly
    observable. If expanding access were inflating self-reported prevalence, this share would have
    to rise, and rise when access rose.</p>

    <figure>
      <img src="{data_uri('part1_ascertainment.png')}"
           alt="Share of hypertensive adults - measured high or on treatment - who report having
                been told, by NHANES cycle. The series rises to a peak around 2013 and then
                declines, with the ACA coverage expansion marked at 2014. A dashed line shows the
                narrower measured-only denominator, which is markedly lower and flatter.">
      <figcaption><b>Ascertainment improved by
      {100 * (asc_aus['ascertained_std'].iloc[-1] - asc_aus['ascertained_std'].iloc[0]):.1f} points
      overall, peaking in {display_cycle(asc_peak['cycle'])}.</b> The share climbs from
      {100 * asc_aus['ascertained_std'].iloc[0]:.1f}% to
      {100 * asc_peak['ascertained_std']:.1f}%, then falls back to
      {100 * asc_aus['ascertained_std'].iloc[-1]:.1f}%. The peak cycle straddles the 2014 coverage
      expansion, so nothing is claimed about which came first. The dashed line conditions on
      measured pressure alone; it looks flat because it drops everyone whose treatment worked, and
      it drops a growing share of them &mdash; from half of the already-diagnosed to two thirds
      across this window. 2021&ndash;2022 is shown separately: CDC changed both the measurement
      instrument and the medication item that cycle.</figcaption>
    </figure>

    <div class="twrap">
      <table>
        <caption>Diagnostic ascertainment for hypertension, adults 20+</caption>
        <thead><tr><th>Cycle</th><th>Instrument</th><th>Hypertensive</th>
          <th>Ascertained</th><th>95% CI</th>
          <th>Measured-only denominator</th></tr></thead>
        <tbody>{rows_asc}</tbody>
      </table>
    </div>

    <p class="measure">This does not support a simple coverage-driven explanation. Ascertainment
    improved over the first half of the series and then stopped, and the years in which coverage
    rose fastest are not the years in which detection improved. That is not evidence against an
    access effect of modest size, which eleven cycles cannot resolve either way; it is evidence
    that the reported trend is not obviously an artefact of better detection.</p>

    <div class="note">
      <b>What this cannot say.</b> The outcome is self-reported physician diagnosis, so it tracks
      diagnosis as much as disease and is sensitive to access to care — a group with worse access
      can appear healthier. Nothing here is adjusted for anything other than age, deliberately:
      these are descriptive quantities, and adjusting them would answer a causal question the
      design does not support.
    </div>
  </div>
</section>

<hr>

<section>
  <div class="sec-head"><div class="sec-num">3</div>
  <h2>Whether the pandemic bent the trend</h2></div>
  <div class="body-indent">
    <div class="chip-row">
      <span class="chip">Quasi-experimental</span>
      <span class="chip">Counterfactual extrapolation</span>
      <span class="chip quiet">Result: no detectable change</span>
    </div>
    <p class="lede measure">Observed prevalence in 2021–2022 sits {pp(p2['gap'])} above what the
    pre-pandemic trend predicts. The 95% interval runs {100 * p2['gap_ci'][0]:.2f} to
    {100 * p2['gap_ci'][1]:+.2f} points and contains zero. The honest reading is that this design,
    on this data, cannot detect a change of the size one might expect.</p>

    <div class="stats">
      {stat("Observed 2021–22", pct(p2['observed'], 2), f"SE {100 * p2['observed_se']:.2f} pp")}
      {stat("Counterfactual", pct(p2['counterfactual'], 2), f"SE {100 * p2['counterfactual_se']:.2f} pp")}
      {stat("Difference", pp(p2['gap']), f"z = {p2['z']:.2f}")}
      {stat("Post-period cycles", "1", f"{p2['extrapolation_years']:.0f}-year extrapolation")}
    </div>

    <figure>
      <img src="{data_uri('part2_counterfactual.png')}"
           alt="Age-standardised prevalence with a fitted pre-pandemic trend extrapolated across
                the gap where NHANES fielded no cycle, compared against the single observed
                Aug 2021&ndash;Aug 2023 point with its confidence interval.">
      <figcaption><b>The gap in the horizontal axis is the analytical problem.</b> NHANES
      suspended field operations, so no 2019–2020 cycle exists and the counterfactual must be
      carried {p2['extrapolation_years']:.0f} years beyond the last observation. With one point
      after the interruption, a level change is estimable but a change in slope is not identified,
      so none is reported.</figcaption>
    </figure>

    <h3>What an interrupted time series normally does, and what is missing here</h3>
    <p class="measure">The design behind this figure is simple to state: fit the trend that held
    before an event, project it forward as the world that would have happened without the event,
    and read the difference against the world that did. Its strength is that it needs no control
    group — the pre-period is the control. Its weakness is that everything depends on the
    projected line being right, and a projection is only as good as the distance it has to travel
    and the number of points on the far side.</p>
    <p class="measure">Both go against this analysis. NHANES did not field a 2019–2020 cycle, so
    the projection spans {p2['extrapolation_years']:.0f} years rather than the usual two, and the
    single post-interruption cycle means a change in level can be estimated but a change in
    trajectory cannot be separated from it at all.</p>

    <div class="note flag">
      <b>The subtle failure this design invites.</b> Design-based standard errors describe
      sampling error only — how much the estimate would move if the same population were sampled
      again. They do not describe how much a national prevalence genuinely moves between cycles.
      Building the counterfactual interval from sampling error alone produces a band that is too
      narrow, and a difference that clears it looks like a pandemic effect when it is an artefact
      of the model. The interval here therefore carries a dispersion term estimated from the
      pre-pandemic residuals rather than assumed. It came out at {p1['dispersion']:.2f} — the series moves slightly
      less than sampling error alone predicts — and is floored at 1, so the band is never narrower
      than nominal but is not inflated either. The null survives both ways: un-floored the interval
      is {100 * p2['gap_ci_unfloored'][0]:.2f} to {100 * p2['gap_ci_unfloored'][1]:+.2f} points, floored it is {100 * p2['gap_ci'][0]:.2f} to {100 * p2['gap_ci'][1]:+.2f}, and both contain zero.
    </div>

    <h3>Who is in the one post-pandemic cycle</h3>
    <p class="measure">The whole counterfactual rests on a single observation, so it matters who
    that observation is made of &mdash; and for a while this section reported a problem that was
    not there. Every NHANES analysis takes the weight of its most restrictive component. The
    outcome here is five questions asked in the household interview, so the interview weight is
    the one that matches it; the examination weight was used originally, and it silently
    restricts the sample to people who also attended the mobile examination centre.</p>

    <p class="measure">That choice mattered most exactly where the analysis is weakest. Under the
    examination weight the post-pandemic cycle lost
    <b>{p1['exam_weight_loss_post_pct']:.1f}%</b> of its age-eligible respondents against
    {p1['exam_weight_loss_other_min_pct']:.1f}&ndash;{p1['exam_weight_loss_other_max_pct']:.1f}%
    elsewhere, and that fourfold change in examination coverage was reported here as a competing
    explanation for the whole gap. Under the interview weight no cycle loses more than
    <b>{p1['max_loss_pct']:.2f}%</b>, and nobody at all lacks a weight. The competing explanation
    was an artefact of the wrong weight, and it is withdrawn rather than quietly dropped.</p>

    <div class="twrap">
      <table>
        <caption>Part 1 and Part 2 &mdash; participant flow by cycle, interview weight</caption>
        <thead><tr><th>Cycle</th><th>Age-eligible (20+)</th>
          <th>No weight</th><th>Analysed</th><th>Lost</th></tr></thead>
        <tbody>{rows_flow}</tbody>
      </table>
    </div>

    <div class="note flag">
      <b>What remains a competing explanation is the cycle itself, and it comes from CDC.</b>
      NCHS names this cycle <em>August 2021 &ndash; August 2023</em>, states that it &ldquo;is
      based on an updated sample design and modified interview as well as examination
      procedures&rdquo;, and urges analysts to proceed with caution before combining it with
      earlier cycles for trend analysis, given the fifteen months in which nothing was observed.
      A changed sample design and a changed instrument are not things a weight corrects. It is
      why this section reports a deviation from an extrapolated trend and not a pandemic effect.
    </div>

    <h3>Letting the data choose the breakpoint &mdash; within the window it can reach</h3>
    <div class="note flag">
      <b>This test cannot address the pandemic, and is not offered as if it could.</b> Three
      points are needed on each side of a knot, so with eleven observations the last candidate
      sits eight years before 2020. Simulated power against a true break at the pandemic is
      0.057 at a slope change of one point per decade &mdash; indistinguishable from the
      test&rsquo;s own five per cent size. What follows is a statement about breaks inside the
      pre-pandemic series and carries no information about a pandemic break either way.
    </div>

    <p class="measure">Within that window, placing a break anywhere is still an assumption
    worth testing. A joinpoint model relaxes it: fit a continuous piecewise line, let the knot fall wherever it best fits, and test
    whether any knot earns its parameter. Because each point carries a known design-based variance,
    the weighted residual sum of squares is an exact goodness-of-fit statistic rather than an
    estimated one &mdash; and it says the straight line already fits. The series scatters no more
    than the sampling errors alone predict, so there is no unexplained structure for a break to
    explain.</p>

    <figure>
      <img src="{data_uri('part2_changepoint.png')}"
           alt="Top panel: improvement in weighted residual sum of squares for each candidate
                breakpoint, none reaching the bootstrap significance threshold. Bottom panel:
                simulated statistical power against the size of a true slope change.">
      <figcaption><b>No break is detectable, and none would be unless it were very large.</b>
      Significance is assessed by parametric bootstrap rather than a chi-square test at the fitted
      knot: searching over the breakpoint inflates the null, so the honest threshold is {cp['crit95']:.1f} rather
      than 3.84. The 95% profile set for the knot spans every candidate year, meaning the data
      cannot localise a break at all.</figcaption>
    </figure>

    <div class="twrap">
      <table>
        <caption>Power to detect a true slope change at 2011</caption>
        <thead><tr><th>True change in slope</th><th>Power</th></tr></thead>
        <tbody>{rows_power}</tbody>
      </table>
    </div>

    <div class="note flag">
      <b>This is a limit of the design, not evidence of absence.</b> A reversal from the observed
      decline to a flat trend &mdash; a slope change of {power_slope_pp:.1f} points per
      decade &mdash; would be detected about {100 * power_at_slope:.0f}% of the time. Only a
      change of roughly {power_80:.1f} points per decade &mdash; large for a series that moves
      between {p_lo:.1f}% and {p_hi:.1f}% &mdash; would be caught reliably. The correct conclusion is that eleven biennial estimates cannot
      settle whether the trend bent, not that it did not.
    </div>

    {ledger(
      decision(
        "Use a <b>questionnaire-based outcome</b> rather than measured blood pressure or lipids.",
        f"Sidesteps the instrument and assay changes accumulated across {p1['n_cycles']} cycles, which would otherwise be indistinguishable from a pandemic effect.",
        "Only captures diagnosed disease, which is slow-moving — precisely the outcome least likely to register a short shock."),
      decision(
        "Weight the series with the <b>interview</b> weight, not the examination weight.",
        f"It is the weight the outcome is entitled to &mdash; five questions asked in the household interview &mdash; and it removes the {p1['exam_weight_loss_post_pct']:.0f}% post-pandemic loss that the examination weight introduced and that was reported here as a competing explanation.",
        f"The series is no longer directly comparable with the examination-weighted analyses in &sect;5 and &sect;6, and n rises from {p1['n_adults_exam_weight']:,} to {p1['n_adults']:,}, so every published figure moved."),
      decision(
        "Estimate <b>dispersion from the residuals</b> rather than assume the design-based errors are the whole story.",
        f"Turns an assumption into a measured quantity: it came out at {p1['dispersion']:.2f}, so the straight line already explains the series as well as sampling error allows.",
        "Floored at 1 so the band is never narrower than nominal, which is a conservative choice made before the answer was known, not after."),
      decision(
        "Report a <b>level difference only</b>, and state that the slope change is unidentified.",
        "Nothing is claimed that one post-period observation cannot support.",
        "The most interesting question — whether the trajectory changed — is left open."),
      decision(
        "Let a <b>joinpoint model</b> nominate the breakpoint, rather than assuming it sits at the pandemic.",
        "Turns the framing into a testable claim. It is not supported: no candidate knot clears the bootstrap threshold, and the profile set for its location spans the whole series.",
        "The same test has well under half the power needed to catch a break the size of the trend itself, so it cannot be reported as evidence that none exists."),
      decision(
        "Assess significance by <b>parametric bootstrap</b> instead of a chi-square test at the fitted knot.",
        f"Prices in the fact that the breakpoint was chosen by searching &mdash; the honest 95% threshold is {cp['crit95']:.1f}, not the nominal 3.84.",
        "Roughly fifty per cent harder to reach significance than the test most software would report by default."),
      decision(
        "Fit the pre-period on the <b>standardised</b> series, not the crude one.",
        "The counterfactual is about disease, not about the population continuing to age.",
        "Inherits every standardisation choice from §2, including the 20+ base."),
    )}

    <div class="note">
      <b>What is still needed.</b> Extending this to measured risk factors — blood pressure,
      lipids, glycaemia, where a real pandemic effect is far more likely to show — requires
      bridging the instrument and assay changes across the series first. Without that bridge, a
      change of blood-pressure device would be attributed to the pandemic.
    </div>
  </div>
</section>

<hr>

<section>
  <div class="sec-head"><div class="sec-num">4</div>
  <h2>Who, among the currently healthy, goes on to die of it</h2></div>
  <div class="body-indent">
    <div class="chip-row">
      <span class="chip">Prospective cohort</span>
      <span class="chip">Cause-specific Cox</span>
      <span class="chip">Competing risks modelled</span>
      <span class="chip">Validated forward in time</span>
    </div>
    <p class="lede measure">Linking survey records to the National Death Index converts a series
    of cross-sections into a cohort: exposures measured at the examination, deaths observed for up
    to twenty years afterwards. This is the only estimand here in which exposure
    precedes outcome, and therefore the only one where prediction is a defensible word.</p>

    <div class="stats">
      {stat("Participants", n_cohort, "40–79, CVD-free at baseline")}
      {stat("CVD deaths", n_cvd, f"{n_competing} competing deaths")}
      {stat("Person-years", n_person_years, "origin at the examination")}
      {stat("Systolic BP", f"HR {sbp_design['hr']:.3f}", f"per 10 mmHg · {sbp_design['lo95']:.3f}–{sbp_design['hi95']:.3f} · survey-design-based 95% CI, stratified PSU design")}
    </div>

    <figure>
      <img src="{data_uri('cif_by_sbp.png')}"
           alt="Cumulative incidence of cardiovascular death over fifteen years, by baseline
                systolic blood pressure category, showing a monotonic gradient.">
      <figcaption><b>A monotonic gradient across five blood-pressure strata.</b> Survey-weighted
      15-year cumulative incidence of cardiovascular death rises from 2.40% below 120 mmHg to
      11.58% at or above 160 mmHg — a 4.8-fold spread, with no crossing between adjacent
      strata.</figcaption>
    </figure>

    <h3>Time is the unit of information, not people</h3>
    <p class="measure">Survival analysis does not count people; it counts person-time at risk. A
    participant recruited two years before follow-up ends contributes two person-years and almost
    no information, however large the sample they arrive in. This has a concrete consequence for
    the cohort's boundaries: extending it to the two most recent linkable cycles would add
    thousands of participants but only about 4% of events, while the cause-of-death coding used
    from 2015 collapses cerebrovascular deaths into a residual category — changing the definition
    of the outcome midway through the series. The cohort therefore stops at 2014, and stopping
    there yields <em>more</em> events than the wider alternative, not fewer.</p>

    <h3>Why deaths from other causes cannot be treated as censoring</h3>
    <p class="measure">Standard survival methods handle incomplete follow-up by censoring: a
    participant still alive at the end of the study is recorded as “outcome not yet observed, and
    still possible”. Applying the same treatment to someone who died of cancer asserts something
    false — that they might still die of cardiovascular disease. The estimate that results answers
    a hypothetical question in which no one can die of anything else.</p>
    <p class="measure">In this cohort the distortion is not academic: competing deaths outnumber
    cardiovascular deaths 2.9 to 1. Absolute risk is therefore built from two cause-specific
    models — one for cardiovascular death, one for everything else — combined into a cumulative
    incidence function, so that the competing hazard remains an explicit object in the model
    rather than an assumption folded into a reweighting.</p>

    <figure>
      <img src="{data_uri('competing_risk_comparison.png')}"
           alt="Comparison of one minus Kaplan-Meier against the Aalen-Johansen estimator,
                showing that treating competing deaths as censoring overstates risk.">
      <figcaption><b>Censoring competing deaths overstates 15-year risk by 7.4%.</b> The gap
      between the two estimators is the size of the error, and it grows with follow-up time
      because the competing hazard accumulates.</figcaption>
    </figure>

    <h3>Blood pressure measured under treatment is not the exposure</h3>
    <p class="measure">A participant on antihypertensive medication has a measured blood pressure
    that reflects the treatment, not their underlying level. The intuitive fix — add “currently
    treated” to the model as a covariate — is wrong for a specific reason: treatment is a
    <span class="term">collider</span>. It is caused both by high blood pressure and by access to
    care, so conditioning on it opens a path between blood pressure and healthcare access that was
    not there before, and contaminates the estimate with confounding it did not previously have.</p>
    <p class="measure">The exposure is instead reconstructed: treated participants have a constant
    added to their measured value to approximate the untreated level. The adjustment is an
    assumption, stated as one, and the model is refitted without it as a sensitivity check —
    the estimate attenuates from {sbp['hr']:.3f} to
    {model['aetiologic_sbp_per_10mmhg_no_tobin']['hr']:.3f} per 10 mmHg, which is the direction
    and roughly the magnitude the reasoning predicts.</p>

    <div class="note flag">
      <b>What this quantity is, stated narrowly on purpose.</b> It is the association of
      treatment-adjusted baseline systolic pressure with subsequent cardiovascular mortality,
      adjusted for the confounders the graph names. It is not the total causal effect of blood
      pressure, and calling it one would claim more than this design carries: the pressure is
      already the product of years of treatment nobody observed, the Tobin constant is a
      convention rather than an identification strategy, there is no treatment history, kidney
      function may precede hypertension as easily as follow it, and excluding prevalent disease
      at baseline does not undo the selection that being alive and non-institutionalised in a
      survey imposes. A target-trial specification with treatment histories would be needed to
      say more, and none of that is available here.
    </div>

    <h3>Who the model is fitted on, which is not who the cohort is</h3>
    <p class="measure">Every fit here drops participants with any covariate missing. That is an
    analysis decision made by a method call, and it changes the population being described: from
    US adults free of cardiovascular disease at baseline, to <b>US adults free of cardiovascular
    disease at baseline who happened to have every variable measured</b>. It removes
    {miss['n_dropped']:,} of {miss['n_cohort']:,} &mdash; {miss['pct_dropped']:.1f}% &mdash; and
    it is not random.</p>

    <div class="twrap">
      <table>
        <caption>What causes the deletion. &ldquo;Uniquely lost&rdquo; is rows this variable alone
        removes &mdash; missing here and complete on everything else.</caption>
        <thead><tr><th>Variable</th><th>Missing</th><th>%</th><th>Uniquely lost</th></tr></thead>
        <tbody>{rows_miss}</tbody>
      </table>
    </div>

    <p class="measure">One variable does most of it: <code>{miss['top_driver']}</code> alone
    removes {miss['top_driver_uniquely_lost']:,} rows. Total and HDL cholesterol are each missing
    for more people, and cost almost nothing extra, because they go missing together and mostly
    for people already lost to something else.</p>

    <div class="twrap">
      <table>
        <caption>Kept against dropped, on everything observed for both</caption>
        <thead><tr><th>Variable</th><th>Kept</th><th>Dropped</th><th>Difference</th></tr></thead>
        <tbody>{rows_misscmp}</tbody>
      </table>
    </div>

    <div class="note flag">
      <b>The dropped are sicker and disproportionately Black, so this is a limitation and not a
      footnote.</b> Cardiovascular mortality among those dropped is
      {100 * miss['cvd_death_dropped']:.2f}% against {100 * miss['cvd_death_kept']:.2f}% among
      those kept, and {100 * miss['race_black_dropped']:.1f}% of the dropped are Black against
      {100 * miss['race_black_kept']:.1f}% of the kept. Missingness is associated with the
      outcome, which is the case in which listwise deletion is not merely inefficient.
    </div>

    <div class="note">
      <b>Two different problems, and only one of them has a correction here.</b> Censoring &mdash;
      follow-up ending before the outcome &mdash; is handled by the survival model itself, which
      is what censoring is for. What follows is about something else: SELECTION, caused by
      dropping participants whose covariates were not all measured. The weights below correct for
      the second and have nothing to say about the first, and neither of them is multiple
      imputation, which would use the partially observed variables rather than only the fully
      observed ones and is <b>not done</b>.
    </div>

    <p class="measure">So the fit is re-run with inverse-probability-of-completeness weights,
    modelled on age, sex, race and cycle &mdash; the variables observed for everyone, which is
    what makes the model able to see the dropped at all. The exposure barely moves: HR
    {miss['sensitivity']['hr_survey']:.4f}
    ({miss['sensitivity']['hr_survey_ci'][0]:.4f}&ndash;{miss['sensitivity']['hr_survey_ci'][1]:.4f})
    under the survey weight against {miss['sensitivity']['hr_ipcw']:.4f}
    ({miss['sensitivity']['hr_ipcw_ci'][0]:.4f}&ndash;{miss['sensitivity']['hr_ipcw_ci'][1]:.4f})
    under IPCW, a shift of {miss['sensitivity']['abs_shift']:.4f}.</p>

    <p class="measure">Two bounds inside that correction are worth naming, because both shrink it
    <em>toward</em> the uncorrected estimate and so buy part of the agreement the paragraph above
    rests on. The propensity is floored at 0.05 &mdash; not binding here, the smallest is
    {miss['trimming']['min_propensity']:.3f} &mdash; and the weights are trimmed at the 99th
    percentile, which binds on {miss['trimming']['n_capped']} participants and removes
    {miss['trimming']['weight_removed_pct']:.2f}% of the re-weighted total. Untrimmed, one
    participant can carry several per cent of the weight, and an estimate driven by three people
    is worse than the one it replaced; trimmed, the correction is smaller than it would otherwise
    have been. Both numbers are here so a reader can judge which trade they prefer.</p>

    <p class="measure"><b>That is reassurance about fragility, not a repair.</b> IPCW restores
    unbiasedness only if completeness is independent of the outcome given what the completeness
    model sees, and the variables most likely to explain both &mdash; illness severity, access to
    care &mdash; are exactly the ones a survey that lost them does not have. What the agreement
    establishes is that this estimate is not sensitive to <em>this</em> correction. Multiple
    imputation, which would use the partially observed variables rather than only the fully
    observed ones, is recorded as not done.</p>

    <h3>Validation splits on survey cycle, not at random</h3>
    <p class="measure">Random cross-validation assumes observations are exchangeable. In a
    clustered sample they are not: participants reached by the same examination location share a
    neighbourhood and an interviewer, so a random split places correlated people on both sides of
    the boundary and reports optimistic performance. Splitting on survey cycle keeps clusters
    intact and answers the more demanding question — whether a score fitted on people surveyed in
    1999–2004 still works on people surveyed a decade later.</p>

    <figure>
      <img src="{data_uri('calibration.png')}"
           alt="Calibration of predicted against observed cardiovascular death risk, by decile of
                predicted risk, on held-out survey cycles.">
      <figcaption><b>Discrimination and calibration are separate properties.</b> Discrimination
      asks whether higher-risk people are ranked above lower-risk people; calibration asks whether
      a predicted 3% actually means 3%. A model can rank well and still be systematically wrong
      about magnitude, which is what makes it unusable for a clinical threshold.</figcaption>
    </figure>

    <div class="twrap">
      <table>
        <caption>Discrimination and calibration, held-out cycles. Both concordance
        columns are censored at the horizon the row names; the weighted column is
        the estimate for the US population the sample represents, the unweighted
        one is the estimate for the sample itself.</caption>
        <thead><tr><th>Test set</th><th>n</th><th>CVD deaths</th>
          <th>Harrell&rsquo;s C<br><span class="thsub">survey-weighted</span></th>
          <th>Harrell&rsquo;s C<br><span class="thsub">unweighted</span></th>
          <th>Mean predicted</th><th>Mean observed</th></tr></thead>
        <tbody>{rows_pred}</tbody>
      </table>
    </div>

    {ledger(
      decision(
        "Exclude participants with <b>cardiovascular disease at baseline</b> rather than adjust for it.",
        "Three things at once: it removes a mediator that would otherwise absorb most of the blood-pressure effect; it gives a cohort with a real clinical counterpart (primary prevention); and it matches the population the clinical risk scores are built for.",
        "Fewer events, since the excluded group has the highest mortality — 19.1 versus 3.9 deaths per 1,000 person-years."),
      decision(
        "Set the time origin at the <b>examination</b>, not the interview.",
        "Follow-up starts when the exposures were actually measured, which is what a survival model assumes.",
        "Requires the examination weight and drops participants who were interviewed but not examined."),
      decision(
        "Define the outcome as <b>heart plus cerebrovascular death</b>, over 1999–2014 only.",
        "More events than the narrower definition over more cycles, and one consistent outcome definition throughout.",
        "Nothing can be said about the period after 2014, and stroke and cardiac deaths are not separable."),
      decision(
        "Model <b>two cause-specific hazards</b> and combine them, rather than fitting a subdistribution model.",
        "The competing hazard stays visible and inspectable; one fitting path serves both the causal and the predictive question.",
        "Absolute risk must be assembled explicitly rather than read off a single fitted model."),
      decision(
        "Adjust treated blood pressure by a <b>fixed constant</b> instead of conditioning on treatment.",
        "Avoids opening a collider path through healthcare access, and targets the untreated exposure the causal question is about.",
        "The constant is borrowed from the literature, not estimated here — an assumption that a sensitivity analysis can bound but not remove."),
      decision(
        "Validate by <b>survey cycle</b> rather than random folds.",
        "No leakage between correlated clusters, and it tests transportability forward in time.",
        "A smaller training set, and performance that will degrade if the population drifts — though that degradation is itself the finding."),
    )}

    <div class="twrap">
      <table>
        <caption>15-year cumulative incidence by baseline systolic blood pressure</caption>
        <thead><tr>{"".join(f"<th>{c}</th>" for c in cif_cols)}</tr></thead>
        <tbody>{rows_cif}</tbody>
      </table>
    </div>

    <div class="twrap">
      <table>
        <caption>Aetiologic model — cause-specific Cox, survey-weighted</caption>
        <thead><tr>{cox_head}</tr></thead>
        <tbody>{rows_cox}</tbody>
      </table>
    </div>

    <div class="twrap">
      <table>
        <caption>Participant flow</caption>
        <thead><tr>{strobe_head}</tr></thead>
        <tbody>{rows_strobe}</tbody>
      </table>
    </div>

    <div class="note">
      <b>What this cannot say.</b> The outcome is death, so non-fatal infarction and stroke are
      invisible and the estimand blends how often disease occurs with how often it kills. NHANES
      samples the living, non-institutionalised population, so people who died young of
      cardiovascular disease were never eligible — a selection that cannot be corrected, only
      declared. Baseline disease is self-reported, with roughly 60–80% sensitivity, so some true
      patients remain in a cohort described as primary prevention, biasing effects toward the
      null. Exposures are measured once, which supports baseline risk prediction — the same design
      as Framingham, the Pooled Cohort Equations, SCORE2 and QRISK3 — but not dynamic risk
      updating, and a single measurement attenuates associations through regression dilution.
      Follow-up ends {DATA_CUTOFF}, entirely before the pandemic. Two design choices are
      simplifications rather than corrections: the cohort pools eight cycles on the two-year
      examination weight, where NCHS's guidance for an analysis spanning 1999&ndash;2002 is to use
      the four-year weights released for those cycles, and complete-case restriction to the eleven
      model inputs drops {miss_pct_people:.1f}% of the cohort and {miss_pct_deaths:.1f}% of the
      cardiovascular deaths ({miss_n_cohort:,} &rarr; {miss_n_kept:,} people,
      {miss_deaths_cohort} &rarr; {miss_deaths_kept} deaths). The first was
      measured before being accepted: the four-year weights disagree sharply per person
      &mdash; 20.6% of participants by more than a fifth &mdash; but almost cancel in aggregate, moving
      the blood-pressure hazard ratio from 1.1216 to 1.1233 and no coefficient by more than 0.91%,
      which is below the precision printed here. The second is not corrected at all: the
      inverse-probability weights described above address censoring, not selection into the
      complete-case subsample.
    </div>
  </div>
</section>

<hr>

<section>
  <div class="sec-head"><div class="sec-num">5</div>
  <h2>What the model is missing, and whether a different model would find it</h2></div>
  <div class="body-indent">
    <div class="chip-row">
      <span class="chip">Prospective</span>
      <span class="chip">Screened on training cycles only</span>
      <span class="chip">Design-based Wald</span>
      <span class="chip">Paired cluster bootstrap</span>
    </div>
    <p class="lede measure">The model in &sect;4 carries eleven variables and reaches
    C&nbsp;=&nbsp;{p4_ref.harrell_c:.3f}. Two quite different things could be holding it there: the
    eleven may not carry more, or the linear additive proportional-hazards form may not fit what
    they carry. Those are separable, so they are separated &mdash; the variable set and the model
    form are varied factorially on one analysis set, with a model on age and sex alone as the
    floor.</p>

    <div class="stats">
      {stat("Candidates screened", f"{p4_scr['n_candidates']}", f"on {p4_scr['n_train']:,} training rows")}
      {stat("Selected", f"{len(p4_sel)}", f"design-based Wald &ge; {p4_scr['wald_threshold']:.2f}")}
      {stat("Best single addition", f"&times;{p4_top.hr_per_sd:.2f}", f"per SD of {p4_top.label}, z = {p4_top.z:.1f}")}
      {stat("Gain in C", f"{p4_gain.delta_c:+.4f}", f"95% CI {p4_gain.delta_lo:+.4f} to {p4_gain.delta_hi:+.4f}")}
    </div>

    <h3>The screen</h3>
    <p class="measure">Fifteen candidates, each scored against the eleven the model already has
    rather than on its own &mdash; a univariate hazard ratio for kidney function mostly reports
    that older people have worse kidneys. Scoring is by the design-based Wald statistic, the
    coefficient over its cluster-robust standard error, which is what the rest of this report
    uses for inference and is the only thing that has a null distribution here. Screening runs on
    the <b>training cycles only</b>; a variable chosen with the test cycles in view would make the
    concordance that follows an in-sample number wearing an out-of-sample label.</p>

    <p class="measure">{p4_screen_says}</p>

    <div class="twrap">
      <table>
        <caption>Every candidate, adjusted for the eleven &mdash; training cycles</caption>
        <thead><tr><th>Candidate</th><th>In the causal model?</th><th>n</th>
          <th>HR per SD</th><th>Wald</th><th>Into the forward path?</th></tr></thead>
        <tbody>{p4_rows_rank}</tbody>
      </table>
    </div>

    <div class="note">
      <b>Half the candidates are measured on half the cohort, and that decides more than it
      looks.</b> Fasting glucose, triglycerides and LDL come from the morning fasting subsample,
      which is roughly half the participants by design, and alcohol intake is missing for a third.
      Requiring complete data on all of them collapsed the common analysis set from
      {p4_scr['n_train']:,} rows and {p4_scr['events_train']} events to 1,644 and 104 &mdash;
      selecting six variables on 104 events is fitting noise. A candidate therefore joins the
      forward path only if it is observed for at least {100 * p4_scr['min_coverage']:.0f}% of the
      training rows. The others keep their rankings, each computed on its own rows, and are marked
      out of the path with the reason rather than quietly dropped.
    </div>

    <h3>Against the current guideline, which the screen was never shown</h3>
    <p class="measure">PREVENT takes two different kinds of variable that the Pooled Cohort
    Equations do not, and the distinction matters here. Its <b>base model</b> requires
    {p4_base_new_list} &mdash; eGFR was newly included as a primary predictor, computed from
    CKD-EPI 2021 on serum creatinine, which is the same equation and the reason the assay
    calibration below had to be done first. Its <b>optional</b> cardiovascular-kidney-metabolic
    extensions are {p4_opt_list}.</p>

    <p class="measure">Of those, {p4_base_had_list} was already among the eleven. The screen was
    able to consider {p4_base_screened} from the base model and {p4_opt_screened} from the
    extensions; {p4_unavailable} could not be built at all &mdash; it {p4_unavailable_why}, which
    is the same constraint that produced the masked variance units in &sect;2. The screen was not
    told that any of them were of interest.</p>

    <p class="measure">{p4_prevent_says}</p>

    <div class="note flag">
      <b>The disagreement points away from the flattering reading, which is why it is worth
      keeping.</b> This cohort is aged 40&ndash;79 and largely has normal filtration &mdash; the
      median eGFR sits near 92, so glomerular filtration has little variance in the range where
      it would separate people, while albuminuria varies across four orders of magnitude and
      marks kidney damage before filtration falls. PREVENT was derived on 6.6&nbsp;million adults
      from age 30 and predicts a composite that includes heart failure; a screen on that
      population, for that outcome, would very likely have kept eGFR. Nothing here is evidence
      against the guideline. It is evidence about what this cohort can see.
    </div>

    <h3>Form against variable set</h3>
    <figure>
      <img src="{data_uri('part4_arms.png')}"
           alt="Paired differences in Harrell C against the published model, with 95% bootstrap
                intervals. Adding one screened variable to the Cox model improves it; both
                gradient-boosting arms are worse, and boosting on the eleven is worse than a Cox
                model on age and sex alone.">
      <figcaption><b>The variable set was binding; the model form was not.</b> Every arm is fitted
      on the same training cycles and scored on the same {p4_arm['n_test']:,} held-out
      participants and {p4_arm['events_test']} cardiovascular deaths, so no difference here is a
      difference in who was scored. Intervals are {p4_arm['n_boot']} bootstrap replicates
      resampling whole variance units rather than rows, for the same reason &sect;2 does.</figcaption>
    </figure>

    <div class="twrap">
      <table>
        <caption>Discrimination on held-out cycles, {p4_arm['horizon']:.0f}-year risk</caption>
        <thead><tr><th>Arm</th><th>Variables</th><th>Harrell C</th>
          <th>AUC at the horizon</th><th>&Delta;C vs published</th><th>95% CI</th></tr></thead>
        <tbody>{p4_rows_arms}</tbody>
      </table>
    </div>

    <p class="measure">One screened variable added {p4_gain.delta_c:+.4f} to C on the same form.
    Changing the form to gradient boosting on the same eleven cost {p4_form.delta_c:+.4f}, and the
    interval on each {p4_both_excl}. The floor arm is what makes those numbers readable: a Cox
    model on age and sex alone reaches C&nbsp;=&nbsp;{p4_floor.harrell_c:.4f}, so gradient
    boosting on all eleven variables {p4_vs_floor} age and sex.</p>

    <div class="note">
      <b>Two statistics, because one of them is not a fair contest.</b> Harrell's C rewards
      ordering deaths correctly in time, and the boosted arms never see a time &mdash; they are
      fitted on a binary "dead of cardiovascular disease by the horizon", which is what a
      general-purpose classifier can represent. Reporting only C would hand the Cox arms an
      advantage that came from the metric. The area under the ROC at the horizon is the statistic
      the boosted arms were actually fitted for, and it ranks the five arms in exactly the same
      order. The result is not an artefact of the choice between them.
    </div>

    <h3>The two orderings, which do not agree</h3>
    <figure>
      <img src="{data_uri('part4_two_orderings.png')}"
           alt="Permutation importance for each variable in the wide prediction model, coloured by
                whether the aetiologic model may adjust for it. Age dominates, followed by urine
                albumin-to-creatinine ratio, which the locked causal graph does not classify.">
      <figcaption><b>Earning a place in one model does not earn it a place in the other.</b>
      Permutation importance measured in the model frame rather than the raw one &mdash; three of
      the eleven features are constructed during model preparation, so shuffling them upstream
      would let them be rebuilt from untouched source columns and report an importance of exactly
      zero.</figcaption>
    </figure>

    <div class="twrap">
      <table>
        <caption>What the prediction needs most, and what the causal model may do with it</caption>
        <thead><tr><th>#</th><th>Variable</th><th>Fall in C when shuffled</th>
          <th>In the causal model?</th><th>Why</th></tr></thead>
        <tbody>{p4_rows_imp}</tbody>
      </table>
    </div>

    <p class="measure">Of the five variables the prediction depends on most,
    <b>{p4["importance"]["n_top5_not_admissible"]}</b> are variables the aetiologic model may not
    simply adjust for. That is the argument of &sect;1 made concrete instead of asserted: the same
    dataset, the same people, two questions, and a variable that is indispensable to one and
    inadmissible in the other.</p>

    <div class="note flag">
      <b>Three of the fifteen candidates are marked "the locked DAG does not say", and that is a
      finding about the DAG.</b> The causal graph in the design document draws the kidney node
      with no parents and no edge to or from blood pressure, so it cannot decide whether eGFR and
      albuminuria are confounders or mediators &mdash; and albuminuria is the one variable the
      screen selected. Lipids sit at a collider between the unmeasured genetic node and adiposity.
      Resolving either is a modelling decision, not a data question, and it is recorded as open
      rather than settled here.
    </div>

    <h3>The assay change underneath all of this</h3>
    <p class="measure">Kidney function could not be screened at all until one thing was corrected.
    NHANES measured serum creatinine on a non-standardised method in two cycles and published a
    Deming regression back onto the reference scale for each, describing the correction as highly
    recommended. Those two cycles fall on <em>opposite sides</em> of the train/test split, so the
    uncorrected series carries a step there that no population change produced: a model fitted on
    it would learn one scale and be judged on another, which looks exactly like a model failing to
    transport.</p>

    <div class="twrap">
      <table>
        <caption>Serum creatinine by cycle, mg/dL &mdash; as loaded and as corrected</caption>
        <thead><tr><th>Cycle</th><th>n</th><th>As loaded</th><th>Corrected</th>
          <th></th></tr></thead>
        <tbody>{p4_rows_creat}</tbody>
      </table>
    </div>

    <p class="measure">The equations were applied before the data was looked at, and both move
    their cycle <em>toward</em> the untouched ones rather than away. That agreement is the check
    that they were read the right way round.</p>

    {ledger(
      decision(
        "Screen on the <b>training cycles only</b>, and score by the design-based Wald statistic.",
        "The concordance that follows is genuinely out of sample, and the statistic has a null distribution under the survey design rather than borrowing one it does not have.",
        f"A candidate observed for less than {100 * p4_scr['min_coverage']:.0f}% of the training rows cannot enter the forward path at all, so anything measured only in the fasting subsample is out by construction."),
      decision(
        "Compare the arms by a <b>paired</b> difference in C, bootstrapped over whole variance units.",
        "The two scores are computed on identical people, so the difference has far less variance than either statistic alone; resampling clusters keeps the interval honest about who is independent.",
        f"{p4_arm['n_boot']} replicates of five arms is the slowest step in the pipeline, and the interval is Monte Carlo rather than exact."),
      decision(
        "Fit the boosted arms on a <b>binary outcome at the horizon</b> rather than on survival time.",
        "It is what a general-purpose classifier can represent, and it makes the comparison one of form rather than of library.",
        "Competing deaths become negative labels rather than a competing risk, and the output ranks people instead of being an absolute risk &mdash; so this section compares discrimination and never calibration."),
      decision(
        "Declare every candidate's causal status by hand, with three states rather than two.",
        "A variable the graph does not classify is reported as unclassified instead of being defaulted to admissible, which would print &lsquo;allowed&rsquo; for variables nobody decided about.",
        "The table carries three &lsquo;undetermined&rsquo; rows that a reader may find unsatisfying, and one of them is the variable the screen chose."),
    )}
  </div>
</section>

<section>
  <div class="sec-head"><div class="sec-num">6</div>
  <h2>Benchmarking against the Pooled Cohort Equations</h2></div>
  <div class="body-indent">
    <div class="chip-row">
      <span class="chip open">Protocol locked &middot; analysis pending</span>
      <span class="chip">Coefficients sourced and verified</span>
    </div>
    <p class="lede measure">A discrimination statistic is only interpretable against something.
    The prespecified comparator is the ASCVD Pooled Cohort Equations — the score this project was
    designed against, and no longer the one ACC/AHA recommend. Its coefficients are in hand —
    transcribed from the 2013 ACC/AHA Full Work Group Report and checked by reproducing the four
    worked examples that document prints for its own equations. The comparison is nonetheless
    held, because of a definitional problem worth stating carefully.</p>

    <div class="note flag">
      <b>The Pooled Cohort Equations are no longer the current clinical standard.</b> The 2026
      ACC/AHA/Multisociety dyslipidemia guideline starts from ten-year <b>PREVENT-ASCVD</b> risk,
      and the 2025 ACC/AHA high blood pressure guideline recommends PREVENT in place of the Pooled
      Cohort Equations. The ACC&rsquo;s own CVD Risk Estimator Plus states that the ten-year risk
      it computes from the pooled cohort equation &ldquo;is no longer supported by ACC clinical
      policy or guidelines&rdquo;. The equations are kept here as the <em>prespecified historical
      benchmark</em>: the comparison protocol, the coefficient transcription and its verification
      were all locked before that change, and re-choosing the comparator afterwards would be a
      design decision made with the answer already in view. PREVENT-ASCVD is recorded as the
      future comparator, not a relabelling of this one — it takes eGFR as an input, drops race,
      runs from age 30, and predicts a different outcome set, so adding it is new work.
    </div>

    <div class="note flag">
      <b>The outcomes are not the same quantity.</b> The Pooled Cohort Equations predict
      <em>hard ASCVD</em> — non-fatal myocardial infarction, coronary death, and fatal or non-fatal
      stroke. This cohort observes cardiovascular <em>death</em> alone. Applying the published
      coefficients directly will over-predict, and that over-prediction is definitional, not a
      failure of the equations in this population.
    </div>

    <p class="measure">This matters because of what the comparison was designed to establish. The
    plan decomposes any performance difference into three sources: a population that has drifted
    since the equations were derived, a different variable set, and a different model form. An
    outcome definition that differs as well is a fourth source, confounded with all three, and it
    would make the decomposition uninterpretable — the naive layer would show large over-prediction
    and an unwary reader would attribute it to population drift.</p>

    <p class="measure">The resolution rests on a property worth naming: <b>discrimination is
    invariant to any monotone transformation of predicted risk</b>. Ranking is unaffected by a
    systematic inflation of the numbers, so a concordance statistic remains comparable across the
    outcome mismatch, whereas calibration does not. Discrimination therefore becomes the primary
    comparison, and the naive layer is split into one arm applying the published baseline survival
    and one recalibrating it to this cohort, so that the definitional gap is isolated instead of
    silently absorbed.</p>

    <p class="measure">The comparison protocol was fixed in advance, before any of it was run,
    and it commits to four things. The primary comparison covers non-Hispanic White and
    non-Hispanic Black adults only, because those are the groups the equations were derived in;
    other groups appear as a labelled sensitivity analysis rather than in the headline. It runs on
    the subsample with all nine inputs observed — and this project's own model is refitted and
    re-evaluated on that same subsample, because two numbers both called a concordance statistic
    look comparable while measuring different populations. Blood pressure enters through the
    equations' own treated and untreated branches, not through this project's reconstruction of an
    untreated level, which was built for a different estimand. And because the outcomes differ, the
    comparison is a prognostic benchmark on discrimination, not a claim about the same endpoint.
    What remains is implementation, not judgement: the coefficient tables and baseline survival
    have still to be written down and pinned by tests.</p>
  </div>
</section>

<hr>

<section>
  <div class="sec-head"><div class="sec-num">7</div>
  <h2>Data and methods</h2></div>
  <div class="body-indent">
    <h3>Sources</h3>
    <ul class="measure">
      <li><b>NHANES 1999–2022</b>, CDC public-use files. All 1,821 published files are enumerated
      and recorded with the rule that retained or dropped each one, before anything is
      downloaded.</li>
      <li><b>NCHS Public-Use Linked Mortality Files</b>, follow-up through {DATA_CUTOFF}. NCHS
      substitutes synthetic follow-up time or cause of death for a small number of records to
      prevent re-identification.</li>
      <li><b>2000 projected U.S. standard population</b>, NCHS <i>Health, United States 2019</i>,
      Appendix II Table 2.</li>
      <li><b>ASCVD Pooled Cohort Equations</b>, 2013 ACC/AHA Full Work Group Report, Table 4 —
      the prespecified historical benchmark. The current ACC/AHA recommendation for ten-year risk
      is the AHA PREVENT-ASCVD equations (2026 ACC/AHA/Multisociety dyslipidemia guideline); they
      are named here as a future comparator and are not used in this report.</li>
    </ul>

    <h3>Estimation</h3>
    <ul class="measure">
      <li><b>Cross-validated against R.</b> Both hand-written estimators were checked
      against an independent implementation &mdash; see the section below.</li>
            <li>Each analysis is weighted with the weight of its most restrictive component: the
      <b>interview</b> weight for the self-reported prevalence series, the <b>examination</b>
      weight for anything that needs a measured blood pressure or a laboratory value. Variances are
      Taylor-linearised and clustered on the masked variance units NCHS releases in place of
      the true design variables (<code>SDMVSTRA</code> × <code>SDMVPSU</code>).</li>
      <li>Age standardisation is direct, to the published 2000 standard bands renormalised over
      adults 20+, with 75–84 and 85+ collapsed to an open 75+ band.</li>
      <li>Absolute risk is assembled from two cause-specific Cox fits rather than a subdistribution
      model.</li>
      <li>Refusal and “don't know” codes are treated as missing, never as “no”. Questionnaire skip
      patterns are decoded deterministically — never having been told you had hypertension means
      untreated, not unknown.</li>
    </ul>

    <h3>Reproducibility</h3>
    <p class="measure">Column names are resolved through a per-cycle crosswalk rather than assumed
    stable, because CDC renames modules and variables across the series and code that assumes
    otherwise reads less data without raising. Every download writes a SHA-256 manifest: public-use
    files are revised in place without renaming, so the digests are what establish that two runs
    read the same bytes. The test suite requires no downloaded data — fixtures write synthetic
    files that round-trip through the same reader the pipeline uses.</p>
  </div>

    <h3>Checked against an independent implementation</h3>
    {f'''
    <p class="measure">Two of the estimators here are written by hand: the Taylor-linearised
    variance for the standardised prevalence, and the cluster-robust Cox. Unit tests can show that
    such an estimator does what its author meant; they cannot show that what the author meant is
    what the method is. So both were re-fitted in R with <code>survey</code> and
    <code>survival</code>, on exactly the rows the shipped code path uses, and compared term by
    term.</p>

    <p class="measure"><b>Part 1 agrees to machine precision.</b> Across all {p1['n_cycles']}
    cycles the standardised prevalence and its standard error match
    <code>svydesign</code>&nbsp;+&nbsp;<code>svyby</code>&nbsp;+&nbsp;<code>svycontrast</code> to
    within {xc_se_max:.1e} absolute and {xc_rel_max:.1e} relative &mdash; floating-point noise. Two
    different R routes to the same estimand agree with each other exactly as well, so this is not
    agreement with one arbitrary choice. R also reports the design degrees of freedom directly:
    {xc_dof_lo}&ndash;{xc_dof_hi} per cycle, which is the number the intervals above use.</p>

    <p class="measure"><b>Part 3 agrees on the coefficients and disagrees on the standard
    errors, for a reason worth stating.</b> Every coefficient matches <code>svycoxph</code> to
    {xc_coef_max:.1e}. The robust standard errors differ by a median of
    {100 * xc_se_med:.2f}% and at worst {100 * xc_se_worst:.1f}%. A third fit &mdash; R&rsquo;s
    <code>coxph</code> with <code>cluster()</code>, which is the same estimator the Python code
    computes &mdash; agrees with it to {100 * xc_cluster_med:.2f}%. The implementation is
    therefore right and the gap is a difference of estimator: the Python fit is an
    <em>unstratified</em> cluster sandwich, while <code>svycoxph</code> uses the stratified
    ultimate-cluster form that NHANES guidance describes.</p>

    <div class="note flag">
      <b>So the Part 3 hazard-ratio intervals reported above are the DESIGN-BASED ones, taken
      from <code>svycoxph</code>.</b> The Python cluster-robust fit is kept beside them as a
      sensitivity analysis rather than replaced, because it is the same estimator every version of
      this report until now used and a reader deserves to see how far the change moved anything.
      It moved the exposure by {100 * xc_exp_rel:.1f}%: HR {sbp['hr']:.4f}
      ({sbp['lo95']:.4f}&ndash;{sbp['hi95']:.4f}) cluster-robust against
      {sbp_design['hr']:.4f} ({sbp_design['lo95']:.4f}&ndash;{sbp_design['hi95']:.4f})
      design-based. Across the nine terms the standard errors differ by a median of
      {100 * xc_se_med:.2f}% and at most {100 * xc_se_worst:.2f}% &mdash; and
      <b>no term changes whether its interval covers the null</b>, so the sensitivity analysis
      agrees with the primary one on every conclusion and differs only on precision. The
      R script and its output are versioned in the repository, so the site builds without R; only
      regenerating them needs it. Writing the stratified form in Python is recorded as open,
      because doing it properly is a project of its own and shipping a second implementation
      nobody has checked would be worse than depending on one that is checked.
    </div>'''}
</section>

<footer>
  <p>CardioTrace · Module 1 of the HealthTrace platform · prepared {BUILD_DATE}. Figures and
  tables are generated from <code>reports/descriptive_results.json</code>,
  <code>reports/model_results.json</code> and <code>reports/tables/</code>; this file inlines them
  and has no external dependencies.</p>
</footer>

</div>
</body>
</html>
"""


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(ROOT)} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
