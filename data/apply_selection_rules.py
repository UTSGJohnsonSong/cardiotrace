"""
Stage 1 — apply an ordered, auditable rule ladder to the Stage 0 file catalog.

WHY THIS EXISTS
---------------
`build_catalog.py` enumerates all 1,821 public NHANES files. Claiming "we
excluded the rest for good reasons" is worth nothing unless every excluded file
carries the specific rule that excluded it. This script produces that ledger:
one row per file, exactly one rule, keep or drop.

THE LADDER
----------
Rules are ordered and first-match-wins, so each file gets exactly one reason.
Rules split into two kinds, and the split matters more than the rules:

  MECHANICAL (R0-R4)  decidable from the catalog alone, no judgement.
                      Anyone re-running this gets the same answer.

  JUDGEMENT  (R5)     "not in the pre-declared concept whitelist". This is the
                      only rule that encodes an opinion, and the whitelist is
                      derived from the DAG in docs/research-design.md, not from
                      looking at the outcome.

Reporting the two counts separately is the honest way to say how much of the
selection is defensible-by-construction and how much rests on our causal model.

    R0 ACCESS      no public data file — NCHS Research Data Center application
                   required (on-site, fee, months). Out of scope for this project.
    R1 UNIT        analysis unit is not the person: lookup tables, food-level
                   records, product-level supplement databases. Joining them to
                   person-level data needs an aggregation step that is its own
                   methodology.
    R2 POPULATION  administered to youth/children only. Target population is
                   adults 40+.
    R3 SURPLUS     surplus-specimen special assays (SS* modules). Run on stored
                   leftover specimens from a subsample; most have no companion
                   public weight variable, so population estimates are not
                   possible without case-by-case weight verification.
    R4 DIET-FRAME  24-hour dietary recall. Needs WTDRD1/WTDR2D, a different
                   sampling frame from WTMEC2YR. Also: in our DAG diet is a
                   MEDIATOR on the SEP -> CVD path, so model E1 must not adjust
                   for it anyway. Excluded from primary; stated as a limitation.
    KEEP           matches a concept in the pre-declared whitelist.
    R5 OFF-DAG     everything else: no path to CVD death in the DAG and not a
                   confounder (environmental toxicants, viral serology, other
                   organ systems). Flagged as hypothesis-generating, not used.

Usage:
    python data/apply_selection_rules.py
"""

import csv
import logging
import re
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

CATALOG_DIR = Path(__file__).parent / "catalog"
CATALOG = CATALOG_DIR / "nhanes_file_catalog.csv"
LEDGER = CATALOG_DIR / "selection_ledger.csv"

# ── The concept whitelist ────────────────────────────────────────────────────
# concept -> (module stems, expected cycle coverage, DAG node)
#
# Matching is on the MODULE STEM, not the file label. CDC's labels are not
# stable: the same LDL/triglyceride file is variously "Cholesterol - LDL &
# Triglycerides", "Cholesterol - LDL, Triglyceride & Apoliprotein (ApoB)"
# (their typo), "Cholesterol - Low - Density Lipoprotein (LDL) &
# Triglycerides", and one HDL label uses an en dash instead of a hyphen. A
# label regex silently under-matches; a hand-verified stem list does not.
#
# Every stem below was read off the Stage 0 catalog and checked against its
# cycle coverage. `expect` is the number of cycles the concept must cover; the
# run FAILS if actual coverage is lower, so a future CDC rename cannot slip
# through as "that panel wasn't collected".
WHITELIST: dict[str, tuple[set[str], int, str]] = {
    # design + demographics — survey weights, PSU, strata, age, sex, race, education, PIR
    "demographics":          ({"DEMO"}, 11, "AGE/SEX/RACE/EDU/INC + design"),
    # baseline CVD: the OLD outcome, now the EXCLUSION criterion. Also FAMHX (MCQ300).
    "medical_conditions":    ({"MCQ"}, 11, "PREV_CVD (exclusion) + FAMHX"),
    # Rose Angina — symptom-based CVD definition, for outcome-validity sensitivity
    "cardiovascular_health": ({"CDQ"}, 10, "outcome validity check"),
    # BP: manual cuff through 2018, oscillometric from 2017. 2017-2018 has BOTH
    # (the bridging sample). BPQ is the questionnaire (diagnosis + treatment).
    "blood_pressure_exam":   ({"BPX", "BPXO"}, 11, "BP"),
    "blood_pressure_quex":   ({"BPQ"}, 11, "BP diagnosis -> MEDS"),
    "body_measures":         ({"BMX"}, 11, "ADIP"),
    # lipids across three naming eras
    "cholesterol_total_hdl": ({"LAB13", "L13", "TCHOL", "HDL"}, 11, "LIP"),
    "cholesterol_ldl_trig":  ({"LAB13AM", "L13AM", "TRIGLY"}, 11, "LIP"),
    "glycohemoglobin":       ({"LAB10", "L10", "GHB"}, 11, "GLU"),
    "fasting_glucose":       ({"LAB10AM", "L10AM", "GLU"}, 11, "GLU"),
    "diabetes_quex":         ({"DIQ"}, 11, "GLU diagnosis"),
    "biochemistry":          ({"LAB18", "L40", "BIOPRO"}, 11, "KID (creatinine)"),
    "urine_albumin_creat":   ({"LAB16", "L16", "ALB_CR"}, 11, "KID (ACR)"),
    "kidney_quex":           ({"KIQ", "KIQ_U"}, 11, "KID"),
    "smoking":               ({"SMQ"}, 11, "SMK"),
    "alcohol":               ({"ALQ"}, 11, "ALC"),
    "physical_activity":     ({"PAQ"}, 11, "PA"),
    # person-level prescription file only; RXQ_DRUG is a lookup table (dropped by R1)
    "prescription_meds":     ({"RXQ_RX"}, 11, "MEDS"),
    "health_insurance":      ({"HIQ"}, 11, "INS"),
    # pre-declared as secondary/exploratory: 2005 onward only
    "sleep":                 ({"SLQ"}, 8, "exploratory"),
}

# Explicitly considered and rejected, so the near-misses are on the record too.
NEAR_MISS_NOTES = {
    "CVX":    "cardiovascular FITNESS (treadmill test), not CVD history — different construct",
    "L13_2":  "second-exam replicate on a subsample, not the primary measurement",
    "L10_2":  "second-exam replicate on a subsample",
    "L40_2":  "second-exam replicate on a subsample",
    "SMQFAM": "household smokers — secondhand exposure, not the participant's own smoking",
    "SMQRTU": "recent tobacco use (5-day recall) — supplements SMQ, not a substitute",
    "SMQSHS": "secondhand smoke exposure",
    "SMQMEC": "MEC-administered youth/adult split form",
    "PAQIAF": "individual activity file — one row per activity, not per person",
}


def stem_of(module: str) -> str:
    """Strip the biennial cycle suffix: TCHOL_J -> TCHOL, LAB13AM -> LAB13AM."""
    return re.sub(r"_[A-L]$", "", module)

# ── Mechanical rules, in order ───────────────────────────────────────────────
def rule_r1_unit(label: str, module: str) -> bool:
    # PAX* are accelerometer files at minute/hour/day granularity (PAXRAW runs
    # to hundreds of GB across the series) — many rows per person.
    return bool(re.search(
        r"technical support file|food code|modification code|individual foods"
        r"|supplement database|drug information|individual dietary supplements",
        label, re.I,
    ) or stem_of(module) in {"RXQ_DRUG", "PAQIAF"}
       or stem_of(module).startswith("PAX"))


# Youth-only modules, enumerated explicitly. An earlier version inferred these
# from a trailing "Y" in the module name (^[A-Z]+Y$) — which silently swallowed
# TRIGLY (triglycerides) and dropped 8 of 11 cycles of lipid data. The coverage
# assertion caught it. Heuristics on identifiers are exactly how the 1999-2004
# laboratory gap happened; enumerate instead of pattern-matching.
YOUTH_MODULES = {"ALQY", "PAQY", "DBQY", "SMQY"}


def rule_r2_population(label: str, module: str) -> bool:
    return bool(re.search(r"\byouth\b|\bchildren\b|\bchild\b|adolescen", label, re.I)
                or stem_of(module) in YOUTH_MODULES)


def rule_r3_surplus(label: str, module: str) -> bool:
    return bool(re.search(r"\(surplus\)", label, re.I) or module.startswith("SS"))


def classify(row: dict) -> tuple[str, str, str, str]:
    """Return (rule_id, rule_name, disposition, kind). First match wins."""
    label, module = row["file_label"], (row["module"] or "")
    downloadable = str(row["downloadable"]).lower() == "true"

    if not downloadable:
        return "R0", "ACCESS: RDC application required", "drop", "mechanical"
    if rule_r1_unit(label, module):
        return "R1", "UNIT: not person-level", "drop", "mechanical"
    if rule_r2_population(label, module):
        return "R2", "POPULATION: youth/children only", "drop", "mechanical"
    if rule_r3_surplus(label, module):
        return "R3", "SURPLUS: subsample assay, no companion weight", "drop", "mechanical"
    if row["component"] == "Dietary":
        return "R4", "DIET-FRAME: WTDRD1 frame + mediator in DAG", "drop", "mechanical"

    stem = stem_of(module)
    for concept, (stems, _expect, _node) in WHITELIST.items():
        if stem in stems:
            return "KEEP", f"whitelist: {concept}", "keep", "judgement"

    if stem in NEAR_MISS_NOTES:
        return "R5", f"OFF-DAG (considered): {NEAR_MISS_NOTES[stem]}", "drop", "judgement"
    return "R5", "OFF-DAG: no path to outcome, not a confounder", "drop", "judgement"


def assert_coverage(out: list[dict]) -> list[str]:
    """Every whitelisted concept must reach its expected cycle coverage.

    This is rule 6.4.2 in the design doc made executable: a file that the
    catalog says exists but that our stem list fails to match must raise, not
    disappear. The 1999-2004 laboratory gap happened precisely because a
    missing file was treated as 'not collected that cycle'.
    """
    problems = []
    for concept, (stems, expect, node) in WHITELIST.items():
        cycles = {o["cycle"] for o in out
                  if o["disposition"] == "keep" and o["rule"].endswith(concept)}
        if len(cycles) < expect:
            problems.append(
                f"{concept}: covers {len(cycles)}/{expect} expected cycles "
                f"(stems {sorted(stems)}) — a rename may have been missed"
            )
    return problems


def main() -> None:
    with open(CATALOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out = []
    for r in rows:
        rule_id, rule, disp, kind = classify(r)
        out.append({
            "cycle": r["cycle"], "component": r["component"], "module": r["module"],
            "file_label": r["file_label"], "rule_id": rule_id, "rule": rule,
            "disposition": disp, "decided_by": kind, "data_url": r["data_url"],
        })

    with open(LEDGER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # ── report ──
    by_rule = Counter((o["rule_id"], o["rule"]) for o in out)
    kept = [o for o in out if o["disposition"] == "keep"]
    mech = sum(1 for o in out if o["decided_by"] == "mechanical")

    log.info(f"\n{'rule':6s} {'n':>6s}  {'kind':10s} description")
    log.info("-" * 78)
    for (rid, rule), n in sorted(by_rule.items()):
        kind = next(o["decided_by"] for o in out if o["rule_id"] == rid)
        log.info(f"{rid:6s} {n:6,d}  {kind:10s} {rule}")

    log.info("-" * 78)
    log.info(f"total files              {len(out):6,d}")
    log.info(f"  excluded mechanically  {mech - sum(1 for o in out if o['decided_by']=='mechanical' and o['disposition']=='keep'):6,d}"
             f"   ({(mech)/len(out):.1%} of all files, no judgement involved)")
    log.info(f"  excluded by judgement  {sum(1 for o in out if o['rule_id']=='R5'):6,d}"
             f"   (R5 only — rests on the DAG)")
    log.info(f"  KEPT                   {len(kept):6,d}   ({len(kept)/len(out):.1%})")
    log.info(f"\nkept files by concept (DAG node):")
    for concept, (stems, expect, node) in WHITELIST.items():
        files = [k for k in kept if k["rule"].endswith(concept)]
        cycles = len({k["cycle"] for k in files})
        flag = "  " if cycles >= expect else "!!"
        log.info(f"{flag}{concept:24s} {len(files):3d} files  {cycles:2d}/{expect} cycles"
                 f"   [{node}]")

    problems = assert_coverage(out)
    if problems:
        log.error("\nCOVERAGE ASSERTION FAILED:")
        for p in problems:
            log.error(f"  {p}")
        raise SystemExit(1)
    log.info("\nCoverage assertions passed for all whitelisted concepts.")
    log.info(f"ledger -> {LEDGER}")


if __name__ == "__main__":
    main()
