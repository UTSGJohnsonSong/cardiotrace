"""Diagnostic ascertainment: what share of measurably ill people know it.

WHY THIS EXISTS
---------------
Part 1's outcome is self-reported physician diagnosis, so it moves with access
to care as well as with disease. That is stated as a limitation, but a
limitation that is only stated cannot be checked. Hypertension can be both
measured at the examination and self-reported in the questionnaire, so for that
one condition the diagnostic pipeline is directly observable:

    ascertained fraction
        = P(told you had high blood pressure | measured high OR on medication)

If expanding access were driving self-reported prevalence upward, this fraction
has to rise, and rise when access rose. It is a far sharper instrument than an
insurance proxy, because it needs no assumption about what insurance does.

THE DENOMINATOR HAS TO INCLUDE THE TREATED
------------------------------------------
Conditioning on measured hypertension alone inverts the answer. Someone who was
diagnosed, put on medication and successfully controlled measures normal, so a
denominator of "currently measures high" drops exactly the people the diagnostic
pipeline worked for -- and drops more of them as treatment improves. In this
series the share of the already-diagnosed who no longer measure high rises from
50% to 68%, so the omission grows monotonically over precisely the window the
trend is read from.

Measured on that denominator, ascertainment looks flat: 50.0% to 50.8% across
the auscultatory window. On the conventional NHANES awareness denominator --
measured high OR currently taking antihypertensive medication -- it rises from
63.7% to 69.2%. The two readings support opposite conclusions, and only the
second one answers the question being asked.

THE INSTRUMENT CHANGE IS THE CATCH
----------------------------------
NHANES measured blood pressure auscultatorily (BPX, mercury
sphygmomanometer throughout) through 2017-2018 and oscillometrically (BPXO)
from 2017-2018 on. The two are
not interchangeable, and a switch mid-series would look exactly like a change in
the thing being measured. 1999-2018 therefore uses BPX throughout, and
2021-2022 -- which has no BPX at all -- is reported separately and marked.

2017-2018 ran both instruments on an overlapping subsample -- 7,132 of the
8,704 BPX participants, 5,601 with a usable systolic on both. That overlap is
the bridge any measured-outcome extension of this series will need, and it is
the reason the split above costs a footnote rather than the analysis.

THRESHOLD
---------
Measured hypertension is mean systolic >= 140 or mean diastolic >= 90, the
long-standing JNC definition. The 2017 ACC/AHA guideline moved the threshold to
130/80; using it would reclassify a large block of people mid-series for reasons
that have nothing to do with their blood pressure, so the older threshold is
kept for comparability and the newer one is available as a sensitivity check.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.cohort import _read, _read_required
from src.descriptive import (
    AGE_BINS, AGE_LABELS, AGE_MIN_DESC, DESC_CYCLES, RACE_LABELS,
    age_standardised_prevalence, cycle_midpoint, crude_prevalence,
)

# Cycles with auscultatory readings, so the instrument is constant.
BPX_CYCLES = [c for c in DESC_CYCLES if c != "2021-2022"]

SBP_READINGS = ["BPXSY1", "BPXSY2", "BPXSY3", "BPXSY4"]
DBP_READINGS = ["BPXDI1", "BPXDI2", "BPXDI3", "BPXDI4"]
SBP_OSC = ["BPXOSY1", "BPXOSY2", "BPXOSY3"]
DBP_OSC = ["BPXODI1", "BPXODI2", "BPXODI3"]

# Antihypertensive medication. The item was renamed for 2021-2022, and the
# neighbouring BPQ101D in that file is CHOLESTEROL medication -- reading it as
# the blood-pressure item would silently swap one drug class for another.
# Verified against the variable labels in every cycle on disk:
#   BPQ050A  "Now taking prescribed medicine for HBP"   1999-2000 .. 2017-2018
#   BPQ150   "Taking high blood pressure medication"    2021-2022
MED_ITEMS = ["BPQ050A", "BPQ150"]

HTN_SBP, HTN_DBP = 140.0, 90.0


def _mean_bp(df: pd.DataFrame, cols: list[str], zero_is_missing: bool) -> pd.Series:
    """Mean of whichever readings the participant actually has.

    A diastolic of 0 is not a blood pressure -- it is the coded absence of a
    fifth Korotkoff sound. Averaging it in would drag a real reading down toward
    a value nobody has, which is how a measurement convention turns into a
    fabricated observation.
    """
    present = [c for c in cols if c in df.columns]
    if not present:
        return pd.Series(np.nan, index=df.index)
    block = df[present].astype(float)
    if zero_is_missing:
        block = block.where(block > 0)
    return block.mean(axis=1, skipna=True)


def build_ascertainment_cycle(cycle: str, oscillometric: bool = False) -> pd.DataFrame:
    """Adults 20+ with a usable measured BP and a usable questionnaire answer."""
    demo = _read_required(
        cycle, "DEMO",
        ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "WTMEC2YR", "SDMVPSU", "SDMVSTRA"])
    extra = _read(cycle, "DEMO", ["RIDRETH3"])
    if extra is not None and "RIDRETH3" in extra.columns:
        demo = demo.merge(extra, on="SEQN", how="left", validate="1:1")

    stem = "BPXO" if oscillometric else "BPX"
    sbp_cols = SBP_OSC if oscillometric else SBP_READINGS
    dbp_cols = DBP_OSC if oscillometric else DBP_READINGS
    bpx = _read(cycle, stem, sbp_cols + dbp_cols)
    if bpx is None:
        raise FileNotFoundError(f"{stem} missing for {cycle}")
    # `_read` returns a SEQN-only frame when the file exists but carries none of
    # the requested columns, so the None check above cannot catch a rename. Left
    # unguarded, _mean_bp returns all-NaN, measured_htn is all-NaN, and
    # build_ascertainment drops the entire cycle -- the series loses a point and
    # nothing says so. build_descriptive_cycle already guards its items this way.
    missing = [c for c in sbp_cols + dbp_cols if c not in bpx.columns]
    if missing:
        raise KeyError(f"{stem} in {cycle} is missing {missing}")

    bpq = _read(cycle, "BPQ", ["BPQ020", "BPQ040A"] + MED_ITEMS)
    if bpq is None or "BPQ020" not in bpq.columns:
        raise KeyError(f"BPQ020 missing for {cycle}")
    med_col = next((c for c in MED_ITEMS if c in bpq.columns), None)
    if med_col is None:
        raise KeyError(f"no antihypertensive medication item for {cycle}; "
                       f"looked for {MED_ITEMS}")

    df = demo.merge(bpx, on="SEQN", how="left", validate="1:1")
    df = df.merge(bpq, on="SEQN", how="left", validate="1:1")
    df = df.rename(columns={"RIDAGEYR": "age", "WTMEC2YR": "wtmec2yr",
                            "SDMVPSU": "psu", "SDMVSTRA": "strata"})
    eth = df["RIDRETH3"] if "RIDRETH3" in df.columns else df["RIDRETH1"]
    df["race_eth"] = eth.map(RACE_LABELS)

    df["sbp"] = _mean_bp(df, sbp_cols, zero_is_missing=False)
    df["dbp"] = _mean_bp(df, dbp_cols, zero_is_missing=True)
    # Either arm can establish hypertension, so a positive on the arm that IS
    # present is conclusive. A negative is not: with one arm missing the
    # criterion was only half applied, and scoring that as "not hypertensive"
    # is the same mistake as reading a refusal code as "no". It also varies over
    # time -- unreadable diastolics run from 45 per cycle down to zero, because
    # the oscillometric device never codes an absent fifth Korotkoff sound -- so
    # it would enter a trend series as a drift rather than a constant offset.
    high = (df["sbp"] >= HTN_SBP) | (df["dbp"] >= HTN_DBP)
    incomplete = df["sbp"].isna() | df["dbp"].isna()
    df["measured_htn"] = high.astype(float)
    df.loc[incomplete & ~high, "measured_htn"] = np.nan

    # 7/9 are refused / do not know: missing, never "no".
    df["told_htn"] = df["BPQ020"].replace({7: np.nan, 9: np.nan}).map({1: 1.0, 2: 0.0})

    # The medication item is skip-gated behind BPQ020 and, before 2021, behind
    # BPQ040A as well. A skip is an answer, not a gap: someone never told they
    # had high blood pressure is not on medication for it. Reading the skip as
    # missing would drop those people from the denominator entirely, which is
    # the same error in a different place.
    med = df[med_col].replace({7: np.nan, 9: np.nan}).map({1: 1.0, 2: 0.0})
    never_told = df["BPQ020"] == 2
    med = med.where(~(med.isna() & never_told), 0.0)
    if "BPQ040A" in df.columns:
        not_prescribed = df["BPQ040A"] == 2
        med = med.where(~(med.isna() & not_prescribed), 0.0)
    df["on_med"] = med

    df["cycle"] = cycle
    df["year"] = cycle_midpoint(cycle)
    df["instrument"] = "oscillometric" if oscillometric else "auscultatory"
    # Anyone measuring high, or on treatment for it, is a person the diagnostic
    # pipeline should have reached.
    df["hypertensive"] = np.where(
        (df["measured_htn"] == 1) | (df["on_med"] == 1), 1.0,
        np.where(df["measured_htn"].isna() & df["on_med"].isna(), np.nan, 0.0))

    return df[["SEQN", "cycle", "year", "instrument", "age", "race_eth",
               "wtmec2yr", "psu", "strata", "sbp", "dbp",
               "measured_htn", "on_med", "hypertensive", "told_htn"]]


def build_ascertainment() -> pd.DataFrame:
    """The auscultatory series, plus 2021-2022 on the oscillometric instrument."""
    frames = [build_ascertainment_cycle(c) for c in BPX_CYCLES]
    frames.append(build_ascertainment_cycle("2021-2022", oscillometric=True))
    df = pd.concat(frames, ignore_index=True)
    df = df[df["age"] >= AGE_MIN_DESC]
    df = df[df["wtmec2yr"].notna() & (df["wtmec2yr"] > 0)]
    df = df[df["hypertensive"].notna() & df["told_htn"].notna()]
    df["age_group"] = pd.cut(df["age"], bins=AGE_BINS, labels=AGE_LABELS,
                             right=False, include_lowest=True)
    return df[df["age_group"].notna()].reset_index(drop=True)


def ascertained_by_cycle(df: pd.DataFrame) -> pd.DataFrame:
    """Share of the measurably hypertensive who report having been told.

    Age-standardised, because the diagnosed share rises steeply with age and the
    population aged: without standardisation an ageing sample would manufacture
    an improvement in ascertainment out of nothing.

    The `measured_only` column repeats the calculation on the narrower "currently
    measures high" denominator. It is reported alongside rather than dropped,
    because the gap between the two IS the finding: the narrow version is flat
    and the correct one rises, and a reader should be able to see which choice
    produced which answer.
    """
    rows = []
    for (cycle, year, instrument), g in df.groupby(
            ["cycle", "year", "instrument"], observed=True):
        htn = g[g["hypertensive"] == 1]
        if htn.empty:
            continue
        p_std, se_std = age_standardised_prevalence(htn, outcome="told_htn", design=g)
        p_crude, se_crude = crude_prevalence(htn, outcome="told_htn", design=g)

        narrow = g[g["measured_htn"] == 1]
        p_narrow, _ = age_standardised_prevalence(narrow, outcome="told_htn", design=g)

        rows.append({
            "cycle": cycle, "year": year, "instrument": instrument,
            "n_hypertensive": len(htn), "n_measured_high": len(narrow),
            "n_on_med": int(htn["on_med"].sum()),
            "n_told": int(htn["told_htn"].sum()),
            "ascertained_std": p_std, "se_std": se_std,
            "lo_std": max(0.0, p_std - 1.96 * se_std),
            "hi_std": p_std + 1.96 * se_std,
            "ascertained_crude": p_crude, "se_crude": se_crude,
            "measured_only_std": p_narrow,
        })
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
