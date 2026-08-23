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
from src.descriptive import AGE_LABELS, PRE_COVID_CYCLES, STD_2000  # noqa: E402

ROOT = Path(__file__).parent.parent
FIG = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "reports" / "cardiotrace-report.html"

BUILD_DATE = "2026-08-21"
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

    rows1 = "".join(
        f"<tr><td>{r.cycle}</td><td>{r.n:,}</td><td>{r.n_cases:,}</td>"
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
    rows_pred = "".join(
        f"<tr><td>{k}</td><td>{v['n']:,}</td><td>{v['cvd_deaths']}</td>"
        f"<td class='em'>{v['harrell_c']:.3f}</td>"
        f"<td>{v['mean_predicted_pct']:.2f}%</td>"
        f"<td>{v['mean_observed_pct']:.2f}%</td></tr>"
        for k, v in pred.items())

    rows_cox = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
        for r in cox.itertuples(index=False))
    cox_head = "".join(f"<th>{c}</th>" for c in cox.columns)

    rows_strobe = "".join(
        "<tr>" + "".join(f"<td>{v}</td>" for v in r) + "</tr>"
        for r in strobe.itertuples(index=False))
    strobe_head = "".join(f"<th>{c}</th>" for c in strobe.columns)

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
        f"<tr><td>{r.cycle}</td><td>{r.age_eligible:,}</td>"
        f"<td>{r.no_exam_weight:,}</td><td>{r.analysed:,}</td>"
        f"<td class='em'>{r.lost_pct:.1f}%</td></tr>"
        for r in flow.itertuples())
    _post_lost = float(flow.loc[flow["cycle"] == "2021-2022", "lost_pct"].iloc[0])
    _other_lost = flow.loc[flow["cycle"] != "2021-2022", "lost_pct"]
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
        f"<tr><td>{r.cycle}</td><td>{r.n:,}</td><td>{r.n_psu}</td>"
        f"<td>{r.deff_std:.2f}</td><td>{r.kish_weighting:.2f}</td>"
        f"<td class='em'>{r.deff_clustering:.2f}</td></tr>"
        for r in overall.itertuples())

    rows_asc = "".join(
        f"<tr><td>{r.cycle}</td><td>{r.instrument}</td><td>{r.n_hypertensive:,}</td>"
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
        f"<td>{r.hr_per_sd:.3f}</td><td class='em'>{r.wald:.1f}</td>"
        f"<td>{'yes' if r.in_pool else (r.note or 'below threshold')}</td></tr>"
        for r in p4_rank.itertuples())

    p4_rows_arms = "".join(
        f"<tr><td>{ARM_LABEL_HTML[r.arm]}</td><td>{r.n_features}</td>"
        f"<td>{r.harrell_c:.4f}</td><td>{r.auc_horizon:.4f}</td>"
        f"<td class='em'>{'&mdash; reference' if r.is_reference else f'{r.delta_c:+.4f}'}</td>"
        f"<td>{'' if r.is_reference else f'{r.delta_lo:+.4f} to {r.delta_hi:+.4f}'}</td></tr>"
        for r in p4_arms.itertuples())

    p4_rows_imp = "".join(
        f"<tr><td>{r.rank}</td><td><code>{r.variable}</code></td>"
        f"<td class='em'>{r.delta_c:+.5f}</td><td>{r.e2_status}</td>"
        f"<td>{r.e2_why}</td></tr>"
        for r in p4_imp.head(8).itertuples())

    p4_rows_creat = "".join(
        f"<tr><td>{r.cycle}</td><td>{r.n:,}</td><td>{r.mean_as_loaded:.4f}</td>"
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

    p4_kept = p4_prev["selected"]
    p4_dropped = p4_prev["rejected"]
    if p4_kept and p4_dropped:
        p4_prevent_says = (
            f"It kept {', '.join(f'<code>{v}</code>' for v in p4_kept)} and "
            f"rejected {', '.join(f'<code>{v}</code>' for v in p4_dropped)}. "
            "A partial match, and the disagreement is the informative half.")
    elif p4_kept:
        p4_prevent_says = ("It selected every one of them, having never been "
                           "told they were the ones to look for.")
    else:
        p4_prevent_says = ("It selected none of them, which is a disagreement "
                           "with the current guideline worth explaining rather "
                           "than smoothing over.")

    sbp = model["aetiologic_sbp_per_10mmhg"]

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
    <span><b>Survey cycles</b> {p1['n_cycles']}, {overall.iloc[0]['cycle']} to {p1['last_cycle']}</span>
    <span><b>Descriptive sample</b> {p1['n_adults']:,} adults 20+</span>
    <span><b>Cohort</b> 20,736 adults 40–79 · 925 CVD deaths</span>
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
              <td>20,736 adults 40–79, CVD-free at baseline</td></tr>
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
      {stat("Adults 20+", f"{p1['n_adults']:,}", f"{p1['n_cycles']} cycles, {overall.iloc[0]['cycle']} to {p1['last_cycle']}")}
      {stat("Crude", f"{pct(p1['crude_first'], 1)} → {pct(p1['crude_last'], 1)}", f"rising, to {p1['last_cycle']}")}
      {stat("Standardised", f"{pct(p1['std_first'], 1)} → {pct(p1['std_last'], 1)}", f"falling, to {p1['last_cycle']}")}
      {stat("Weighted mean age", f"{p1['mean_age_first']:.1f} → {p1['mean_age_last']:.1f}", "years — the driver")}
    </div>

    <figure>
      <img src="{data_uri('part1_standardisation.png')}"
           alt="Crude and age-standardised prevalence of self-reported cardiovascular disease by
                NHANES cycle, 1999 to 2022. The two series track together until roughly 2015, then
                the crude series rises while the standardised series stays flat.">
      <figcaption><b>Two series, opposite conclusions.</b> Both lines run all
      {p1['n_cycles']} cycles, to {p1['last_cycle']}; the trend is fitted on the
      {n_pre_cycles} pre-pandemic cycles only, because §3 exists to ask what the last one did
      relative to it. Over that window the standardised series falls
      {abs(100 * p1['std_slope_per_decade']):.2f} points per decade (95% CI
      {100 * p1['std_slope_ci'][0]:.2f} to {100 * p1['std_slope_ci'][1]:.2f}) while the crude
      series rises {100 * p1['crude_slope_per_decade']:+.2f}. The interval excludes zero, so the
      decline is not noise. Read the final point with the caveat §3 develops: that cycle lost
      {_post_lost:.1f}% of age-eligible adults to a missing examination weight, against
      {_other_lost.min():.1f}&ndash;{_other_lost.max():.1f}% everywhere else.</figcaption>
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
      overall, peaking in {asc_peak['cycle']}.</b> The share climbs from
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
                2021-2022 point with its confidence interval.">
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
    <p class="measure">The whole counterfactual rests on a single observation, so
    it matters who that observation is made of. Every cycle loses some
    age-eligible respondents who were interviewed but never examined and
    therefore carry no examination weight. In 2021&ndash;2022 that loss is
    <b>{_post_lost:.1f}%</b>, against {_other_lost.min():.1f}&ndash;
    {_other_lost.max():.1f}% in every other cycle &mdash; a fourfold change in
    examination coverage, concentrated on exactly the point the analysis leans
    on.</p>

    <div class="twrap">
      <table>
        <caption>Part 1 and Part 2 &mdash; participant flow by cycle</caption>
        <thead><tr><th>Cycle</th><th>Age-eligible (20+)</th>
          <th>No examination weight</th><th>Analysed</th><th>Lost</th></tr></thead>
        <tbody>{rows_flow}</tbody>
      </table>
    </div>

    <div class="note flag">
      <b>This is a competing explanation, not a footnote.</b> A cycle that
      examined a different quarter of the people it recruited could differ from
      its predecessors for reasons that have nothing to do with the pandemic&rsquo;s
      effect on cardiovascular disease. The survey weights are designed to
      correct for non-response, and NCHS reweighted this cycle accordingly, but
      that correction is an adjustment rather than a guarantee. It belongs beside
      the gap, not below it.
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
      {stat("Participants", "20,736", "40–79, CVD-free at baseline")}
      {stat("CVD deaths", "925", "2,711 competing deaths")}
      {stat("Person-years", "235,553", "origin at the examination")}
      {stat("Systolic BP", f"HR {sbp['hr']:.3f}", f"per 10 mmHg · {sbp['lo95']:.3f}–{sbp['hi95']:.3f}")}
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
    the effect attenuates from {sbp['hr']:.3f} to
    {model['aetiologic_sbp_per_10mmhg_no_tobin']['hr']:.3f} per 10 mmHg, which is the direction
    and roughly the magnitude the reasoning predicts.</p>

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
        <caption>Discrimination and calibration, held-out cycles</caption>
        <thead><tr><th>Test set</th><th>n</th><th>CVD deaths</th><th>Harrell&rsquo;s C</th>
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
      Follow-up ends {DATA_CUTOFF}, entirely before the pandemic.
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

    <h3>Against the current guideline, which was never consulted</h3>
    <p class="measure">The 2023 PREVENT equations added three variables to the Pooled Cohort
    Equations: {", ".join(f"<code>{k}</code>" for k in p4_prev["additions"])}. All three were
    among the candidates here, and the screen was not told that. {p4_prevent_says}</p>

    <p class="measure">The disagreement has a reason worth stating rather than explaining away.
    This cohort is aged 40&ndash;79 and largely has normal filtration &mdash; eGFR has little
    variance where it would matter, while albuminuria varies across the whole range and marks
    damage before filtration falls. A screen run on a cohort with more advanced kidney disease
    would very likely have kept both.</p>

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
    interval excludes zero in both directions. The floor arm is what makes those numbers readable:
    a Cox model on age and sex alone reaches C&nbsp;=&nbsp;{p4_floor.harrell_c:.4f}, so gradient
    boosting on all eleven variables discriminates <em>worse than age and sex</em>.</p>

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
      <span class="chip open">Open decision</span>
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

    <p class="measure">Three decisions remain open and are recorded as open: how to handle race
    categories the equations do not cover, whether to restrict the comparison to the subsample
    with all nine inputs observed, and whether treated blood pressure enters through the
    equations' own treated branch rather than this project's reconstruction of the untreated
    level. Each changes the answer, so none is being made silently.</p>
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
      <li>Every population quantity is weighted with the examination weight. Variances are
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
