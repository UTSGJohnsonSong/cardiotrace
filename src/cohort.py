"""
Part 3 cohort assembly: primary-prevention cohort with mortality linkage.

    NHANES 1999-2014 (8 cycles), adults 40-79, no self-reported CVD at baseline,
    linked to the National Death Index through 2019-12-31.

DESIGN DECISIONS ENCODED HERE
-----------------------------
Harmonisation lives in Python, not in SQL. CDC renames both files and columns
across the series (HDL is LBDHDL -> LBXHDD -> LBDHDD; creatinine is LBDSCR in
2001-2002 only; 2021-2022 publishes triglycerides in mmol/L). Selecting a
different column per cycle is awkward in SQL and untestable without a database,
so this module reads data/catalog/variable_crosswalk.csv and emits one tidy
person-level frame. dbt keeps the modelling and aggregation it is good at.

Consequence: this runs with no database, which makes iteration fast.

Cycle range stops at 2013-2014 for two reasons, both measured rather than
assumed (see docs/research-design.md 3.2):
  - UCOD_LEADING collapses codes 3-9 into "other" from 2015 on, so
    cerebrovascular deaths become invisible and the outcome definition would
    silently change mid-series.
  - 2015-2018 contributes only ~4% of events anyway (median follow-up 3.0y).

One bonus of that range: every cycle in it uses the manual sphygmomanometer.
The oscillometric switch (BPXO) starts in 2017-2018, so Part 3 needs no
instrument bridging at all — that problem belongs to Part 2.
"""

import csv
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
MORT = ROOT / "data" / "raw_mortality"
CROSSWALK = ROOT / "data" / "catalog" / "variable_crosswalk.csv"
MORT_RELEASE = "2019"

CYCLES = ["1999-2000", "2001-2002", "2003-2004", "2005-2006",
          "2007-2008", "2009-2010", "2011-2012", "2013-2014"]

MORT_COLSPECS = [(0, 6), (14, 15), (15, 16), (16, 19), (19, 20), (20, 21), (42, 45), (45, 48)]
MORT_NAMES = ["seqn", "eligstat", "mortstat", "ucod_leading",
              "diabetes_on_dc", "hypertension_on_dc", "permth_int", "permth_exm"]

AGE_MIN, AGE_MAX = 40, 79          # PCE applicability range
CVD_UCOD = {1, 5}                  # diseases of heart + cerebrovascular
# The five self-reported conditions that define baseline CVD. All five are
# required: MCQ160F is stroke, and losing it silently admits stroke survivors.
CVD_ITEMS = ["MCQ160B", "MCQ160C", "MCQ160D", "MCQ160E", "MCQ160F"]


# ── file access ──────────────────────────────────────────────────────────────

CYCLE_SUFFIX = re.compile(r"_[A-L]$")


def _find(cycle: str, stem: str) -> Path | None:
    """The file in `cycle` for `stem`, matching ONLY the biennial cycle suffix.

    The suffix is a single letter _B.._L appended by CDC; it is not "any
    underscore". An earlier `s.startswith(stem + "_")` matched far too much:
    `_find(c, "L13")` also matched `L13_2_B.XPT`, the second-exam replicate run
    on a subsample, and `sorted()` puts `L13_2_B` before `L13_B` because '2' < 'B'
    — so HDL would have been drawn from the replicate rather than the main exam,
    silently, for that cycle. Anchoring the pattern makes the two distinct stems
    they actually are.
    """
    for p in sorted((RAW / cycle).glob("*.XPT")):
        s = p.stem.upper()
        if s == stem or (CYCLE_SUFFIX.sub("", s) == stem and s != stem):
            return p
    return None


def _find_any(cycle: str, stems: list[str]) -> tuple[str, Path] | tuple[None, None]:
    """First stem in `stems` that resolves. CDC also renames whole modules:
    kidney is KIQ in 1999-2000 and KIQ_U from 2001-2002 on."""
    for stem in stems:
        p = _find(cycle, stem)
        if p is not None:
            return stem, p
    return None, None


def _read(cycle: str, stem: str | list[str], cols: list[str]) -> pd.DataFrame | None:
    """Read SEQN plus whichever of `cols` the file actually has.

    `stem` may be a list, tried in order, for modules CDC renamed outright.
    """
    path = _find(cycle, stem) if isinstance(stem, str) else _find_any(cycle, stem)[1]
    if path is None:
        return None
    _, meta = pyreadstat.read_xport(str(path), encoding="LATIN1", metadataonly=True)
    have = {c.upper() for c in meta.column_names}
    want = [c for c in ["SEQN"] + cols if c in have]
    if "SEQN" not in want:
        return None
    d, _ = pyreadstat.read_xport(str(path), encoding="LATIN1", usecols=want)
    d.columns = [c.upper() for c in d.columns]
    return d


def _read_required(cycle: str, stem: str, cols: list[str]) -> pd.DataFrame:
    """Same as _read, for modules whose absence must stop the run.

    `_read` returning None means "carry on without this variable", which is the
    right default for an optional questionnaire but catastrophic for the
    demographics file that supplies age, sex and the survey weights. Splitting
    the two puts the distinction in the call site instead of relying on whoever
    edits next to remember a None check.
    """
    d = _read(cycle, stem, cols)
    if d is None:
        raise FileNotFoundError(
            f"required module {stem} not found for cycle {cycle} in {RAW / cycle}")
    missing = [c for c in cols if c not in d.columns]
    if missing:
        raise KeyError(f"{stem} in {cycle} is missing required columns {missing}")
    return d


def load_crosswalk() -> dict[tuple[str, str], tuple[str, str, float]]:
    """(analyte, cycle) -> (source module stem, column name, unit multiplier).

    The CSV also carries `unit` and `canonical_unit`. They are checked here and
    then dropped: a row whose units differ must have a multiplier != 1, and a row
    whose units match must have exactly 1. Getting that backwards is silent and
    large — the one real conversion in the table is triglycerides mmol/L -> mg/dL
    at x88.57, so a stray 1.0 would put that column off by two orders of
    magnitude with no error anywhere.
    """
    out: dict[tuple[str, str], tuple[str, str, float]] = {}
    with open(CROSSWALK, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            factor = float(r["to_canonical"])
            same_unit = r["unit"] == r["canonical_unit"]
            if same_unit != (factor == 1.0):
                raise ValueError(
                    f"{r['analyte']}/{r['cycle']}: unit {r['unit']!r} -> "
                    f"{r['canonical_unit']!r} but to_canonical={factor}")
            key = (r["analyte"], r["cycle"])
            if key in out:
                raise ValueError(f"duplicate crosswalk row for {key}")
            out[key] = (r["source_module"], r["variable"], factor)
    return out


# ── per-cycle assembly ───────────────────────────────────────────────────────

def build_cycle(cycle: str, xw: dict) -> pd.DataFrame:
    # DEMO carries age, sex and the survey design variables — nothing downstream
    # is meaningful without it, so this one must raise rather than return None.
    # RIDRETH3 is deliberately not required: it only exists from 2011 on.
    d = _read_required(cycle, "DEMO",
                       ["RIDAGEYR", "RIAGENDR", "RIDRETH1", "WTMEC2YR", "SDMVPSU", "SDMVSTRA"])
    optional = _read(cycle, "DEMO", ["RIDRETH3", "DMDEDUC2", "INDFMPIR"])
    if optional is not None:
        d = d.merge(optional, on="SEQN", how="left", validate="1:1")
    df = d.rename(columns={
        "RIDAGEYR": "age", "WTMEC2YR": "wtmec2yr", "SDMVPSU": "psu", "SDMVSTRA": "strata",
        "INDFMPIR": "pir",
    })
    df["sex"] = df["RIAGENDR"].map({1: "Male", 2: "Female"})
    # RIDRETH3 splits out Non-Hispanic Asian from 2011 on; fall back where absent.
    eth = df["RIDRETH3"] if "RIDRETH3" in df.columns else df["RIDRETH1"]
    # RIDRETH1 uses 5 for "Other Race - Including Multi-Racial"; RIDRETH3 uses 7
    # and adds 6 for Non-Hispanic Asian. Omitting 5 silently nulls ~2.8% of the
    # cohort — the pre-2011 multiracial respondents.
    df["race_eth"] = eth.map({1: "Mexican American", 2: "Other Hispanic",
                              3: "NH White", 4: "NH Black", 5: "Other/Multi",
                              6: "NH Asian", 7: "Other/Multi"})
    # `.astype(float)` on a comparison turns NaN into 0.0 — an unknown race would
    # silently become "not Black". `.where(eth.notna())` puts the missing back.
    df["race_black"] = (eth == 4).astype("float").where(eth.notna())
    # 7 = refused, 9 = don't know -> missing, not a category.
    # DMDEDUC2 and INDFMPIR come from the optional read, so they may be absent.
    # Reaching for them unconditionally raised KeyError — invisible on real data
    # where they always exist, which is exactly why it needed a test.
    df["education"] = (df["DMDEDUC2"].where(~df["DMDEDUC2"].isin([7, 9]))
                       if "DMDEDUC2" in df.columns else np.nan)
    # NHANES top-codes the poverty-income ratio at 5.
    df["pir"] = df["pir"].clip(upper=5) if "pir" in df.columns else np.nan

    # Blood pressure: drop reading 1. The first cuff reading runs high (white-coat
    # effect); NHANES/AHA practice averages the later readings.
    bp = _read(cycle, "BPX", ["BPXSY1", "BPXSY2", "BPXSY3", "BPXDI1", "BPXDI2", "BPXDI3"])
    if bp is not None:
        for out, pre in [("systolic_bp", "BPXSY"), ("diastolic_bp", "BPXDI")]:
            # sorted(), not source order: dropping got[1:] assumes the readings
            # arrive numbered. If pyreadstat ever returned BPXSY2 before BPXSY1
            # we would discard reading 2 and KEEP reading 1 — the white-coat
            # reading we are specifically trying to exclude — biasing every
            # blood pressure upward with no error.
            got = sorted(c for c in bp.columns if c.startswith(pre))
            if not got:
                continue
            # Diastolic 0 is a documented NHANES code for "no sound heard".
            vals = bp[got].astype("float")
            if pre == "BPXDI":
                vals = vals.replace(0.0, np.nan)
            # Prefer readings 2+ (reading 1 runs high — white-coat effect), but
            # fall back PER PARTICIPANT, not per column. Every cycle ships all
            # three columns, so a column-level fallback never fires: a person
            # whose exam stopped after reading 1 got mean([NaN, NaN]) = NaN.
            # That silently dropped 369 cohort members who DO have a reading,
            # including 47 CVD deaths — and they are not a random subset, their
            # mean reading-1 SBP is 133.2 against a cohort mean of 127.4, because
            # a curtailed exam correlates with being sicker.
            later = vals[got[1:]].mean(axis=1) if len(got) > 1 else pd.Series(np.nan, index=vals.index)
            bp[out] = later.fillna(vals[got[0]])
        keep = ["SEQN"] + [c for c in ("systolic_bp", "diastolic_bp") if c in bp.columns]
        df = df.merge(bp[keep], on="SEQN", how="left", validate="1:1")

    bm = _read(cycle, "BMX", ["BMXBMI", "BMXWAIST"])
    if bm is not None:
        df = df.merge(bm.rename(columns={"BMXBMI": "bmi", "BMXWAIST": "waist_cm"}),
                      on="SEQN", how="left", validate="1:1")

    # Hypertension questionnaire. BPQ050A ("now taking prescribed medicine") is
    # only asked of respondents who said yes to BPQ020 ("ever told high blood
    # pressure"); everyone else skips it. 94% of its nulls are BPQ020=2. That is
    # a skip pattern, not missing data — decode it to 0 rather than dropping the
    # person. Doing so takes this column from 65.3% to 5.4% missing.
    bpq = _read(cycle, "BPQ", ["BPQ020", "BPQ040A", "BPQ050A"])
    if bpq is not None:
        bpq["htn_diagnosed"] = bpq["BPQ020"].map({1: 1.0, 2: 0.0})
        col = "BPQ050A" if "BPQ050A" in bpq.columns else "BPQ040A"
        bpq["bp_treated"] = bpq[col].map({1: 1.0, 2: 0.0})
        # The skip runs BPQ020 -> BPQ040A -> BPQ050A, so there are TWO branches
        # that leave BPQ050A blank while the answer is unambiguously "untreated":
        #   BPQ020 = 2  never told they had high blood pressure
        #   BPQ040A = 2 told, but never prescribed medication
        # Decoding only the first left 1,061 of the remaining 1,129 nulls (94%)
        # on the table — the same skip pattern one question deeper. Handling both
        # takes this column from 5.4% to ~0.3% missing.
        untreated = (bpq["BPQ020"] == 2)
        if "BPQ040A" in bpq.columns:
            untreated |= (bpq["BPQ020"] == 1) & (bpq["BPQ040A"] == 2)
        bpq.loc[untreated & bpq["bp_treated"].isna(), "bp_treated"] = 0.0
        df = df.merge(bpq[["SEQN", "htn_diagnosed", "bp_treated"]], on="SEQN", how="left", validate="1:1")

    diq = _read(cycle, "DIQ", ["DIQ010", "DIQ050"])
    if diq is not None:
        # 3 = "borderline". Coded 0 here; sensitivity analysis flips it (see
        # docs/methodology-review.md 8.4).
        diq["diabetes_dx"] = diq["DIQ010"].map({1: 1.0, 2: 0.0, 3: 0.0})
        if "DIQ050" in diq.columns:
            diq["on_insulin"] = diq["DIQ050"].map({1: 1.0, 2: 0.0})
            diq.loc[(diq["diabetes_dx"] == 0) & diq["on_insulin"].isna(), "on_insulin"] = 0.0
        df = df.merge(diq[[c for c in ("SEQN", "diabetes_dx", "on_insulin") if c in diq.columns]],
                      on="SEQN", how="left", validate="1:1")

    # Smoking as three categories. Collapsing former into never (as the previous
    # pipeline did) discards an independent risk factor and dilutes the estimate.
    smq = _read(cycle, "SMQ", ["SMQ020", "SMQ040"])
    if smq is not None:
        ever = smq["SMQ020"].map({1: True, 2: False})
        # .map, not .isin: `SMQ040.isin([1, 2])` returns False for code 7
        # (refused) and for NaN, so a respondent who declined to answer gets
        # ever=True & ~now and is filed as a FORMER smoker. Mapping leaves
        # 7/9/NaN as missing so they propagate instead of being invented.
        now = (smq["SMQ040"].map({1: True, 2: True, 3: False})
               if "SMQ040" in smq.columns else pd.Series(np.nan, index=smq.index))
        # dtype=object, not a bare np.nan: `smq["smoking"] = np.nan` creates a
        # float64 column and assigning "never" into it raises TypeError on
        # pandas 3.x. The np.nan-over-pd.NA convention is about which missing
        # SENTINEL to use; it does not license letting pandas infer a numeric
        # dtype for a column that holds strings.
        smq["smoking"] = pd.Series(np.nan, index=smq.index, dtype=object)
        smq.loc[ever == False, "smoking"] = "never"
        smq.loc[(ever == True) & (now == False), "smoking"] = "former"
        smq.loc[(ever == True) & (now == True), "smoking"] = "current"
        smq["current_smoker"] = smq["smoking"].map({"never": 0.0, "former": 0.0, "current": 1.0})
        df = df.merge(smq[["SEQN", "smoking", "current_smoker"]], on="SEQN", how="left", validate="1:1")

    # Baseline CVD: the previous project's OUTCOME becomes this project's
    # EXCLUSION criterion. 7/9 (refused / don't know) are missing, not "no".
    # Required, not optional: prev_cvd is the EXCLUSION criterion for the whole
    # primary-prevention design. Computing it from "whichever MCQ160 columns
    # happened to load" means a single rename — MCQ160F is stroke — quietly
    # admits stroke survivors to the cohort as healthy subjects. That inflates
    # the CVD death rate and no coverage check can see it, because the column
    # comes out fully populated and merely wrong.
    mcq = _read_required(cycle, "MCQ", CVD_ITEMS)
    valid = mcq[CVD_ITEMS].isin([1, 2])
    mcq["prev_cvd"] = (mcq[CVD_ITEMS] == 1).any(axis=1).astype("float")
    mcq.loc[~valid.any(axis=1), "prev_cvd"] = np.nan
    df = df.merge(mcq[["SEQN", "prev_cvd"]], on="SEQN", how="left", validate="1:1")

    # Questionnaire variables drift too, the same way filenames and lab columns
    # do: health insurance is HID010 through 2003-2004 and HIQ011 from 2005 on.
    # Reading only the newer name silently blanks three whole cycles. Candidates
    # are listed oldest-first and the first one present wins.
    # (module stem, column) pairs, oldest naming first. CDC renames the MODULE
    # and the COLUMN independently, so a single stem with a list of columns is
    # not enough: kidney is KIQ/KIQ020 in 1999-2000 and KIQ_U/KIQ022 from
    # 2001-2002, both labelled "Ever told you had weak/failing kidneys". Treating
    # that as a real absence and allowlisting it is how a rename gets laundered
    # into an accepted gap.
    #
    # vigorous_work is named for 2007+ deliberately. PAD200 in 1999-2006 asks
    # about ANY vigorous activity, PAQ605 about vigorous WORK activity — a
    # different construct, not a rename. Rather than silently pool them or leave
    # a column that looks 43% missing, the name declares its own coverage.
    for pairs, out, kind in [
        ([("ALQ", "ALQ130")], "drinks_per_day", "count"),
        ([("HIQ", "HID010"), ("HIQ", "HIQ011")], "insured", "yesno"),
        ([("KIQ", "KIQ020"), ("KIQ_U", "KIQ022")], "kidney_dx", "yesno"),
        ([("PAQ", "PAQ605")], "vigorous_work_2007plus", "yesno"),
    ]:
        for stem, col in pairs:
            t = _read(cycle, stem, [col])
            if t is not None and col in t.columns:
                t[out] = (t[col].map({1: 1.0, 2: 0.0}) if kind == "yesno"
                          else t[col].where(t[col] < 777))
                df = df.merge(t[["SEQN", out]], on="SEQN", how="left", validate="1:1")
                break

    for analyte in ["total_cholesterol", "hdl_cholesterol", "ldl_cholesterol",
                    "triglycerides", "hba1c", "fasting_glucose", "creatinine",
                    "uric_acid", "urine_albumin", "urine_creatinine"]:
        mod, var, factor = xw[(analyte, cycle)]
        lab = _read(cycle, mod, [var])
        if lab is not None and var in lab.columns:
            lab[analyte] = lab[var] * factor
            df = df.merge(lab[["SEQN", analyte]], on="SEQN", how="left", validate="1:1")

    df["cycle"] = cycle
    return df.drop(columns=[c for c in df.columns if c.isupper() and c != "SEQN"])


def load_mortality() -> pd.DataFrame:
    frames = []
    for cycle in CYCLES:
        tag = cycle.replace("-", "_")
        d = pd.read_fwf(MORT / f"NHANES_{tag}_MORT_{MORT_RELEASE}_PUBLIC.dat",
                        colspecs=MORT_COLSPECS, names=MORT_NAMES, dtype=str)
        for c in MORT_NAMES:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        frames.append(d)
    m = pd.concat(frames, ignore_index=True).rename(columns={"seqn": "SEQN"})
    # MORTSTAT is blank for anyone not eligible for linkage. `(mortstat == 1)`
    # is False for those rows, so `.astype(float)` would stamp them 0.0 —
    # indistinguishable from a confirmed survivor and biasing incidence down.
    # Keep them NaN; the cohort filter drops them a few lines later, and
    # make_event_code() raises if any survive that far.
    # MORT_COLSPECS are hardcoded byte offsets and the parse uses
    # errors="coerce", so an NCHS layout change turns the OUTCOME variable into
    # NaN with no error at all: cvd_death would collapse toward zero while every
    # other column still looked plausible. Assert the domains instead.
    if m.SEQN.isna().any():
        raise ValueError(f"{int(m.SEQN.isna().sum())} mortality rows have an unparseable "
                         "SEQN — the fixed-width layout has probably shifted")
    for col, allowed in [("eligstat", {1, 2, 3}), ("mortstat", {0, 1}),
                         ("ucod_leading", set(range(1, 11)))]:
        seen = set(m[col].dropna().unique()) - allowed
        if seen:
            raise ValueError(f"{col} has out-of-domain values {sorted(seen)}; expected {sorted(allowed)}")
    if m.SEQN.duplicated().any():
        raise ValueError(f"{int(m.SEQN.duplicated().sum())} duplicate SEQN in the mortality files")

    known = m.mortstat.notna()
    # A decedent whose cause was not coded is NOT a competing death — `~isin` is
    # True for NaN, which would post them to the competing arm on no evidence.
    # Two records today; wrong in principle regardless of count.
    cause_known = m.ucod_leading.notna() | (m.mortstat == 0)
    m["cvd_death"] = ((m.mortstat == 1) & m.ucod_leading.isin(CVD_UCOD)
                      ).astype("float").where(known & cause_known)
    m["competing_death"] = ((m.mortstat == 1) & m.ucod_leading.notna()
                            & ~m.ucod_leading.isin(CVD_UCOD)
                            ).astype("float").where(known & cause_known)
    m["followup_years"] = m.permth_exm / 12.0
    return m


# ── cohort with STROBE accounting ────────────────────────────────────────────

def build_cohort() -> tuple[pd.DataFrame, pd.DataFrame]:
    xw = load_crosswalk()
    df = pd.concat([build_cycle(c, xw) for c in CYCLES], ignore_index=True)
    # Run the guard here, before any filtering, so a rename cannot hide behind an
    # exclusion. Wiring it in is the point: an earlier version of this check
    # existed but had no caller, which is the same as not having it.
    assert_cycle_coverage(df)
    mort = load_mortality()

    steps: list[tuple[str, pd.DataFrame]] = [("NHANES 1999-2014 respondents", df)]

    df = df.merge(mort, on="SEQN", how="left", validate="1:1")
    steps.append(("Merged with the linked mortality file", df))

    df = df[df.eligstat == 1]
    steps.append(("Eligible for linkage (ELIGSTAT = 1)", df))

    df = df[df.permth_exm.notna()]
    steps.append(("Completed the MEC examination", df))

    df = df[df.age.between(AGE_MIN, AGE_MAX)]
    steps.append((f"Aged {AGE_MIN}-{AGE_MAX}", df))

    df = df[df.wtmec2yr.fillna(0) > 0]
    steps.append(("Non-zero examination weight", df))

    df = df[df.prev_cvd.notna()]
    steps.append(("Baseline CVD status known", df))

    df = df[df.prev_cvd == 0]
    steps.append(("Free of self-reported CVD at baseline", df))

    # A decedent whose underlying cause was never coded cannot be assigned to
    # either arm. Excluding them is a STROBE row, not a silent recode — folding
    # them into "competing" or "censored" would bias the CIF with no trace.
    df = df[df.cvd_death.notna() & df.competing_death.notna()]
    steps.append(("Cause of death coded for every decedent", df))

    n0 = len(steps[0][1])
    prev = n0
    rows = []
    for label, d in steps:
        rows.append({"step": label, "n": len(d), "excluded": prev - len(d),
                     "pct_of_start": round(100 * len(d) / n0, 1),
                     "cvd_deaths": int(d.cvd_death.sum()) if "cvd_death" in d else None})
        prev = len(d)
    return df.reset_index(drop=True), pd.DataFrame(rows)


# Every column build_cycle() is supposed to produce. Declared, not inferred: a
# variable whose merge never fired leaves NO column behind, so a check that
# iterates over df.columns cannot see it. That is exactly the shape of a
# series-wide rename like HID010 -> HIQ011.
EXPECTED_COLUMNS = {
    "wtmec2yr", "psu", "strata", "age", "sex", "race_eth", "race_black",
    "education", "pir", "systolic_bp", "diastolic_bp", "bmi", "waist_cm",
    "htn_diagnosed", "bp_treated", "diabetes_dx", "on_insulin", "smoking",
    "current_smoker", "prev_cvd", "drinks_per_day", "insured", "kidney_dx",
    "vigorous_work_2007plus", "total_cholesterol", "hdl_cholesterol", "ldl_cholesterol",
    "triglycerides", "hba1c", "fasting_glucose", "creatinine", "uric_acid",
    "urine_albumin", "urine_creatinine",
}

# Cycle-level gaps that are real, verified absences rather than renames. Anything
# NOT listed here that comes back empty for a whole cycle is treated as a defect.
KNOWN_EMPTY: dict[str, set[str]] = {
    # PAQ605 (vigorous WORK activity) starts in 2007-2008. The pre-2007 PAD200
    # asks about ANY vigorous activity — a different construct, not a rename, so
    # it is a real gap. The column name carries the restriction.
    "vigorous_work_2007plus": {"1999-2000", "2001-2002", "2003-2004", "2005-2006"},
}


def check_cycle_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Report variables that are missing or wholly empty for entire cycles.

    Four separate bugs in this project came from one root cause: CDC renames
    identifiers across the series, and code that assumes a single name silently
    blanks whole cycles. Filenames (LAB13 -> L13 -> TCHOL), lab columns (LBDHDL
    -> LBXHDD -> LBDHDD), questionnaire columns (HID010 -> HIQ011), and a regex
    that read TRIGLY_D as a youth module. None raised; each looked like ordinary
    missingness.

    Three failure shapes, all covered here:
      absent      the column does not exist at all — the merge never fired
      all_empty   present but 100% null in EVERY cycle
      some_empty  100% null in some cycles but not others

    An earlier version reported only the third and iterated over the columns that
    happened to exist, so the two worse shapes — a rename that hit the whole
    series — were invisible to it.
    """
    cycles = set(df.cycle.unique())
    rows = []

    for col in sorted(EXPECTED_COLUMNS - set(df.columns)):
        rows.append({"variable": col, "gap_kind": "absent", "n_cycles_empty": len(cycles),
                     "empty_cycles": "(column never created)", "expected_gap": False})

    for col in sorted(EXPECTED_COLUMNS & set(df.columns)):
        by = df.groupby("cycle")[col].apply(lambda s: s.isna().mean())
        empty = set(by[by >= 0.999].index)
        if not empty:
            continue
        gap_kind = "all_empty" if empty == cycles else "some_empty"
        rows.append({"variable": col, "gap_kind": gap_kind, "n_cycles_empty": len(empty),
                     "empty_cycles": ", ".join(sorted(empty)),
                     "expected_gap": empty <= KNOWN_EMPTY.get(col, set())})

    if not rows:
        return pd.DataFrame(columns=["variable", "gap_kind", "n_cycles_empty",
                                     "empty_cycles", "expected_gap"])
    return pd.DataFrame(rows).sort_values(["expected_gap", "n_cycles_empty"],
                                          ascending=[True, False])


def assert_cycle_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Raise on any unexplained cycle-wide gap. Returns the full report."""
    report = check_cycle_coverage(df)
    unexpected = report[~report.expected_gap] if len(report) else report
    if len(unexpected):
        detail = "\n".join(
            f"  {r.variable:22s} {r.gap_kind:10s} {r.empty_cycles}"
            for r in unexpected.itertuples())
        raise ValueError(
            "Cycle-wide data gaps that are not declared in KNOWN_EMPTY. These are "
            "almost always a CDC rename, not real absence:\n" + detail)
    return report
