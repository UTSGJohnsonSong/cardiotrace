"""Laboratory derivations the cohort carries the inputs for but does not compute.

`cohort.build_cohort` already reads serum creatinine, urine albumin, urine
creatinine and glycohemoglobin through the crosswalk, which handles the module
and column drift correctly -- including that serum creatinine is `LBDSCR` in
2001-2002 and `LBXSCR` everywhere else. What the crosswalk cannot carry is a
calibration: its `to_canonical` column is a multiplier, and two cycles of serum
creatinine need an intercept as well.

That gap is not cosmetic, and it is invisible in the data unless looked for:

    cycle       n     mean creatinine (mg/dL, as loaded)
    1999-2000  2030   0.7600     <- training cycle, ~0.14 below its neighbours
    2001-2002  2277   0.9026
    2003-2004  2076   0.9102
    2005-2006  2095   0.9506     <- 10-year test cycle, ~0.07 above
    2007-2008  2800   0.8799
    2009-2014  8264   0.891-0.918

The training cycles average 0.8597 and the 10-year test cycles 0.9102. That
0.05 mg/dL gap is an assay change, not a population one, and it sits exactly on
the train/test boundary: a model fitted on creatinine or eGFR would learn one
scale and be judged on another, which looks like a model failing to transport.

Nothing here is used by the published Part 3 model -- creatinine is in neither
P_FEATURES nor E2_ADJUSTMENT -- so applying the correction changes no result
already in print. It exists so the screening in `screening.py` can consider
kidney function without inheriting the artefact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

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
# 2001-2002 and 2003-2004 were compared against the same reference method and
# found not to differ (paired t-test p = 0.28); their documentation states that
# no correction is necessary. 2007-2008 onward were standardised by CDC before
# release.
#
# The equations were applied without first looking at the data, and they move
# each named cycle toward the untouched ones rather than away: 1999-2000 from
# 0.6931 to 0.8491 and 2005-2006 from 0.8899 to 0.8543 on the full NHANES
# sample, against 0.85-0.88 elsewhere. The 1999-2000 shift of 0.156 mg/dL
# matches the 0.158 CDC reports. Both directions correct, which is the check
# that the equations were read the right way round.
CREATININE_CALIBRATION: dict[str, tuple[float, float]] = {
    "1999-2000": (0.147, 1.013),        # (intercept, slope)
    "2005-2006": (-0.016, 0.978),
}


# Every cycle this project analyses, so an unrecognised label is a typo or a
# new cycle rather than a cycle that needs no correction. The two are
# indistinguishable to `.fillna`, and the repo already carries two conventions
# for cycle strings -- `model_results.json` uses an en dash where the cohort
# uses a hyphen -- so the confusion is available today, not hypothetical.
KNOWN_CYCLES = frozenset([
    "1999-2000", "2001-2002", "2003-2004", "2005-2006", "2007-2008",
    "2009-2010", "2011-2012", "2013-2014", "2015-2016", "2017-2018",
    "2021-2022",
])


def calibrate_creatinine(df: pd.DataFrame, column: str = "creatinine") -> pd.Series:
    """`column`, per row, on the IDMS-traceable scale its cycle requires.

    An unknown cycle label raises. `.fillna((0.0, 1.0))` is the right default
    for a cycle CDC says needs no correction and the wrong one for a cycle the
    map has never seen, and nothing downstream can tell those apart: the page
    would state that 1999-2000 needed no correction, which is the opposite of
    what this module exists to say.
    """
    unknown = sorted(set(df["cycle"].dropna().unique()) - KNOWN_CYCLES)
    if unknown:
        raise KeyError(
            f"unrecognised cycle label(s) {unknown}. Calibration would silently "
            f"fall back to the identity, and the report would then state that "
            f"these cycles needed no correction.")
    scr = pd.to_numeric(df[column], errors="coerce")
    intercept = df["cycle"].map(
        {c: v[0] for c, v in CREATININE_CALIBRATION.items()}).fillna(0.0)
    slope = df["cycle"].map(
        {c: v[1] for c, v in CREATININE_CALIBRATION.items()}).fillna(1.0)
    return intercept + slope * scr


def egfr_ckdepi_2021(scr: pd.Series, age: pd.Series, female: pd.Series) -> pd.Series:
    """The 2021 race-free CKD-EPI creatinine equation.

        eGFR = 142 * min(Scr/k, 1)^a * max(Scr/k, 1)^-1.200 * 0.9938^age
               * 1.012 [if female]
        k = 0.7 (female) / 0.9 (male);   a = -0.241 (female) / -0.302 (male)

    Coefficients from the National Kidney Foundation's published form,
    https://www.kidney.org/ckd-epi-creatinine-equation-2021, matching Inker et
    al., N Engl J Med 2021. Serum creatinine in mg/dL and already IDMS-
    standardised -- which is exactly what `calibrate_creatinine` is for.

    The 2021 equation drops the race coefficient the 2009 version carried. That
    is not only a clinical-practice question here: the 2009 equation multiplied
    eGFR by 1.159 for Black participants, so any analysis that used it alongside
    race would have had the race term already inside one of its own predictors.
    """
    scr = pd.to_numeric(scr, errors="coerce")
    age = pd.to_numeric(age, errors="coerce")
    fem = np.asarray(female).astype(bool)
    kappa = np.where(fem, 0.7, 0.9)
    alpha = np.where(fem, -0.241, -0.302)
    ratio = scr / kappa
    return pd.Series(
        142.0
        * np.minimum(ratio, 1.0) ** alpha
        * np.maximum(ratio, 1.0) ** -1.200
        * 0.9938 ** age
        * np.where(fem, 1.012, 1.0),
        index=scr.index)


def derive(cohort: pd.DataFrame) -> pd.DataFrame:
    """Add the derived laboratory variables, leaving the originals in place.

    Returns a copy. `creatinine` keeps its as-loaded values so the calibration
    remains auditable against them; the corrected series is a separate column
    and is the only one eGFR is computed from.
    """
    d = cohort.copy()
    d["creatinine_std"] = calibrate_creatinine(d)
    d["creatinine_calibrated"] = d["cycle"].isin(CREATININE_CALIBRATION)
    d["egfr"] = egfr_ckdepi_2021(d["creatinine_std"], d["age"], d["sex"] == "Female")

    # Urine albumin-to-creatinine ratio, mg/g. NHANES reports urine albumin in
    # ug/mL and urine creatinine in mg/dL, so the ratio needs 100x to land on
    # mg per gram. Logged because it spans four orders of magnitude and enters
    # every risk equation that uses it on the log scale.
    uma = pd.to_numeric(d["urine_albumin"], errors="coerce")
    ucr = pd.to_numeric(d["urine_creatinine"], errors="coerce")
    d["uacr"] = np.where(ucr > 0, 100.0 * uma / ucr, np.nan)
    d["log_uacr"] = np.log(d["uacr"].where(d["uacr"] > 0))

    # Pulse pressure: stiffness of the large arteries, and not a linear function
    # of the two pressures a linear model already has -- it is their difference,
    # which a model in systolic and diastolic can represent, so it is here to be
    # tested rather than assumed to add anything.
    d["pulse_pressure"] = (pd.to_numeric(d["systolic_bp"], errors="coerce")
                           - pd.to_numeric(d["diastolic_bp"], errors="coerce"))
    return d


def calibration_effect(cohort: pd.DataFrame) -> pd.DataFrame:
    """Per-cycle creatinine before and after correction, for the report.

    The point of the table is not the size of either column but the shape of
    the difference between them: the two corrected cycles sit on opposite sides
    of the train/test split, so the uncorrected series carries a step there that
    no population change produced.
    """
    d = derive(cohort)
    rows = []
    for cycle, block in d.groupby("cycle", sort=True):
        raw = pd.to_numeric(block["creatinine"], errors="coerce").dropna()
        std = block.loc[raw.index, "creatinine_std"]
        rows.append({
            "cycle": cycle,
            "n": int(len(raw)),
            "mean_as_loaded": round(float(raw.mean()), 4),
            "mean_calibrated": round(float(std.mean()), 4),
            "corrected": cycle in CREATININE_CALIBRATION,
        })
    return pd.DataFrame(rows)
