"""The benchmark narrative reads committed results, including sample losses."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"1a_published_ascvd": "1a · Published PCE (hard ASCVD)",
          "1b_mortality_recalibration": "1b · PCE slopes, mortality baselines",
          "2_same_inputs_refit": "2 · Same inputs, refitted Cox",
          "3_cardiotrace_refit": "3 · CardioTrace, refitted"}


def build():
    path = ROOT / "reports/pce_results.json"
    if not path.exists():
        raise FileNotFoundError("reports/pce_results.json missing; run scripts/build_pce_results.py")
    results = json.loads(path.read_text(encoding="utf-8"))
    parts = []
    for name, label in [("primary", "Primary: non-Hispanic White and Black"),
                        ("other_ethnicities_white_equation_sensitivity", "Sensitivity: other ethnicities mapped to White equations")]:
        r = results[name]
        cascade = " &rarr; ".join(f"{row['step'].replace('_', ' ')}: {row['n']:,} ({row['cvd_deaths']} deaths)" for row in r["cascade"])
        rows = []
        for horizon, test in r["tests"].items():
            for arm, m in test["metrics"].items():
                delta = test["delta_c_vs_published_pce"].get(arm)
                delta_text = (f"{delta['delta']:+.4f} ({delta['lo']:+.4f}, {delta['hi']:+.4f})"
                              if delta else "reference")
                rows.append(f"<tr><td>{horizon}</td><td>{LABELS[arm]}</td><td>{m['n']:,}</td>"
                            f"<td>{m['events_at_horizon']}</td><td>{m['c']:.4f}</td>"
                            f"<td>{m['c_unweighted']:.4f}</td><td>{m['auc_horizon']:.4f}</td>"
                            f"<td>{delta_text}</td><td>{m['mean_score_pct']:.2f}%</td>"
                            f"<td>{m['observed_cvd_mortality_pct']:.2f}%</td></tr>")
        parts.append(f"<h3>{label}</h3><p class='measure'>{cascade}.</p>"
                     f"<p class='measure'>Training: {r['n_train']:,} participants, {r['train_cvd_deaths']} CVD deaths, "
                     f"{r['train_competing_deaths']} competing deaths, 1999–2004. Every arm uses the same rows.</p>"
                     "<div class='twrap'><table><thead><tr><th>Horizon</th><th>Arm</th><th>n</th><th>CVD events by horizon</th>"
                     "<th>Weighted C</th><th>Unweighted C</th><th>Evaluable-case AUC</th><th>ΔC vs PCE (95% interval)</th>"
                     "<th>Mean score</th><th>Observed mortality (AJ)</th></tr></thead><tbody>"
                     + "".join(rows) + "</tbody></table></div>")
    curve = pd.read_csv(ROOT / "reports/tables/decision_curve_primary.csv")
    rows = []
    for horizon in (10, 5):
        for threshold in (.01, .02, .05):
            d = curve[(curve.horizon_years == horizon) & (abs(curve.threshold-threshold) < 1e-8)]
            vals = d.set_index("arm").net_benefit
            rows.append(f"<tr><td>{horizon}y</td><td>{100*threshold:.1f}%</td>"
                        + "".join(
                            f"<td>{'&mdash;' if arm == 'treat_none' else f'{1000*vals[arm]:.2f}'}</td>"
                            for arm in ["1b_mortality_recalibration", "2_same_inputs_refit",
                                        "3_cardiotrace_refit", "treat_all", "treat_none"])
                        + "</tr>")
    return "".join(parts) + """
    <p class="measure">The published PCE column always contains ten-year hard-ASCVD scores,
    even when ranking five-year mortality. Its mean is not a mortality calibration estimate.
    The other arms estimate mortality. Baseline adaptation uses only training cycles and retains
    the published PCE slopes, with group-specific competing hazards. Arm 2 is a pooled linear
    same-input Cox model, not a reproduction of every PCE interaction. Arm 3 retains the
    existing CardioTrace preprocessing. Pooled ordering can change after group-specific
    adaptation; monotone invariance does not make different endpoints equivalent.</p>
    <p class="measure">Intervals use 200 paired PSU-bootstrap replicates within strata,
    conditional on the training fits. AUC excludes people whose horizon outcome is unknown;
    it is not censoring-weighted AUC. AJ mortality and the five-year decision curves account
    for earlier administrative censoring under independent censoring assumptions.</p>
    <h3>Exploratory decision curves for CVD mortality</h3>
    <p class="measure">Net benefit is expressed per 1,000 people at illustrative thresholds.
    All twenty thresholds from 0.5% to 10% are retained in the committed decision-curve tables.
    Competing deaths count as non-cases; early censoring is handled with weighted AJ within
    threshold-positive groups. The published ASCVD score is excluded because it has a different
    endpoint. These thresholds describe hypothetical tradeoffs, not treatment recommendations.
    Point estimates have no uncertainty bands and establish no clinical benefit.</p>
    <div class="twrap"><table><thead><tr><th>Horizon</th><th>Threshold</th>
    <th>PCE mortality adaptation</th><th>Same inputs</th><th>CardioTrace</th>
    <th>Treat all</th><th>Treat none</th></tr></thead><tbody>""" + "".join(rows) + """</tbody></table></div>
    <p class="measure">Reporting evidence and remaining disclosures are mapped in
    <a href="https://github.com/UTSGJohnsonSong/cardiotrace/blob/main/docs/tripod-checklist.md">the TRIPOD+AI checklist</a>.
    The <a href="https://github.com/UTSGJohnsonSong/cardiotrace/blob/main/docs/reproducibility.md">reproducibility guide</a>
    separates offline rendering, raw-data analysis, R cross-checks and the optional warehouse.</p>"""
