"""Flatten the published estimates into one long table Tableau can pivot.

The report chooses its views: ten figures, each answering one question. That is
the right shape for an argument and the wrong shape for a reader who wants to ask
their own. The estimates already cover 6 outcomes x 11 cycles x 6 age bands x 4
race groups, which is far more cells than a static page can show, so the extract
exists to expose the cells the report had to leave out -- not to restate it.

One long table rather than several wide ones, because Tableau's own guidance is
that a single tall table with a dimension column pivots without joins, and a
dashboard built on joins breaks the moment a cycle is added.

Every value here is copied from an artefact under reports/tables. Nothing is
recomputed, so the dashboard cannot disagree with the report; if it ever does,
the cause is this file, not two independent analyses drifting apart.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "data" / "tableau"

# Column order is the contract with the workbook: Tableau binds fields by name,
# so renaming one here silently empties a shelf rather than raising.
FIELDS = [
    "cycle", "year", "dimension", "level", "outcome",
    "n", "n_cases", "n_psu",
    "pct_standardised", "se_pct", "ci_lo_pct", "ci_hi_pct", "pct_crude",
    # A published interval that does not say which critical value produced it
    # cannot be read. These rows carry 21-32 PSUs across 13-16 strata, so the
    # design df runs 8-17 and the critical value runs t(17) = 2.110 to
    # t(8) = 2.306 against z = 1.96 -- up to 18% wider. Two workbooks built a
    # month apart would otherwise plot bands of different meaning under one
    # legend. (The earlier version of this comment said "14-17 PSUs across 7-8
    # strata, single-digit df": 14-17 is the df range of the overall series,
    # written into the PSU slot and halved into the strata slot.)
    "design_dof", "ci_crit",
    "deff", "n_effective",
]

# The six conditions, in the order the report introduces them.
OUTCOMES = [
    ("prev_cvd", "Any cardiovascular disease"),
    ("has_chd", "Coronary heart disease"),
    ("has_mi", "Myocardial infarction"),
    ("has_stroke", "Stroke"),
    ("has_heart_failure", "Heart failure"),
    ("has_angina", "Angina"),
]


def rows(name: str) -> list[dict]:
    with (TABLES / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pct(value: str | None) -> str:
    """Proportions are stored as fractions and read as percentages.

    Tableau formats a measure once, for every mark on the shelf, so mixing
    fractions and percentages in one column would put 0.088 and 8.8 on the same
    axis. Converting here keeps the unit decision out of the workbook.
    """
    return "" if value in (None, "") else f"{100 * float(value):.4f}"


def blank_to_empty(value: str | None) -> str:
    return "" if value is None else value


def main() -> None:
    out: list[dict] = []

    # ── the headline series, one row per cycle ────────────────────────────
    for r in rows("part1_prevalence_by_cycle.csv"):
        out.append({
            "cycle": r["cycle"], "year": r["year"],
            "dimension": "Overall", "level": "All adults 20+",
            "outcome": "Any cardiovascular disease",
            "n": r["n"], "n_cases": r["n_cases"], "n_psu": r["n_psu"],
            "pct_standardised": pct(r["p_std"]), "se_pct": pct(r["se_std"]),
            "ci_lo_pct": pct(r["lo_std"]), "ci_hi_pct": pct(r["hi_std"]),
            "pct_crude": pct(r["p_crude"]),
            "design_dof": r["design_dof"], "ci_crit": f"{float(r['crit']):.4f}",
            "deff": f"{float(r['deff_std']):.4f}",
            "n_effective": f"{float(r['n_effective_std']):.1f}",
        })

    # ── by race, the same estimator on a domain ───────────────────────────
    for r in rows("part1_prevalence_by_race.csv"):
        out.append({
            "cycle": r["cycle"], "year": r["year"],
            "dimension": "Race and ethnicity", "level": r["race_eth"],
            "outcome": "Any cardiovascular disease",
            "n": r["n"], "n_cases": r["n_cases"], "n_psu": r["n_psu"],
            "pct_standardised": pct(r["p_std"]), "se_pct": pct(r["se_std"]),
            "ci_lo_pct": pct(r["lo_std"]), "ci_hi_pct": pct(r["hi_std"]),
            "pct_crude": pct(r["p_crude"]),
            "design_dof": r["design_dof"], "ci_crit": f"{float(r['crit']):.4f}",
            "deff": f"{float(r['deff_std']):.4f}",
            "n_effective": f"{float(r['n_effective_std']):.1f}",
        })

    # ── by age band. These are age-specific rates, so there is nothing to
    #    standardise and no design-based interval was computed for them; the
    #    empty columns are deliberate and the workbook must not plot a band
    #    where none exists.
    for r in rows("part1_prevalence_by_age.csv"):
        out.append({
            "cycle": r["cycle"], "year": r["year"],
            "dimension": "Age band", "level": r["age_group"],
            "outcome": "Any cardiovascular disease",
            "n": r["n"], "n_cases": "", "n_psu": "",
            "pct_standardised": "", "se_pct": "", "ci_lo_pct": "", "ci_hi_pct": "",
            "design_dof": "", "ci_crit": "",
            "pct_crude": pct(r["p"]),
            "deff": "", "n_effective": "",
        })

    # ── each condition, on the same estimator as everything else ──────────
    # These used to read reports/tables/prevalence_has_*.csv, whose only writer
    # is legacy-invalid/run_pipeline.py -- the pipeline this project replaced.
    # Three things followed, all of them in the committed extract:
    #   * `midyear` came from the legacy helper, which dates the redesigned
    #     cycle 2021.5 where every other block dates it 2022.6, so these 66 rows
    #     plotted 1.1 years to the left of the rest of the workbook;
    #   * the prevalence was crude, pooled-weighted and differently filtered, so
    #     the same outcome and cycle appeared twice in one column with two
    #     values (8.0967% against 8.0208%);
    #   * nothing in the build regenerated the inputs, so verify_clean_rebuild
    #     could not have caught either -- the exact "artefact outliving its
    #     code" mode it exists for.
    # They are now age-standardised, interview-weighted and design-based, like
    # the Overall series, which is what makes the docstring's promise true.
    for stem, label in OUTCOMES:
        for r in rows(f"part1_prevalence_{stem}.csv"):
            out.append({
                "cycle": r["cycle"], "year": r["year"],
                "dimension": "Condition", "level": label, "outcome": label,
                "n": r["n"], "n_cases": r["n_cases"], "n_psu": r["n_psu"],
                "pct_standardised": pct(r["p_std"]), "se_pct": pct(r["se_std"]),
                "ci_lo_pct": pct(r["lo_std"]), "ci_hi_pct": pct(r["hi_std"]),
                "design_dof": r["design_dof"], "ci_crit": f"{float(r['crit']):.4f}",
                "pct_crude": pct(r["p_crude"]),
                "deff": f"{float(r['deff_std']):.4f}",
                "n_effective": f"{float(r['n_effective_std']):.1f}",
            })

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "cardiotrace_prevalence.csv"
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in out:
            writer.writerow({k: blank_to_empty(row.get(k)) for k in FIELDS})

    by_dim: dict[str, int] = {}
    for row in out:
        by_dim[row["dimension"]] = by_dim.get(row["dimension"], 0) + 1
    print(f"  {target.relative_to(ROOT)}  {len(out)} rows")
    for dim, count in by_dim.items():
        print(f"    {dim:<22s} {count:4d}")

    if len(out) < 100:
        sys.exit("extract is implausibly small; an input table is probably missing")


if __name__ == "__main__":
    main()
