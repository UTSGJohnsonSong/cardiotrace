"""Figures for Part 1 and Part 2.

Three figures, each carrying one claim that the underlying table supports:

  part1_standardisation   crude prevalence rises and the standardised series
                          does not, because the population aged. Both series
                          share one axis because the divergence is the subject.
  part1_by_race           four groups as small multiples, not four lines on one
                          axis: four categorical hues cannot clear the all-pairs
                          separation floor on this surface, and four overlapping
                          confidence bands are unreadable regardless. Each panel
                          carries the national series in grey as a common
                          reference so panels compare to each other.
  part2_counterfactual    the pre-pandemic fit extrapolated across the gap
                          NHANES left in the series, against the single observed
                          post-pandemic point.

The Other Hispanic panel is shaded before NHANES broadened its Hispanic
oversample: the cycle sample size roughly quadruples across that boundary, so
the early segment measures a different sample rather than a different level of
disease, and is marked rather than quietly plotted as trend. The counts in the
annotation are read from the table, because when they were typed here they went
stale the first time the age base moved.

Every heading is wrapped to the figure width before it is drawn. These figures are
saved with bbox_inches="tight", so an unwrapped heading -- not the axes -- sets the
width of the saved PNG. part1_ascertainment shipped at 3475x684 for a 1204 px axes
because its subtitle was one 24.6-inch line, and inside a phone-width plate that
image collapsed to 58 px tall. The wrap width therefore has to track figsize, which
is why `_heading` reads it off the figure instead of taking a constant.

Palette, spines and grid come from src.survival, so these sit in the same visual
system as the Part 3 figures. Both hues are the first two categorical slots and
clear the all-pairs separation checks in light and dark.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.survival import (  # noqa: E402
    AXIS, GRIDLINE, INK_MUTED, INK_PRIMARY, INK_SECONDARY, SURFACE,
)
from src.descriptive import PRE_COVID_CYCLES, cycle_midpoint  # noqa: E402
from scripts.build_descriptive_results import wls_trend, predict_at  # noqa: E402

ROOT = Path(__file__).parent.parent
REPORTS = ROOT / "reports"
FIG = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"

SERIES = "#2a78d6"      # categorical slot 1 — the estimate that counts
FLAG = "#eb6834"        # categorical slot 2 — the naive comparison / the flag
REFERENCE = "#b8b7ae"   # grey national reference inside the small multiples

plt.rcParams.update({
    "figure.dpi": 140, "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED, "ytick.color": INK_MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": GRIDLINE, "grid.linewidth": 0.8,
})

# NHANES broadened its Hispanic oversample from this cycle on.
OVERSAMPLE_YEAR = 2007.5

RACE_ORDER = ["Non-Hispanic White", "Non-Hispanic Black",
              "Mexican American", "Other Hispanic"]
XTICKS = [2000, 2004, 2008, 2012, 2016, 2022]
XLABELS = ["1999", "2003", "2007", "2011", "2015", "2021"]


def _style(ax, ylabel):
    ax.set_ylabel(ylabel, color=INK_SECONDARY)
    ax.grid(axis="y", alpha=0.7)
    ax.set_axisbelow(True)


# Heading typography. 12.5 and 8.5 were inline literals in `_heading`; they are
# named here because the wrap and the vertical stacking both have to agree with
# them, and a silent disagreement shows up as a title printed over a subtitle.
_TITLE_PT = 12.5
_SUB_PT = 8.5
_LINESPACING = 1.25
_TITLE_GAP_PT = 3.5


def _wrap_to_width(fig, text: str, fontsize: float, weight: str,
                   width_in: float) -> str:
    """Word-wrap `text` so no line exceeds `width_in`, measured for real.

    The headings are assembled from the artefacts, so their length is not known
    when the figure is laid out, and `savefig(bbox_inches="tight")` grows the
    saved PNG to whatever the longest line needs. That is how part1_ascertainment
    shipped at 3475x684 for a 1204 px axes: the subtitle was one 24.6-inch line.

    Measured against the renderer rather than counted in characters, because the
    character width depends on which font the machine actually resolves from the
    rcParam stack, and a character count that is right here is wrong on CI.

    Explicit newlines are honoured and each segment wrapped independently. A
    single word longer than `width_in` still overflows; no heading contains one.
    """
    limit = width_in * fig.dpi
    probe = fig.text(0.0, 0.0, "", fontsize=fontsize, fontweight=weight)
    renderer = fig.canvas.get_renderer()

    def width_of(s: str) -> float:
        probe.set_text(s)
        return probe.get_window_extent(renderer).width

    out: list[str] = []
    for segment in text.split("\n"):
        line = ""
        for word in segment.split():
            trial = f"{line} {word}" if line else word
            if line and width_of(trial) > limit:
                out.append(line)
                line = word
            else:
                line = trial
        out.append(line)
    probe.remove()
    return "\n".join(out)


def _heading(fig, title, subtitle):
    """Title and standfirst as figure text, so they cannot collide with axes.

    Both are wrapped to the figure width. The block is anchored at the subtitle's
    baseline and grows upward, so a two- or three-line subtitle pushes the title
    up rather than printing under it.
    """
    width_in, height_in = fig.get_size_inches()
    title = _wrap_to_width(fig, title, _TITLE_PT, "bold", width_in)
    subtitle = _wrap_to_width(fig, subtitle, _SUB_PT, "normal", width_in)

    sub_y = 1.004
    fig.text(0.0, sub_y, subtitle, color=INK_MUTED, fontsize=_SUB_PT,
             linespacing=_LINESPACING, ha="left", va="bottom")

    block_pt = (subtitle.count("\n") + 1) * _SUB_PT * _LINESPACING + _TITLE_GAP_PT
    fig.text(0.0, sub_y + block_pt / (72.0 * height_in), title,
             color=INK_PRIMARY, fontweight="bold", fontsize=_TITLE_PT,
             linespacing=_LINESPACING, ha="left", va="bottom")


def figure_standardisation(overall: pd.DataFrame, p1: dict) -> None:
    x = overall["year"].to_numpy()
    fig, ax = plt.subplots(figsize=(8.6, 4.6))

    ax.fill_between(x, 100 * overall["lo_std"], 100 * overall["hi_std"],
                    color=SERIES, alpha=0.13, linewidth=0)
    ax.plot(x, 100 * overall["p_crude"], color=FLAG, linewidth=2,
            marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)
    ax.plot(x, 100 * overall["p_std"], color=SERIES, linewidth=2,
            marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)

    # Two series, direct-labelled: the point of the figure is which is which.
    ax.annotate("Crude", xy=(x[-1], 100 * overall["p_crude"].iloc[-1]),
                xytext=(8, 5), textcoords="offset points", color=FLAG,
                fontsize=9.5, fontweight="bold", va="center")
    ax.annotate("Age-standardised", xy=(x[-1], 100 * overall["p_std"].iloc[-1]),
                xytext=(8, -6), textcoords="offset points", color=SERIES,
                fontsize=9.5, fontweight="bold", va="center")

    # Stated on the plotted endpoints, because those are what a reader can
    # measure off the line. The earlier version quoted the pre-pandemic movement
    # in the title and the full-series mean ages in the subtitle, so the two
    # halves of one caption covered different periods.
    crude_d = 100 * (overall["p_crude"].iloc[-1] - overall["p_crude"].iloc[0])
    std_d = 100 * (overall["p_std"].iloc[-1] - overall["p_std"].iloc[0])
    _heading(fig,
             f"Crude prevalence rose {crude_d:.1f} points. "
             f"Age-standardised fell {abs(std_d):.1f}.",
             f"Self-reported cardiovascular disease, US adults {p1['age_floor']}+, "
             f"NHANES {int(overall['year'].iloc[0])}–"
             f"{int(overall['year'].iloc[-1]) + 1}. Weighted mean age rose "
             f"{p1['mean_age_first']:.1f} → {p1['mean_age_last']:.1f} over the "
             "same period. Band is the 95% design-based interval on the "
             "standardised series.")
    _style(ax, "Prevalence (%)")
    ax.set_xticks(XTICKS)
    ax.set_xticklabels(XLABELS, fontsize=8.5)
    ax.set_xlim(x[0] - 0.5, x[-1] + 2.6)
    ax.set_ylim(6, 13)
    fig.savefig(FIG / "part1_standardisation.png", bbox_inches="tight",
                facecolor=SURFACE)
    plt.close(fig)


def figure_by_race(race: pd.DataFrame, overall: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 6.0), sharex=True, sharey=True)
    x_all = overall["year"].to_numpy()

    for ax, group in zip(axes.ravel(), RACE_ORDER):
        g = race[race["race_eth"] == group].sort_values("year")
        ax.plot(x_all, 100 * overall["p_std"], color=REFERENCE, linewidth=1.6,
                zorder=1)
        ax.fill_between(g["year"], 100 * g["lo_std"], 100 * g["hi_std"],
                        color=SERIES, alpha=0.13, linewidth=0, zorder=2)
        ax.plot(g["year"], 100 * g["p_std"], color=SERIES, linewidth=2,
                marker="o", markersize=4, markeredgecolor=SURFACE,
                markeredgewidth=1.0, zorder=3)
        ax.set_title(group, color=INK_PRIMARY, loc="left", fontsize=10,
                     fontweight="bold", pad=6)
        _style(ax, "")
        ax.set_xticks(XTICKS)
        ax.set_xticklabels(XLABELS, fontsize=8)

        if group == "Other Hispanic":
            early = g[g["year"] < OVERSAMPLE_YEAR]
            ax.axvspan(1998.6, OVERSAMPLE_YEAR - 0.9, color=GRIDLINE, alpha=0.55,
                       linewidth=0, zorder=0)
            ax.annotate(f"n = {early['n'].min()}–{early['n'].max()} per cycle"
                        + "\nbefore the sample widened",
                        xy=(1999.2, 1.4), fontsize=7.5, color=INK_MUTED,
                        ha="left", va="bottom")

    axes[0][0].annotate("grey line = all adults", xy=(2012.5, 1.6),
                        fontsize=7.5, color=INK_MUTED, ha="left")
    for ax in axes[:, 0]:
        ax.set_ylabel("Prevalence (%)", color=INK_SECONDARY)
    axes[0][0].set_ylim(0, 16)

    black = race[race["race_eth"] == "Non-Hispanic Black"].set_index("cycle")["p_std"]
    nat = overall.set_index("cycle")["p_std"]
    above = int((black > nat.reindex(black.index)).sum())
    _heading(fig,
             f"Non-Hispanic Black adults are above the national rate in "
             f"{above} of {len(black)} cycles",
             "Age-standardised prevalence of self-reported cardiovascular disease. "
             "Shaded bands are 95% design-based intervals; the grey line repeats the "
             "national series in every panel.")
    fig.tight_layout()
    fig.savefig(FIG / "part1_by_race.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def figure_counterfactual(overall: pd.DataFrame, p2: dict) -> None:
    pre = overall[overall["cycle"].isin(PRE_COVID_CYCLES)]
    post = overall[overall["cycle"] == "2021-2022"].iloc[0]
    fit = wls_trend(pre["year"].to_numpy(), pre["p_std"].to_numpy(),
                    pre["se_std"].to_numpy())

    x0 = cycle_midpoint("2021-2022")
    last_obs = pre["year"].max()
    grid = np.linspace(pre["year"].min(), x0 + 0.3, 240)
    fitted = np.array([predict_at(fit, xi) for xi in grid])
    yhat, se_hat = fitted[:, 0], fitted[:, 1]

    fig, ax = plt.subplots(figsize=(8.6, 4.6))

    ax.axvspan(last_obs, x0, color=GRIDLINE, alpha=0.5, linewidth=0, zorder=0)
    ax.fill_between(grid, 100 * (yhat - 1.96 * se_hat), 100 * (yhat + 1.96 * se_hat),
                    color=SERIES, alpha=0.12, linewidth=0, zorder=1)
    solid = grid <= last_obs
    ax.plot(grid[solid], 100 * yhat[solid], color=SERIES, linewidth=2, zorder=3)
    ax.plot(grid[~solid], 100 * yhat[~solid], color=SERIES, linewidth=2,
            linestyle=(0, (5, 3)), zorder=3)
    ax.plot(pre["year"], 100 * pre["p_std"], linestyle="none", marker="o",
            markersize=6, color=SERIES, markeredgecolor=SURFACE,
            markeredgewidth=1.2, zorder=4)

    obs, se_obs = 100 * float(post["p_std"]), 100 * float(post["se_std"])
    cf = 100 * predict_at(fit, x0)[0]
    ax.errorbar([x0], [obs], yerr=[1.96 * se_obs], fmt="o", markersize=8,
                color=FLAG, ecolor=FLAG, elinewidth=2, capsize=4,
                markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=5)

    # The gap, drawn once and labelled clear of both series.
    ax.annotate("", xy=(x0 + 0.55, obs), xytext=(x0 + 0.55, cf),
                arrowprops=dict(arrowstyle="<->", color=INK_SECONDARY, linewidth=1.3))
    # The arrow is drawn from computed endpoints, so a typed label could -- and
    # did -- disagree with the arrow it labels inside the shipped image.
    _g, _lo, _hi = 100 * p2["gap"], 100 * p2["gap_ci"][0], 100 * p2["gap_ci"][1]
    _lbl = (f"{_g:+.2f} pp" + "\n" +
            f"95% CI {_lo:+.2f} to {_hi:+.2f}").replace("-", "\u2212")
    ax.annotate(_lbl, xy=(x0 + 0.75, (obs + cf) / 2),
                ha="left", va="center", color=INK_SECONDARY, fontsize=8.5)
    ax.annotate("observed 2021–22", xy=(x0, obs + 1.96 * se_obs),
                xytext=(-6, 8), textcoords="offset points", color=FLAG,
                fontsize=9.5, fontweight="bold", ha="right")
    ax.annotate("counterfactual", xy=(x0, cf), xytext=(-8, -16),
                textcoords="offset points", color=SERIES, fontsize=9.5,
                fontweight="bold", ha="right")
    ax.annotate("no cycle fielded", xy=((last_obs + x0) / 2, 6.35),
                ha="center", va="bottom", color=INK_MUTED, fontsize=8)

    _heading(fig,
             "One post-pandemic point cannot carry an interrupted time series",
             f"Age-standardised prevalence, pre-pandemic trend extrapolated "
             f"{p2[chr(39)+chr(39)] if False else p2['extrapolation_years']:.0f} years "
             "across a cycle NHANES did not field. Band is the 95% interval on the "
             "fitted trend; the level change is not identified from a single point.")
    _style(ax, "Prevalence (%)")
    ax.set_xticks(XTICKS)
    ax.set_xticklabels(XLABELS, fontsize=8.5)
    ax.set_xlim(pre["year"].min() - 0.5, x0 + 3.4)
    ax.set_ylim(6, 12.5)
    fig.savefig(FIG / "part2_counterfactual.png", bbox_inches="tight",
                facecolor=SURFACE)
    plt.close(fig)


def figure_ascertainment(asc: pd.DataFrame) -> None:
    """How much of the measurably hypertensive population knows it."""
    aus = asc[asc["instrument"] == "auscultatory"]
    osc = asc[asc["instrument"] == "oscillometric"]
    fig, ax = plt.subplots(figsize=(8.6, 4.6))

    x = aus["year"].to_numpy()
    ax.fill_between(x, 100 * aus["lo_std"], 100 * aus["hi_std"],
                    color=SERIES, alpha=0.13, linewidth=0)
    ax.plot(x, 100 * aus["ascertained_std"], color=SERIES, linewidth=2,
            marker="o", markersize=5, markeredgecolor=SURFACE, markeredgewidth=1.2)

    peak = aus.loc[aus["ascertained_std"].idxmax()]
    ax.annotate(f"peak {100 * peak['ascertained_std']:.1f}%\n{peak['cycle']}",
                xy=(peak["year"], 100 * peak["ascertained_std"]),
                xytext=(-4, 14), textcoords="offset points", ha="center",
                color=INK_SECONDARY, fontsize=9, fontweight="bold")

    # The ACA coverage expansion, marked so the reader can see the phase.
    ax.axvline(2014.0, color=FLAG, linewidth=1.4, linestyle=(0, (4, 3)), zorder=1)
    ax.annotate("main ACA coverage\nexpansion phases in", xy=(2014.15, 40.5),
                color=FLAG, fontsize=8.5, ha="left", va="bottom")

    for _, r in osc.iterrows():
        ax.errorbar([r["year"]], [100 * r["ascertained_std"]],
                    yerr=[1.96 * 100 * r["se_std"]], fmt="s", markersize=7,
                    color=INK_MUTED, ecolor=INK_MUTED, elinewidth=1.6, capsize=4,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=5)
        ax.annotate("different\ninstrument", xy=(r["year"], 100 * r["ascertained_std"]),
                    xytext=(9, -4), textcoords="offset points",
                    color=INK_MUTED, fontsize=8)

    # The narrower denominator, drawn faint, because the gap between the two IS
    # the finding: it is flat and the correct one rises.
    ax.plot(x, 100 * aus["measured_only_std"], color=INK_MUTED, linewidth=1.5,
            linestyle=(0, (4, 3)), zorder=2)
    ax.annotate("measured high only", xy=(x[-1], 100 * aus["measured_only_std"].iloc[-1]),
                xytext=(8, -2), textcoords="offset points",
                color=INK_MUTED, fontsize=8.5)

    _rise = 100 * (aus["ascertained_std"].iloc[-1] - aus["ascertained_std"].iloc[0])
    _heading(fig,
             f"Ascertainment rose {_rise:.0f} points overall, peaking in "
             f"{peak['cycle']} and falling back after",
             "Share of adults 20+ who are hypertensive — measured ≥140/90 OR on treatment "
             "— and report having been told. Age-standardised; band is the 95% design-based "
             "interval. The dashed line conditions on measured pressure alone, which drops "
             "everyone treatment has controlled and so understates the trend. Grey square is "
             "2021–2022: different instrument and a different medication item, not on the "
             "series.")
    _style(ax, "Ascertained (%)")
    ax.set_xticks(XTICKS)
    ax.set_xticklabels(XLABELS, fontsize=8.5)
    ax.set_xlim(1998.9, 2023.4)
    ax.set_ylim(38, 92)
    fig.savefig(FIG / "part1_ascertainment.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def figure_changepoint(overall: pd.DataFrame, cp: dict) -> None:
    """Where a break would sit if there were one, and what size it would take.

    The two panels stack rather than sit side by side. Side by side they shared
    one 293 px plate on a phone, so each panel got roughly 145 px of width and
    the whole figure rendered 89 px tall; stacked, each panel gets the full
    width and the figure renders 241 px tall. Stacking rather than emitting a
    narrow variant for CSS to pick, because the single-file report is emailed
    and cannot rely on `<picture>`, and because build_site.externalise_images
    only rewrites `src=` -- a `<source srcset>` would stay inlined as a data URI
    in every docs page.
    """
    # Read the persisted test rather than re-running it. Re-running here with a
    # different replicate count put a different critical value on the figure from
    # the one the report quoted.
    line_wrss = cp["line_wrss"]
    inside = set(cp["profile_set"])
    power = cp["power"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.6, 6.6))

    taus = [t for t, _ in cp["profile"]]
    gains = [line_wrss - w for _, w in cp["profile"]]
    colours = [SERIES if t in inside else INK_MUTED for t in taus]
    ax1.bar(taus, gains, width=1.1, color=colours, zorder=2)
    ax1.axhline(cp["crit95"], color=FLAG, linewidth=1.6,
                linestyle=(0, (4, 3)), zorder=3)
    ax1.annotate(f"95% bootstrap threshold {cp['crit95']:.1f}", xy=(2003.2, cp["crit95"]),
                 xytext=(0, 5), textcoords="offset points",
                 color=FLAG, fontsize=8.5, fontweight="bold")
    ax1.annotate("naive χ² threshold 3.84", xy=(2003.2, 3.84), xytext=(0, 4),
                 textcoords="offset points", color=INK_MUTED, fontsize=8)
    ax1.axhline(3.84, color=INK_MUTED, linewidth=1.0, linestyle=":", zorder=1)
    ax1.set_title("No candidate break clears the threshold", color=INK_PRIMARY,
                  loc="left", fontsize=10.5, fontweight="bold", pad=8)
    ax1.set_xlabel("Candidate breakpoint (year)", color=INK_SECONDARY)
    _style(ax1, "Improvement in weighted RSS")
    ax1.set_ylim(0, max(7.0, cp["crit95"] * 1.15))

    pc = [(r["slope_change_per_decade_pp"], r["power"]) for r in power]
    ax2.plot([a for a, _ in pc], [100 * b for _, b in pc], color=SERIES,
             linewidth=2, marker="o", markersize=5,
             markeredgecolor=SURFACE, markeredgewidth=1.2)
    ax2.axhline(80, color=FLAG, linewidth=1.4, linestyle=(0, (4, 3)))
    ax2.annotate("80% power", xy=(0.25, 80), xytext=(0, 5),
                 textcoords="offset points", color=FLAG, fontsize=8.5,
                 fontweight="bold")
    ax2.set_title("…and the design could not see one this small", color=INK_PRIMARY,
                  loc="left", fontsize=10.5, fontweight="bold", pad=8)
    ax2.set_xlabel("True slope change at the break (pp per decade)", color=INK_SECONDARY)
    _style(ax2, "Power (%)")
    ax2.set_ylim(0, 100)

    _heading(fig,
             "No evidence of a breakpoint — and too little power to rule a moderate one out",
             f"Top: every admissible knot, against a bootstrap threshold that prices in having "
             f"searched for it (best knot {cp['tau']:.0f}, p = {cp['p']:.2f}). Blue bars "
             f"are inside the 95% profile set, which spans "
             f"{'the whole grid' if cp['profile_set_spans_grid'] else 'part of the grid'}. "
             f"Bottom: simulated power to detect a true break at "
             f"{cp['power_tau']:.0f}.")
    fig.tight_layout()
    fig.savefig(FIG / "part2_changepoint.png", bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    overall = pd.read_csv(TABLES / "part1_prevalence_by_cycle.csv")
    race = pd.read_csv(TABLES / "part1_prevalence_by_race.csv")
    asc = pd.read_csv(TABLES / "part1_ascertainment.csv")
    results = json.loads((REPORTS / "descriptive_results.json").read_text())
    cp = json.loads((TABLES / "part2_changepoint.json").read_text())

    figure_standardisation(overall, results["part1"])
    figure_by_race(race, overall)
    figure_counterfactual(overall, results["part2"])
    figure_ascertainment(asc)
    figure_changepoint(overall, cp)
    print("wrote 5 figures: standardisation, by_race, counterfactual, "
          "ascertainment, changepoint")


if __name__ == "__main__":
    main()
