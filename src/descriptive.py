"""Part 1 and Part 2: the descriptive and quasi-experimental analyses.

WHY THIS IS SEPARATE FROM cohort.py
-----------------------------------
`cohort.py` builds the Part 3 survival cohort: 40-79, free of CVD at baseline,
1999-2014, joined to the mortality linkage. It is covered by the regression
suite and must not move. The descriptive analyses need a different sample
(all adults, every cycle through 2021-2022, CVD as an outcome rather than an
exclusion), so they get their own builder and reuse only the file-access layer
-- which is the part that actually earned its tests, since it is what survives
CDC's renaming.

2021-2022 IS WHY THIS COULD NOT JUST CALL build_cycle()
-------------------------------------------------------
`build_cycle` raises on 2021-2022: CDC dropped BPQ040A and BPQ050A outright and
replaced BPQ090D/BPQ100D with BPQ101D. That is the same identifier drift this
project documents, caught this time by a hard failure rather than a silent gap.
The descriptive analyses do not need the BP-treatment questions, so rather than
widen the tested Part 3 path before a deadline, they read only what they use.

AGE STANDARDISATION
-------------------
Direct standardisation to the 2000 projected U.S. standard population, on the
age bands NCHS names for NHANES -- 20-34, 35-44, 45-54, 55-64, 65-74 -- with
NCHS's open 65+ group split here into 65-74 and 75+.

The split is ours, not theirs. Health, United States Appendix II says NHANES
estimates are "age adjusted ... using five age groups: 20-34, 35-44, 45-54,
55-64, and 65-74 or 65 and over". Reporting the top band open at 65 would
discard the steepest part of the age gradient, and the Master List note
explicitly authorises constructing other groupings from it, so the sixth band
is a defensible refinement -- but it is a refinement, and claiming NCHS
authority for it would repeat the provenance error recorded below.

An earlier version of this module used a 25+ base, on the stated grounds that
"the published distribution starts at 15-24, so no published weight splits at
20." That was wrong, and the error is worth recording because it was a
mis-scoping rather than a miscalculation. The 15-24 grouping appears in Health,
United States Appendix II Table 2 because that table presents the distribution
used for *mortality* statistics. The same standard is published at finer
resolution in the Master List of Klein & Schoenborn, Statistical Notes No. 20,
which carries an explicit 20-24 weight (0.066478); Table A of that report
assigns NHANES distributions on a 20+ base, and no 25+ base is among them.

NHANES top-codes age -- 85 before 2007, 80 from 2007 -- so 75-84 and 85+ are
collapsed into an open 75+ band, which is the one grouping that means the same
thing in every cycle.

VARIANCE
--------
Taylor linearisation for the standardised proportion, aggregated to
stratum x PSU. Writing the standardised estimate as a sum of ratios,

    p_std = sum_j W_j * p_j,   p_j = sum_{i in j} w_i y_i / sum_{i in j} w_i

the linearised value for person i in age group j is

    z_i = W_j * w_i * (y_i - p_j) / S_j,      S_j = sum_{i in j} w_i

Summing z within PSU and applying the stratified formula keeps the covariance
between age groups that a per-group variance would throw away -- the same
person's PSU contributes to several age groups at once.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.cohort import _read, _read_required

# Every cycle present on disk. 2019-2020 does not exist: NHANES suspended field
# operations for COVID and released a combined 2017-2020 pre-pandemic file
# instead, which is not used here because 2017-2018 is available on its own.
DESC_CYCLES = [
    "1999-2000", "2001-2002", "2003-2004", "2005-2006", "2007-2008",
    "2009-2010", "2011-2012", "2013-2014", "2015-2016", "2017-2018",
    "2021-2022",
]

# Cycles fielded entirely before the pandemic, used to fit the counterfactual.
PRE_COVID_CYCLES = DESC_CYCLES[:-1]

AGE_MIN_DESC = 20

# The five self-reported conditions. All five are required: MCQ160F is stroke,
# and losing it silently redefines the outcome.
CVD_ITEMS = ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]

# 2000 projected U.S. standard population, proportion distribution, on the
# all-ages base of 274,634 thousand. Each entry is the sum of the Master List
# five-year weights it spans, written out so the arithmetic is auditable rather
# than asserted.
#
# Source: Klein RJ, Schoenborn CA. "Age Adjustment Using the 2000 Projected U.S.
# Population." Healthy People 2010 Statistical Notes No. 20. NCHS, January 2001,
# Table 1 (Master List). The first five bands are the NHANES groups named in
# Health, United States Appendix II; the 65+ group is split here into 65-74 and
# 75+, which the Master List note authorises and the top-coding note explains.
#
# `age_standardised_prevalence` renormalises over whichever bands are present,
# which is what the Master List note authorises: "the age-adjustment weights
# should be recalculated using the appropriate denominator and must add to 1."
STD_2000 = {
    "20-34": 0.066478 + 0.064530 + 0.071044,   # 20-24, 25-29, 30-34
    "35-44": 0.080762 + 0.081851,              # 35-39, 40-44
    "45-54": 0.072118 + 0.062716,              # 45-49, 50-54
    "55-64": 0.048454 + 0.038793,              # 55-59, 60-64
    "65-74": 0.034264 + 0.031773,              # 65-69, 70-74
    "75+": 0.027000 + 0.017842 + 0.015508,     # 75-79, 80-84, 85+
}
AGE_BINS = [20, 35, 45, 55, 65, 75, np.inf]
AGE_LABELS = ["20-34", "35-44", "45-54", "55-64", "65-74", "75+"]

RACE_LABELS = {
    1: "Mexican American",
    2: "Other Hispanic",
    3: "Non-Hispanic White",
    4: "Non-Hispanic Black",
    5: "Other / Multiracial",
    6: "Non-Hispanic Asian",
    7: "Other / Multiracial",
}


def cycle_midpoint(cycle: str) -> float:
    """Midpoint year, so cycles sit on a real time axis rather than an index."""
    start = int(cycle.split("-")[0])
    return start + 0.5


def build_descriptive_cycle(cycle: str) -> pd.DataFrame:
    """Demographics plus the five CVD questions for one cycle."""
    demo = _read_required(
        cycle, "DEMO",
        ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "WTMEC2YR", "SDMVPSU", "SDMVSTRA"])
    extra = _read(cycle, "DEMO", ["RIDRETH3"])
    if extra is not None and "RIDRETH3" in extra.columns:
        demo = demo.merge(extra, on="SEQN", how="left", validate="1:1")

    mcq = _read(cycle, "MCQ", CVD_ITEMS)
    if mcq is None:
        raise FileNotFoundError(f"MCQ module missing for {cycle}")
    missing = [c for c in CVD_ITEMS if c not in mcq.columns]
    if missing:
        raise KeyError(f"MCQ in {cycle} is missing {missing}")

    df = demo.merge(mcq, on="SEQN", how="left", validate="1:1")
    df = df.rename(columns={
        "RIDAGEYR": "age", "WTMEC2YR": "wtmec2yr",
        "SDMVPSU": "psu", "SDMVSTRA": "strata",
    })
    df["sex"] = df["RIAGENDR"].map({1: "Male", 2: "Female"})
    eth = df["RIDRETH3"] if "RIDRETH3" in df.columns else df["RIDRETH1"]
    df["race_eth"] = eth.map(RACE_LABELS)

    # 7 and 9 are refused / do not know. They are missing, never "no" -- coding
    # them as no is how a refusal quietly becomes a healthy person.
    items = []
    for col in CVD_ITEMS:
        v = df[col].replace({7: np.nan, 9: np.nan})
        items.append(v.map({1: 1.0, 2: 0.0}))
    stacked = pd.concat(items, axis=1)
    # Any yes is a yes even if other items are missing; all-missing stays missing.
    df["prev_cvd"] = np.where(
        stacked.eq(1).any(axis=1), 1.0,
        np.where(stacked.notna().any(axis=1), 0.0, np.nan))

    df["cycle"] = cycle
    df["year"] = cycle_midpoint(cycle)
    keep = ["SEQN", "cycle", "year", "age", "sex", "race_eth",
            "wtmec2yr", "psu", "strata", "prev_cvd"]
    return df[keep]


def build_descriptive(ladder: list | None = None) -> pd.DataFrame:
    """Every cycle, adults 20+, with a usable weight and outcome.

    Pass a list to `ladder` to receive the per-cycle exclusion counts. Part 3 has
    a STROBE flow table and Part 1 had nothing, so 2021-2022 could lose 22% of
    its age-eligible respondents to a zero examination weight -- against 3 to 9%
    everywhere else -- without a reader being able to see it. That cycle is the
    single post-pandemic observation the whole counterfactual rests on, and a
    fourfold change in examination coverage there is a competing explanation for
    the gap.
    """
    frames = [build_descriptive_cycle(c) for c in DESC_CYCLES]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["age"] >= AGE_MIN_DESC]
    if ladder is not None:
        for cycle, g in df.groupby("cycle", observed=True):
            no_weight = int((g["wtmec2yr"].isna() | (g["wtmec2yr"] <= 0)).sum())
            no_outcome = int(g.loc[g["wtmec2yr"] > 0, "prev_cvd"].isna().sum())
            ladder.append({
                "cycle": cycle, "age_eligible": len(g),
                "no_exam_weight": no_weight, "no_outcome": no_outcome,
                "analysed": len(g) - no_weight - no_outcome,
                "lost_pct": 100 * (no_weight + no_outcome) / len(g),
            })
    df = df[df["wtmec2yr"].notna() & (df["wtmec2yr"] > 0)]
    df = df[df["prev_cvd"].notna()]
    df["age_group"] = pd.cut(df["age"], bins=AGE_BINS, labels=AGE_LABELS,
                             right=False, include_lowest=True)
    df = df[df["age_group"].notna()]
    return df.reset_index(drop=True)


def _linearised_variance(df: pd.DataFrame, z: pd.Series) -> float:
    """Stratified, PSU-clustered variance of a linearised total.

    Strata that contribute only one PSU to this domain are COLLAPSED into a
    single pseudo-stratum rather than skipped. Skipping them was the original
    behaviour and it silently understated the variance: a lone PSU has no
    within-stratum degrees of freedom, so dropping it removes its contribution
    entirely instead of borrowing one.

    That is not a hypothetical. The overall series has no singleton strata, but
    the race subgroups have 47 across 44 published subgroup-cycles, and in
    2001-2002 Other Hispanic the dropped strata held 36% of the sample -- a
    standard error of 0.92 pp where the collapsed-stratum estimate gives 1.26.
    The symptom was visible in the output all along: an understated variance
    drives the design effect below one and makes the effective sample size
    exceed the nominal one. Some rows still do -- see `design_effect`, which
    reports rather than suppresses them, because at 14-17 design degrees of
    freedom a per-cycle DEFF below one is usually noise rather than evidence.

    Collapsing is the remedy NCHS documents for exactly this case in a domain
    analysis. It is mildly conservative -- the pooled pseudo-stratum treats
    between-stratum differences as sampling variation -- which is the right
    direction to err in.
    """
    tmp = pd.DataFrame({"strata": df["strata"].values,
                        "psu": df["psu"].values,
                        "z": np.asarray(z)})
    by_psu = tmp.groupby(["strata", "psu"], observed=True)["z"].sum().reset_index()

    sizes = by_psu.groupby("strata", observed=True).size()
    singletons = set(sizes[sizes < 2].index)
    if singletons:
        by_psu["strata"] = by_psu["strata"].where(
            ~by_psu["strata"].isin(singletons), other="__collapsed__")
        # With exactly one singleton the pseudo-stratum still holds one unit
        # and the n_h < 2 branch below would skip it -- the original bug,
        # moved rather than removed. Centring that unit on the grand mean of
        # all PSU totals borrows a degree of freedom instead, which is what
        # Stata's singleunit(centered) does.
        if len(singletons) == 1:
            grand = by_psu["z"].mean()
            lone = by_psu["strata"] == "__collapsed__"
            return _stratified_sum(by_psu[~lone]) + float(
                ((by_psu.loc[lone, "z"] - grand) ** 2).sum())

    return _stratified_sum(by_psu)


def _stratified_sum(by_psu: pd.DataFrame) -> float:
    """Sum of within-stratum sums of squares, with the ultimate-cluster factor.

    No finite-population correction: NHANES sampling fractions are negligible
    and NCHS guidance is to omit it, so including one would understate the
    variance rather than refine it.
    """
    var = 0.0
    for _, g in by_psu.groupby("strata", observed=True):
        n_h = len(g)
        if n_h < 2:
            # Reachable only when the whole domain is a single unit, in which
            # case no design-based variance exists at all.
            continue
        var += n_h / (n_h - 1) * float(((g["z"] - g["z"].mean()) ** 2).sum())
    return var


def _domain_variance(df: pd.DataFrame, z: np.ndarray,
                     design: pd.DataFrame | None) -> float:
    """Variance of a linearised total, over the whole design when df is a domain.

    With no `design` the frame IS the whole sample and this is the ordinary
    stratified formula. With one, the linearised values are scattered back into
    a full-length vector -- zero outside the domain -- so that every sampling
    unit contributes, including the ones holding none of the domain.
    """
    if design is None:
        return _linearised_variance(df, z)
    full = np.zeros(len(design))
    pos = design.index.get_indexer(df.index)
    if (pos < 0).any():
        raise ValueError("domain rows are not a subset of the design frame")
    full[pos] = z
    return _linearised_variance(design, full)


def age_standardised_prevalence(df: pd.DataFrame,
                                outcome: str = "prev_cvd",
                                design: pd.DataFrame | None = None) -> tuple[float, float]:
    """Directly standardised prevalence and its linearised standard error.

    `outcome` names the 0/1 column. It is a parameter rather than a fixed name
    because `src.ascertainment` standardises a different quantity with the same
    machinery, and renaming its column to `prev_cvd` to fit made the caller read
    a hypertension-awareness flag out of something labelled cardiovascular
    disease.

    `design` is the frame carrying the full sampling structure when `df` is a
    DOMAIN -- a subgroup such as one race category. A domain variance must be
    computed over every sampling unit in the sample, with a linearised value of
    zero for people outside the domain; restricting to the domain's own rows
    deletes the units that contain none of its members and recomputes stratum
    means over what is left, which understates the variance. That understatement
    is what drove design effects below one in 19 of 44 published subgroup rows.
    """
    present = [g for g in AGE_LABELS if (df["age_group"] == g).any()]
    total_w = sum(STD_2000[g] for g in present)
    if total_w == 0:
        return float("nan"), float("nan")

    p_std = 0.0
    z = np.zeros(len(df))
    ag = df["age_group"].to_numpy()
    w_all = df["wtmec2yr"].to_numpy()
    y_all = df[outcome].to_numpy()

    for g in present:
        m = ag == g
        w, y = w_all[m], y_all[m]
        s_j = w.sum()
        if s_j <= 0:
            continue
        p_j = float((w * y).sum() / s_j)
        wt = STD_2000[g] / total_w
        p_std += wt * p_j
        z[m] = wt * w * (y - p_j) / s_j

    return p_std, float(np.sqrt(_domain_variance(df, z, design)))


def crude_prevalence(df: pd.DataFrame,
                     outcome: str = "prev_cvd",
                     design: pd.DataFrame | None = None) -> tuple[float, float]:
    """Unstandardised weighted prevalence, for the standardisation contrast."""
    w = df["wtmec2yr"].to_numpy()
    y = df[outcome].to_numpy()
    s = w.sum()
    p = float((w * y).sum() / s)
    z = w * (y - p) / s
    return p, float(np.sqrt(_domain_variance(df, z, design)))


def srs_variance_standardised(df: pd.DataFrame,
                              outcome: str = "prev_cvd") -> float:
    """Variance the STANDARDISED estimate would have under simple random sampling.

    This is the denominator a design effect needs, and getting it wrong is how
    the first version of this function reported design effects below one for
    two of eleven cycles and nineteen of forty-four subgroup rows.

    That version divided the design variance of the *standardised* estimate by
    p(1-p)/n, which is the simple-random-sample variance of a *crude* one. They
    are variances of different estimators. Direct standardisation applies fixed
    weights to within-band proportions, so under simple random sampling its
    variance is

        sum_j W_j^2 * p_j (1 - p_j) / n_j

    which omits the between-band component that p(1-p)/n carries. The reference
    was therefore systematically too large, which pushed the ratio below one --
    an arithmetic artefact of the comparison, not a property of the design.
    """
    present = [g for g in AGE_LABELS if (df["age_group"] == g).any()]
    total_w = sum(STD_2000[g] for g in present)
    if total_w == 0:
        return float("nan")
    var = 0.0
    ag = df["age_group"].to_numpy()
    y_all = df[outcome].to_numpy()
    for g in present:
        m = ag == g
        n_j = int(m.sum())
        if n_j == 0:
            continue
        p_j = float(y_all[m].mean())
        wt = STD_2000[g] / total_w
        var += wt ** 2 * p_j * (1 - p_j) / n_j
    return var


def kish_weighting_factor(df: pd.DataFrame) -> float:
    """1 + CV^2 of the survey weights: the part of the design effect the
    weights alone account for.

    Reported next to the design effect because the two are routinely
    conflated. A design effect measures unequal selection AND clustering
    together; attributing all of it to clustering overstates what the cluster
    structure costs, in this series by roughly a factor of 1.6.
    """
    w = df["wtmec2yr"].to_numpy(float)
    if len(w) == 0 or w.mean() == 0:
        return float("nan")
    return float(1.0 + (w.std(ddof=0) / w.mean()) ** 2)


def design_effect(df: pd.DataFrame, *, se: float,
                  outcome: str = "prev_cvd") -> tuple[float, float]:
    """TOTAL design effect and effective sample size for the standardised estimate.

    Total, meaning it carries both unequal selection probabilities and
    clustering. `kish_weighting_factor` isolates the first, so the two
    together bound what the clustering contributes. Reporting this number as
    the cost of clustering alone would overstate it.

    DEFF is the design-based variance divided by the variance the same estimator
    would have had under simple random sampling of the same size. NCHS publishes
    no variable-by-variable design effects for continuous NHANES, so the only way
    to know what the clustering costs this estimate is to compute it.

    n / DEFF is the effective sample size. NCHS states the bound conditionally:
    "When the DEFF is greater than 1, the effective sample size is less than
    the number of sample persons but greater than the number of clusters." A
    DEFF below 1 therefore sits outside what NCHS describes rather than
    violating a law -- it means either unusually effective stratification or,
    as happened here, a denominator that was not the right one.

    `se` is keyword-only. It must be the standard error of the standardised
    estimate on this same frame, and the caller computes a crude one a few lines
    away; crossing them is silent.
    """
    n = len(df)
    srs_var = srs_variance_standardised(df, outcome=outcome)
    if n == 0 or se <= 0 or not np.isfinite(srs_var) or srs_var <= 0:
        return float("nan"), float("nan")
    deff = se ** 2 / srs_var
    return float(deff), float(n / deff)


def by_cycle(df: pd.DataFrame, group: str | None = None,
             outcome: str = "prev_cvd") -> pd.DataFrame:
    """Per-cycle prevalence, optionally within a subgroup."""
    keys = ["cycle", "year"] + ([group] if group else [])
    rows = []
    for vals, g in df.groupby(keys, observed=True):
        vals = vals if isinstance(vals, tuple) else (vals,)
        # A subgroup is a domain: its variance needs the whole cycle's sampling
        # structure, not just the rows that happen to fall in the subgroup.
        design = df[df["cycle"] == g["cycle"].iloc[0]] if group else None
        p_std, se_std = age_standardised_prevalence(g, outcome=outcome, design=design)
        p_crude, se_crude = crude_prevalence(g, outcome=outcome, design=design)
        row = dict(zip(keys, vals))
        deff_std, n_eff_std = design_effect(g, se=se_std, outcome=outcome)
        kish = kish_weighting_factor(g)
        row.update(n=len(g), n_cases=int(g[outcome].sum()),
                   n_psu=int(g.groupby(["strata", "psu"], observed=True).ngroups),
                   p_std=p_std, se_std=se_std,
                   lo_std=max(0.0, p_std - 1.96 * se_std),
                   hi_std=p_std + 1.96 * se_std,
                   p_crude=p_crude, se_crude=se_crude,
                   deff_std=deff_std, n_effective_std=n_eff_std,
                   kish_weighting=kish,
                   deff_clustering=deff_std / kish if kish else float("nan"))
        rows.append(row)
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)
