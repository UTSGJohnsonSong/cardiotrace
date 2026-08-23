"""Two figures for Part 4.

  part4_arms            what varying the variable set buys, against what varying
                        the model form costs, with the floor arm as the scale.
  part4_two_orderings   the same variables ranked by how much the prediction
                        needs them and coloured by what the causal model may do
                        with them. The disagreement between the two is the point
                        of the section, so it has to be visible in one image.

Every number in a title, label or annotation is read from the artefacts, and the
palette, spines and heading machinery come from the descriptive figures, so
these sit in the same visual system as the other eight.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.survival import AXIS, INK_MUTED, INK_SECONDARY, SURFACE  # noqa: E402
from scripts.make_descriptive_figures import (  # noqa: E402
    FLAG, REFERENCE, SERIES, _heading, _style,
)

ROOT = Path(__file__).parent.parent
FIG = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"

ARM_LABEL = {
    "cox_p": "Cox, the eleven\n(the published model)",
    "cox_wide": "Cox, the eleven\n+ what the screen chose",
    "gbm_p": "Gradient boosting,\nthe eleven",
    "gbm_wide": "Gradient boosting,\nthe eleven + the screen",
    "floor_age_sex": "Cox, age and sex only\n(the floor)",
}

# Blue where the difference is positive, orange where it is negative: the two
# categorical slots already carry "the estimate that counts" and "the flag" on
# every other figure in the report.
STATUS_COLOUR = {"admissible": SERIES, "forbidden": FLAG,
                 "undetermined": REFERENCE, "exposure": INK_SECONDARY}


def figure_arms(arms: pd.DataFrame, res: dict) -> None:
    d = arms[~arms["is_reference"]].sort_values("delta_c")
    fig, ax = plt.subplots(figsize=(8.6, 4.0))
    y = range(len(d))

    for i, r in zip(y, d.itertuples()):
        colour = SERIES if r.delta_c > 0 else FLAG
        ax.plot([r.delta_lo, r.delta_hi], [i, i], color=colour, linewidth=2.4,
                solid_capstyle="round", zorder=2)
        ax.plot([r.delta_c], [i], "o", color=colour, markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=1.3, zorder=3)

    ax.axvline(0.0, color=AXIS, linewidth=1.1, linestyle="--", zorder=1)
    ax.set_yticks(list(y))
    ax.set_yticklabels([ARM_LABEL[a] for a in d["arm"]], fontsize=9)
    ax.set_xlabel("Difference in Harrell C against the published model",
                  color=INK_SECONDARY)
    ax.grid(axis="x", alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

    ref = arms[arms["is_reference"]].iloc[0]
    gain = arms.loc[arms["arm"] == "cox_wide"].iloc[0]
    form = arms.loc[arms["arm"] == "gbm_p"].iloc[0]
    a = res["arms"]
    _heading(
        fig,
        "The variable set was the binding constraint, not the model form",
        f"Paired differences in Harrell C on the same {a['n_test']:,} held-out "
        f"participants and {a['events_test']} cardiovascular deaths, with 95% "
        f"intervals from {a['n_boot']} bootstrap replicates resampling whole "
        f"variance units. Reference: the published cause-specific Cox pair, "
        f"C = {ref.harrell_c:.3f}. One screened variable adds "
        f"{gain.delta_c:+.4f}; changing the form to gradient boosting on the "
        f"same eleven costs {form.delta_c:+.4f}.")
    fig.tight_layout()
    fig.savefig(FIG / "part4_arms.png", dpi=140, bbox_inches="tight",
                facecolor=SURFACE)
    plt.close(fig)


def figure_two_orderings(imp: pd.DataFrame, res: dict) -> None:
    d = imp.sort_values("delta_c", ascending=True).tail(12)
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    colours = [STATUS_COLOUR[s] for s in d["e2_status"]]
    ax.barh(range(len(d)), d["delta_c"], color=colours, height=0.72)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d["variable"], fontsize=9)
    ax.set_xlabel("Fall in Harrell C when the variable is shuffled",
                  color=INK_SECONDARY)
    ax.axvline(0.0, color=AXIS, linewidth=1.0)
    ax.grid(axis="x", alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)

    handles = [plt.Rectangle((0, 0), 1, 1, color=STATUS_COLOUR[s])
               for s in ("admissible", "undetermined", "forbidden", "exposure")]
    ax.legend(handles,
              ["the causal model may adjust for it",
               "the locked DAG does not say",
               "the causal model may not",
               "the exposure itself"],
              loc="lower right", frameon=False, fontsize=8.5,
              labelcolor=INK_MUTED)

    top5 = res["importance"]["top5"]
    bad = res["importance"]["top5_not_admissible"]
    _heading(
        fig,
        "The two orderings disagree, which is the whole argument",
        f"Permutation importance in the prediction model, coloured by what the "
        f"aetiologic model is allowed to do with each variable. Of the five the "
        f"prediction depends on most ({', '.join(top5)}), "
        f"{len(bad)} are variables the causal model may not simply adjust for "
        f"({', '.join(bad)}). A variable that earns its place in one model is "
        f"not thereby admissible in the other.")
    fig.tight_layout()
    fig.savefig(FIG / "part4_two_orderings.png", dpi=140, bbox_inches="tight",
                facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    res = json.loads((ROOT / "reports" / "part4_learning_results.json")
                     .read_text(encoding="utf-8"))
    arms = pd.read_csv(TABLES / "part4_arms.csv")
    imp = pd.read_csv(TABLES / "part4_importance.csv")
    figure_arms(arms, res)
    figure_two_orderings(imp, res)
    print("wrote 2 figures: part4_arms, part4_two_orderings")


if __name__ == "__main__":
    main()
