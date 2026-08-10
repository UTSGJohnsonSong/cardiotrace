"""Tests for cohort assembly.

Every one of these is a regression test for a defect that actually shipped in
this project. The failure mode is always the same: CDC renames an identifier,
code that assumes one name produces a blank or partial column, and the result
looks like ordinary missing data. Nothing raises; the numbers just move.

    python -m pytest tests/test_cohort.py -q
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import cohort as C  # noqa: E402
from tests.conftest import crosswalk_row  # noqa: E402


# ── _find: only the biennial cycle suffix, never "any underscore" ────────────

@pytest.mark.parametrize("files,stem,expected", [
    (["DEMO.XPT"], "DEMO", "DEMO.XPT"),
    (["DEMO_J.XPT"], "DEMO", "DEMO_J.XPT"),
    # KIQ_U is a module name that contains an underscore; the trailing _U must
    # not be mistaken for a cycle suffix.
    (["KIQ_U_B.XPT"], "KIQ_U", "KIQ_U_B.XPT"),
    (["KIQ.XPT"], "KIQ", "KIQ.XPT"),
    # ...and asking for KIQ_U must NOT silently pick up KIQ.
    (["KIQ.XPT"], "KIQ_U", None),
    # The one that shipped: L13_2_B is the second-exam replicate on a subsample.
    # sorted() puts it before L13_B ('2' < 'B'), so a prefix match would have
    # drawn HDL from the replicate.
    (["L13_B.XPT", "L13_2_B.XPT"], "L13", "L13_B.XPT"),
    (["L13_B.XPT", "L13_2_B.XPT"], "L13_2", "L13_2_B.XPT"),
    # TRIGLY ends in Y but is not a youth module, and BPX must not match BPXO.
    (["TRIGLY_D.XPT"], "TRIGLY", "TRIGLY_D.XPT"),
    (["BPXO_J.XPT"], "BPX", None),
])
def test_find_matches_cycle_suffix_only(fake_raw, files, stem, expected):
    for f in files:
        fake_raw("2001-2002", Path(f).stem, {"SEQN": [1.0]})
    got = C._find("2001-2002", stem)
    assert (got.name if got else None) == expected


# ── crosswalk: units and multipliers must agree ──────────────────────────────

def test_crosswalk_rejects_unit_change_with_unit_multiplier(fake_crosswalk):
    fake_crosswalk([crosswalk_row("triglycerides", "2021-2022", "TRIGLY", "LBDTRSI",
                                  unit="mmol/L", canonical="mg/dL", factor=1.0)])
    with pytest.raises(ValueError, match="to_canonical"):
        C.load_crosswalk()


def test_crosswalk_rejects_same_unit_with_conversion_factor(fake_crosswalk):
    fake_crosswalk([crosswalk_row("hdl_cholesterol", "2005-2006", "HDL", "LBDHDD",
                                  factor=88.57)])
    with pytest.raises(ValueError, match="to_canonical"):
        C.load_crosswalk()


def test_crosswalk_rejects_duplicate_key(fake_crosswalk):
    row = crosswalk_row("hdl_cholesterol", "2005-2006", "HDL", "LBDHDD")
    fake_crosswalk([row, row])
    with pytest.raises(ValueError, match="duplicate"):
        C.load_crosswalk()


# ── build_cycle: the decode rules ────────────────────────────────────────────

LAB_ANALYTES = ["total_cholesterol", "hdl_cholesterol", "ldl_cholesterol",
                "triglycerides", "hba1c", "fasting_glucose", "creatinine",
                "uric_acid", "urine_albumin", "urine_creatinine"]


def _minimal_cycle(fake_raw, fake_crosswalk, cycle="2005-2006", n=4, **overrides):
    """A cycle with every required module present and benign values."""
    seqn = [float(i) for i in range(1, n + 1)]
    tables = {
        "DEMO": {"SEQN": seqn, "RIDAGEYR": [50.0] * n, "RIAGENDR": [1.0] * n,
                 "RIDRETH1": [3.0] * n, "WTMEC2YR": [1000.0] * n,
                 "SDMVPSU": [1.0] * n, "SDMVSTRA": [10.0] * n},
        "MCQ": {"SEQN": seqn, **{c: [2.0] * n for c in C.CVD_ITEMS}},
        "BPX": {"SEQN": seqn, "BPXSY1": [130.0] * n, "BPXSY2": [120.0] * n,
                "BPXSY3": [120.0] * n, "BPXDI1": [80.0] * n,
                "BPXDI2": [80.0] * n, "BPXDI3": [80.0] * n},
        "BPQ": {"SEQN": seqn, "BPQ020": [2.0] * n, "BPQ040A": [np.nan] * n,
                "BPQ050A": [np.nan] * n},
        "SMQ": {"SEQN": seqn, "SMQ020": [2.0] * n, "SMQ040": [np.nan] * n},
    }
    for name, cols in overrides.items():
        tables[name] = {"SEQN": seqn, **cols}
    for name, cols in tables.items():
        fake_raw(cycle, name, cols)
    # A one-column lab file per analyte keeps the crosswalk satisfiable.
    rows = []
    for a in LAB_ANALYTES:
        fake_raw(cycle, f"LAB{a[:3].upper()}", {"SEQN": seqn, "LBXX": [1.0] * n})
        rows.append(crosswalk_row(a, cycle, f"LAB{a[:3].upper()}", "LBXX"))
    fake_crosswalk(rows)
    return cycle


def test_race_code_5_is_other_not_missing(fake_raw, fake_crosswalk):
    """RIDRETH1 uses 5 for Other/Multi-Racial; omitting it nulled 2.8% of the cohort."""
    cyc = _minimal_cycle(fake_raw, fake_crosswalk,
                         DEMO={"RIDAGEYR": [50.0] * 4, "RIAGENDR": [1.0] * 4,
                               "RIDRETH1": [1.0, 3.0, 4.0, 5.0],
                               "WTMEC2YR": [1000.0] * 4, "SDMVPSU": [1.0] * 4,
                               "SDMVSTRA": [10.0] * 4})
    out = C.build_cycle(cyc, C.load_crosswalk())
    assert out.race_eth.notna().all()
    assert out.race_eth.iloc[3] == "Other/Multi"


def test_unknown_race_does_not_become_not_black(fake_raw, fake_crosswalk):
    cyc = _minimal_cycle(fake_raw, fake_crosswalk,
                         DEMO={"RIDAGEYR": [50.0] * 4, "RIAGENDR": [1.0] * 4,
                               "RIDRETH1": [4.0, np.nan, 3.0, 3.0],
                               "WTMEC2YR": [1000.0] * 4, "SDMVPSU": [1.0] * 4,
                               "SDMVSTRA": [10.0] * 4})
    out = C.build_cycle(cyc, C.load_crosswalk()).sort_values("SEQN")
    assert out.race_black.iloc[0] == 1.0
    assert pd.isna(out.race_black.iloc[1]), "NaN race must not be coded as 'not Black'"


@pytest.mark.parametrize("bpq020,bpq040a,bpq050a,expected", [
    (2.0, np.nan, np.nan, 0.0),   # never told -> untreated (skip branch 1)
    (1.0, 1.0, 1.0, 1.0),         # told, prescribed, taking
    (1.0, 1.0, 2.0, 0.0),         # told, prescribed, not taking
    (1.0, 2.0, np.nan, 0.0),      # told, never prescribed -> untreated (branch 2)
    (7.0, np.nan, np.nan, None),  # refused -> genuinely missing
    (9.0, np.nan, np.nan, None),
])
def test_bp_treatment_skip_pattern(fake_raw, fake_crosswalk, bpq020, bpq040a, bpq050a, expected):
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=1,
                         BPQ={"BPQ020": [bpq020], "BPQ040A": [bpq040a],
                              "BPQ050A": [bpq050a]})
    got = C.build_cycle(cyc, C.load_crosswalk()).bp_treated.iloc[0]
    assert pd.isna(got) if expected is None else got == expected


@pytest.mark.parametrize("smq020,smq040,expected", [
    (2.0, np.nan, "never"),
    (1.0, 1.0, "current"),
    (1.0, 2.0, "current"),
    (1.0, 3.0, "former"),
    # The one that shipped: isin([1,2]) made a refusal look like "not current",
    # so a refuser was filed as a former smoker.
    (1.0, 7.0, None),
    (1.0, np.nan, None),
    (7.0, np.nan, None),
])
def test_smoking_three_categories(fake_raw, fake_crosswalk, smq020, smq040, expected):
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=1,
                         SMQ={"SMQ020": [smq020], "SMQ040": [smq040]})
    got = C.build_cycle(cyc, C.load_crosswalk()).smoking.iloc[0]
    assert pd.isna(got) if expected is None else got == expected


def test_blood_pressure_falls_back_per_participant_not_per_column(fake_raw, fake_crosswalk):
    """Reading 1 runs high, so 2+3 are preferred — but a participant whose exam
    stopped after reading 1 must keep it. Judging on column presence instead of
    per row dropped 369 cohort members, 47 of them CVD deaths."""
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=2,
                         BPX={"BPXSY1": [140.0, 150.0], "BPXSY2": [120.0, np.nan],
                              "BPXSY3": [122.0, np.nan], "BPXDI1": [80.0, 82.0],
                              "BPXDI2": [78.0, np.nan], "BPXDI3": [78.0, np.nan]})
    out = C.build_cycle(cyc, C.load_crosswalk()).sort_values("SEQN")
    assert out.systolic_bp.iloc[0] == pytest.approx(121.0)   # mean(120, 122)
    assert out.systolic_bp.iloc[1] == pytest.approx(150.0)   # falls back to reading 1


def test_diastolic_zero_is_no_sound_heard_not_a_measurement(fake_raw, fake_crosswalk):
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=1,
                         BPX={"BPXSY1": [130.0], "BPXSY2": [120.0], "BPXSY3": [120.0],
                              "BPXDI1": [80.0], "BPXDI2": [0.0], "BPXDI3": [76.0]})
    out = C.build_cycle(cyc, C.load_crosswalk())
    assert out.diastolic_bp.iloc[0] == pytest.approx(76.0)


def test_kidney_module_rename_is_followed(fake_raw, fake_crosswalk):
    """KIQ/KIQ020 in 1999-2000, KIQ_U/KIQ022 from 2001-2002 — same question."""
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=2)
    fake_raw(cyc, "KIQ", {"SEQN": [1.0, 2.0], "KIQ020": [1.0, 2.0]})
    out = C.build_cycle(cyc, C.load_crosswalk()).sort_values("SEQN")
    assert list(out.kidney_dx) == [1.0, 0.0]


def test_missing_cvd_item_raises_rather_than_admitting_stroke_survivors(fake_raw, fake_crosswalk):
    """prev_cvd is the exclusion criterion. Computing it from whichever MCQ160
    columns happened to load would quietly admit stroke survivors (MCQ160F)."""
    cyc = _minimal_cycle(fake_raw, fake_crosswalk, n=2)
    fake_raw(cyc, "MCQ", {"SEQN": [1.0, 2.0], "MCQ160B": [2.0, 2.0],
                          "MCQ160C": [2.0, 2.0], "MCQ160D": [2.0, 2.0],
                          "MCQ160E": [2.0, 2.0]})     # MCQ160F (stroke) renamed away
    with pytest.raises(KeyError, match="MCQ160F"):
        C.build_cycle(cyc, C.load_crosswalk())


def test_missing_demo_raises(fake_raw, fake_crosswalk):
    cyc = _minimal_cycle(fake_raw, fake_crosswalk)
    (fake_raw.root / cyc / "DEMO.XPT").unlink()
    with pytest.raises(FileNotFoundError, match="DEMO"):
        C.build_cycle(cyc, C.load_crosswalk())


# ── check_cycle_coverage: all three failure shapes ───────────────────────────

def _frame(**cols):
    return pd.DataFrame({"cycle": ["A"] * 3 + ["B"] * 3, **cols})


def test_coverage_flags_variable_blank_in_one_cycle():
    df = _frame(bmi=[20.0, 21.0, 22.0, np.nan, np.nan, np.nan])
    out = C.check_cycle_coverage(df)
    row = out[out.variable == "bmi"].iloc[0]
    assert row.gap_kind == "some_empty" and row.empty_cycles == "B"


def test_coverage_flags_variable_blank_in_every_cycle():
    """The earlier version excluded this case with `len(empty) < nunique` — the
    most catastrophic shape was the one it refused to print."""
    df = _frame(bmi=[np.nan] * 6)
    out = C.check_cycle_coverage(df)
    assert out[out.variable == "bmi"].iloc[0].gap_kind == "all_empty"


def test_coverage_flags_column_that_was_never_created():
    """A merge that never fired leaves no column, so iterating over df.columns
    cannot see it. This is the shape of a series-wide rename."""
    df = _frame(bmi=[20.0] * 6)
    out = C.check_cycle_coverage(df)
    assert "systolic_bp" in set(out[out.gap_kind == "absent"].variable)


def test_assert_cycle_coverage_raises_on_undeclared_gap():
    df = _frame(**{c: [1.0] * 6 for c in C.EXPECTED_COLUMNS})
    df["bmi"] = [1.0, 1.0, 1.0, np.nan, np.nan, np.nan]
    with pytest.raises(ValueError, match="bmi"):
        C.assert_cycle_coverage(df)


def test_assert_cycle_coverage_allows_declared_gap():
    df = _frame(**{c: [1.0] * 6 for c in C.EXPECTED_COLUMNS})
    col, cycles = next(iter(C.KNOWN_EMPTY.items()))
    df = pd.DataFrame({"cycle": sorted(cycles) + ["2013-2014"],
                       **{c: [1.0] * (len(cycles) + 1) for c in C.EXPECTED_COLUMNS}})
    df.loc[df.cycle.isin(cycles), col] = np.nan
    C.assert_cycle_coverage(df)          # must not raise
