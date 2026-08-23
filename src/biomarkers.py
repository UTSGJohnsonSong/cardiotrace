"""Laboratory variables the baseline model does not use, assembled for screening.

The prediction model in `models.py` carries eleven variables chosen because a
clinician would have them at a routine visit. The advisor asked whether anything
outside that set carries independent information, which requires pulling the
laboratory modules the cohort build deliberately left alone.

Three things here are not optional and none of them are visible in the data:

1. CDC RENAMED EVERY ONE OF THESE MODULES. Glycohemoglobin is LAB10 in
   1999-2000, L10_B/_C through 2003-2004, and GHB from 2005-2006 on. Urine
   albumin and creatinine run LAB16 -> L16 -> ALB_CR. Serum chemistry runs
   LAB18 -> L40 -> BIOPRO. `cohort._read` takes a list of stems for exactly this
   reason, so the drift is declared here rather than rediscovered.

2. THE SERUM CREATININE COLUMN ALSO DRIFTS, AND ONLY ONCE. It is LBXSCR
   everywhere except 2001-2002, which uses LBDSCR. Asking for one name loses a
   whole cycle in silence: the merge simply produces NaN for those participants,
   and 2001-2002 sits inside the model's training window.

3. TWO CYCLES OF SERUM CREATININE ARE NOT COMPARABLE TO THE REST UNTIL
   CORRECTED. See CREATININE_CALIBRATION below. This is the one that would have
   done real damage: the two affected cycles fall on opposite sides of the
   train/test split, so uncorrected data manufactures a train-test shift that
   looks exactly like a model failing to transport, when the cause is an assay
   change.

Nothing here computes a risk estimate. It produces variables; the screening
module decides whether any of them earn a place.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.cohort import CYCLES, _read

# ── serum creatinine calibration ─────────────────────────────────────────────
#
# CKD-EPI requires creatinine "standardized to IDMS" (National Kidney Foundation,
# https://www.kidney.org/ckd-epi-creatinine-equation-2021). NHANES measured two
# cycles on a method that was not, and published the Deming regression back onto
# the standard scale for each, describing the correction as "highly recommended":
#
#   1999-2000  standard = 1.013 * NHANES + 0.147
#              https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/1999/DataFiles/LAB18.htm
#   2005-2006  standard = -0.016 + 0.978 * NHANES
#              https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2005/DataFiles/BIOPRO_D.htm
#
# 2001-2002 and 2003-2004 were checked against the same reference method and
# found not to differ (paired t-test p=0.28); their documentation states no
# correction is necessary. 2007-2008 onward were standardised before release.
#
# The 1999-2000 shift is about +0.16 mg/dL, roughly a tenth of a typical value,
# which moves eGFR by several mL/min/1.73m2 -- enough to reclassify CKD stage
# near the boundaries, and enough to bias every model fitted on that cycle.
CREATININE_CALIBRATION: dict[str, tuple[float, float]] = {
    "1999-2000": (0.147, 1.013),        # (intercept, slope)
    "2005-2006": (-0.016, 0.978),
}

# ── module and column drift ──────────────────────────────────────────────────
# Stem candidates are tried in order; every column candidate is requested and
# whichever exists is used. Both lists are per-concept, never per-cycle, so a new
# cycle needs one entry rather than a new branch.
SOURCES: dict[str, tuple[list[str], list[str]]] = {
    "hba1c":            (["GHB", "LAB10", "L10"], ["LBXGH"]),
    "creatinine":       (["BIOPRO", "LAB18", "L40"], ["LBXSCR", "LBDSCR"]),
    "urine_albumin":    (["ALB_CR", "LAB16", "L16"], ["URXUMA"]),
    "urine_creatinine": (["ALB_CR", "LAB16", "L16"], ["URXUCR"]),
}


def egfr_ckdepi_2021(scr: pd.Series, age: pd.Series, female: pd.Series) -> pd.Series:
    """The 2021 race-free CKD-EPI creatinine equation.

        eGFR = 142 * min(Scr/k, 1)^a * max(Scr/k, 1)^-1.200 * 0.9938^age
               * 1.012 [if female]
        k = 0.7 (female) / 0.9 (male);   a = -0.241 (female) / -0.302 (male)

    Coefficients from the National Kidney Foundation's published form,
    https://www.kidney.org/ckd-epi-creatinine-equation-2021, matching Inker et
    al., N Engl J Med 2021. Serum creatinine in mg/dL, already IDMS-standardised
    -- see `calibrate_creatinine`, which two cycles require.

    The 2021 equation drops the race coefficient the 2009 version carried. That
    is not only a clinical-practice question here: the 2009 equation multiplied
    eGFR by 1.159 for Black participants, so a race-stratified analysis using it
    would have had the race term already baked into one of its own predictors.
    """
    scr = pd.to_numeric(scr, errors="coerce")
    age = pd.to_numeric(age, errors="coerce")
    female = np.asarray(female).astype(bool)
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr / kappa
    return pd.Series(
        142.0
        * np.minimum(ratio, 1.0) ** alpha
        * np.maximum(ratio, 1.0) ** -1.200
        * 0.9938 ** age
        * np.where(female, 1.012, 1.0),
        index=scr.index)


def calibrate_creatinine(scr: pd.Series, cycle: str) -> pd.Series:
    """Put one cycle's serum creatinine onto the IDMS-traceable scale."""
    intercept, slope = CREATININE_CALIBRATION.get(cycle, (0.0, 1.0))
    return intercept + slope * pd.to_numeric(scr, errors="coerce")


def _first_present(frame: pd.DataFrame, names: list[str]) -> pd.Series | None:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return None


def load_cycle(cycle: str) -> pd.DataFrame:
    """One row per SEQN with whichever laboratory concepts that cycle carries."""
    out = pd.DataFrame()
    for concept, (stems, cols) in SOURCES.items():
        frame = _read(cycle, stems, cols)
        if frame is None:
            continue
        series = _first_present(frame, cols)
        if series is None:
            continue
        piece = pd.DataFrame({"seqn": frame["SEQN"].astype("int64"),
                              concept: series.to_numpy()})
        out = piece if out.empty else out.merge(piece, on="seqn", how="outer")

    if out.empty:
        return out

    if "creatinine" in out.columns:
        out["creatinine"] = calibrate_creatinine(out["creatinine"], cycle)
        out["creatinine_calibrated"] = cycle in CREATININE_CALIBRATION

    # Urine albumin-to-creatinine ratio in mg/g. NHANES reports urine albumin in
    # ug/mL and urine creatinine in mg/dL, so the ratio needs 100x to land on
    # mg per gram: (ug/mL) / (mg/dL) = (mg/L) / (10 mg/L) -> x100 for mg/g.
    if {"urine_albumin", "urine_creatinine"} <= set(out.columns):
        ucr = pd.to_numeric(out["urine_creatinine"], errors="coerce")
        uma = pd.to_numeric(out["urine_albumin"], errors="coerce")
        out["uacr"] = np.where(ucr > 0, 100.0 * uma / ucr, np.nan)

    out["cycle"] = cycle
    return out


def load_all(cycles: list[str] | None = None) -> pd.DataFrame:
    frames = [load_cycle(c) for c in (cycles or CYCLES)]
    return pd.concat([f for f in frames if not f.empty], ignore_index=True)


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Non-missing count per concept per cycle.

    A concept that vanishes for one cycle is the failure mode this module exists
    to prevent, and it is invisible downstream: the merge yields NaN, the model
    drops those rows, and the only symptom is a smaller n nobody reads.
    """
    concepts = [c for c in ("hba1c", "creatinine", "uacr") if c in df.columns]
    rows = []
    for cycle, block in df.groupby("cycle", sort=False):
        row: dict[str, object] = {"cycle": cycle, "n": len(block)}
        for concept in concepts:
            row[concept] = int(block[concept].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)
