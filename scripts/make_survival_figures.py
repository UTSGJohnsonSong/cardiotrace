"""
Descriptive survival figures for the Part 3 primary-prevention cohort.

    fig 1  cumulative incidence of CVD death by baseline systolic BP category
    fig 2  naive 1 - KM vs competing-risk CIF, whole cohort

Labels are English: the repository README is English, and DejaVu Sans (the
matplotlib default that ships everywhere) has no CJK glyphs, so Chinese labels
render as boxes on any machine without a CJK font installed. Keeping the figures
font-portable matters more than matching the working language of the notes.

Colours come from the validated dataviz reference palette; see src/survival.py
for which slots and why. Point estimates are survey-weighted. Design-based
confidence bands are NOT produced here and the subtitles say so.

    python scripts/make_survival_figures.py
"""

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.survival import (  # noqa: E402
    ORDINAL_BLUE, CATEGORICAL, INK_PRIMARY, INK_SECONDARY, INK_MUTED,
    GRIDLINE, AXIS, SURFACE, SBP_BINS, SBP_LABELS,
    aalen_johansen_cif, kaplan_meier, make_event_code, at_risk_counts,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
COHORT = ROOT / "data" / "processed" / "cohort_part3.csv.gz"
FIG = ROOT / "reports" / "figures"
TAB = ROOT / "reports" / "tables"
# Curves are drawn to 15 years. Only the 1999-2006 cycles are observed that long
# (max follow-up runs 20.8y for 1999-2000 down to 7.1y for 2013-2014), so the
# right-hand end of every curve rests on the older half of the cohort. The
# estimators handle the administrative censoring correctly — this is a statement
# about which cycles carry the tail, not an error.
HORIZON = 15.0
TICKS = [0, 3, 6, 9, 12, 15]
MIN_STRATUM_N = 100     # below this a curve is too noisy to plot

plt.rcParams.update({
    "figure.dpi": 140, "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRIDLINE, "grid.linewidth": 0.8,
})


def _style(ax, title, subtitle):
    ax.set_title(title, fontweight="bold", color=INK_PRIMARY, loc="left", pad=18)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_MUTED,
            fontsize=8.5, va="bottom")
    ax.set_xlabel("Years since baseline examination", color=INK_SECONDARY)
    ax.set_ylabel("Cumulative incidence (%)", color=INK_SECONDARY)
    ax.set_xlim(0, HORIZON)
    ax.set_xticks(TICKS)
    ax.grid(axis="y", alpha=0.7)
    ax.set_axisbelow(True)


def figure_by_sbp(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df.systolic_bp.notna()].copy()
    d["sbp_cat"] = pd.cut(d.systolic_bp, bins=SBP_BINS, labels=SBP_LABELS, right=False)

    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    rows = []
    for colour, label in zip(ORDINAL_BLUE, SBP_LABELS):
        g = d[d.sbp_cat == label]
        if len(g) < MIN_STRATUM_N:
            log.warning(f"  stratum {label} has n={len(g)} < {MIN_STRATUM_N}; not plotted")
            continue
        cif = aalen_johansen_cif(g.followup_years, make_event_code(g), g.wtmec2yr)
        cif = cif[cif.t <= HORIZON]
        ax.step(cif.t, 100 * cif.cif, where="post", lw=2.0, color=colour,
                label=f"{label} mmHg")
        end = 100 * cif.cif.iloc[-1]
        ax.annotate(f"{end:.1f}%", (HORIZON, end), xytext=(6, 0), textcoords="offset points",
                    color=colour, fontsize=9, va="center", fontweight="bold")
        rows.append({"stratum_mmhg": label, "n": len(g),
                     "cvd_deaths": int(g.cvd_death.sum()),
                     "cif_15y_pct": round(end, 2)})

    _style(ax, "Systolic blood pressure and 15-year cumulative incidence of CVD death",
           "NHANES 1999–2014 · adults 40–79 · free of CVD at baseline · survey-weighted · "
           "competing deaths accounted for (Aalen-Johansen)")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left",
              title="Baseline systolic BP", title_fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.savefig(FIG / "cif_by_sbp.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)

    out = pd.DataFrame(rows)
    out.to_csv(TAB / "cif_by_sbp.csv", index=False)
    at_risk_counts(d, TICKS, "sbp_cat").to_csv(TAB / "at_risk_by_sbp.csv")
    return out


def figure_competing_risk(df: pd.DataFrame) -> dict:
    e = make_event_code(df)
    naive = kaplan_meier(df.followup_years, e, df.wtmec2yr)
    cif = aalen_johansen_cif(df.followup_years, e, df.wtmec2yr)
    naive, cif = naive[naive.t <= HORIZON], cif[cif.t <= HORIZON]
    n_end, c_end = 100 * naive.cum_inc.iloc[-1], 100 * cif.cif.iloc[-1]

    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.step(naive.t, 100 * naive.cum_inc, where="post", lw=2.0, color=CATEGORICAL[1],
            label="1 − Kaplan-Meier  (competing deaths treated as censoring)")
    ax.step(cif.t, 100 * cif.cif, where="post", lw=2.0, color=CATEGORICAL[0],
            label="Aalen-Johansen CIF  (competing risk accounted for)")
    for val, colour in [(n_end, CATEGORICAL[1]), (c_end, CATEGORICAL[0])]:
        ax.annotate(f"{val:.2f}%", (HORIZON, val), xytext=(6, 0), textcoords="offset points",
                    color=colour, fontsize=9, va="center", fontweight="bold")
    # Lower-right quadrant is the only reliably empty region: both curves are
    # monotone increasing from the origin, so they occupy the diagonal and the
    # legend takes the upper left. Placing the gap callout mid-plot collided with
    # the legend text.
    ax.annotate(f"gap at 15y:  +{n_end - c_end:.2f} pp  "
                f"({100 * (n_end / c_end - 1):.0f}% relative)",
                xy=(HORIZON * 0.72, c_end * 0.28), color=INK_SECONDARY, fontsize=9,
                ha="center")

    ratio = df.competing_death.sum() / df.cvd_death.sum()
    _style(ax, "Treating competing deaths as censoring overstates CVD risk",
           f"Same cohort · {int(df.competing_death.sum()):,} competing deaths vs "
           f"{int(df.cvd_death.sum()):,} CVD deaths ({ratio:.1f} : 1) · survey-weighted point "
           "estimates, no design-based CI")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", labelcolor=INK_SECONDARY)
    fig.savefig(FIG / "competing_risk_comparison.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return {"naive_15y_pct": round(n_end, 2), "cif_15y_pct": round(c_end, 2),
            "absolute_pp": round(n_end - c_end, 2),
            "relative_pct": round(100 * (n_end / c_end - 1), 1)}


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(COHORT)
    log.info(f"cohort n={len(df):,} · CVD deaths {int(df.cvd_death.sum()):,} · "
             f"competing deaths {int(df.competing_death.sum()):,}")

    by_sbp = figure_by_sbp(df)
    log.info("\n=== CIF by systolic BP ===")
    log.info(by_sbp.to_string(index=False))

    cr = figure_competing_risk(df)
    log.info("\n=== competing risk ===")
    for k, v in cr.items():
        log.info(f"  {k:16s} {v}")
    log.info(f"\nfigures -> {FIG}")


if __name__ == "__main__":
    main()
