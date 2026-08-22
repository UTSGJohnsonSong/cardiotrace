"""Guard the transcribed ASCVD Pooled Cohort Equations table.

`data/reference/pce_coefficients.csv` was typed in by hand from a PDF, which is
exactly the kind of step that fails silently. Two things make that safe here.

First, the source prints a worked example for all four race-sex groups -- one
profile, four published answers -- so the table can be checked against its own
origin rather than against our belief about it.

Second, the checks are split, because they validate different rows of the file:

    the linear predictor      -> validates the 13 coefficients
    risk from the PRINTED sum -> validates mean_lp and baseline_survival

The second deliberately feeds the source's printed "Individual Sum" instead of
ours. That sum is printed to two decimals and exp() amplifies the rounding: for
white men 60.69 and 60.70 give 5.33% and 5.39%. Feeding our own sum would make
this test fail on the source's rounding rather than on a transcription error.

Source: 2013 ACC/AHA Guideline on the Assessment of Cardiovascular Risk,
Full Work Group Report, Table 4, pp.32-33.
"""

import csv
import math
from pathlib import Path

import pytest

REFERENCE = Path(__file__).parent.parent / "data" / "reference" / "pce_coefficients.csv"

GROUPS = ("white_women", "aa_women", "white_men", "aa_men")

VARIABLES = (
    "ln_age",
    "ln_age_squared",
    "ln_total_cholesterol",
    "ln_age_x_ln_total_cholesterol",
    "ln_hdl_c",
    "ln_age_x_ln_hdl_c",
    "ln_treated_systolic_bp",
    "ln_age_x_ln_treated_systolic_bp",
    "ln_untreated_systolic_bp",
    "ln_age_x_ln_untreated_systolic_bp",
    "current_smoker",
    "ln_age_x_current_smoker",
    "diabetes",
)

# Table 4 prints one profile for every group: 55 years, total cholesterol
# 213 mg/dL, HDL-C 50 mg/dL, untreated systolic BP 120 mm Hg, nonsmoker,
# no diabetes -- and the Individual Sum and 10-year risk it should produce.
PROFILE = dict(age=55, tc=213, hdl=50, sbp=120, smoker=0, diabetes=0, treated=False)

PUBLISHED = {
    "white_women": (-29.67, 2.1),
    "aa_women": (86.16, 3.0),
    "white_men": (60.69, 5.3),
    "aa_men": (18.97, 6.1),
}


@pytest.fixture(scope="module")
def table():
    coef, param = {}, {}
    with REFERENCE.open() as fh:
        for row in csv.DictReader(fh):
            value = None if row["value"] == "NA" else float(row["value"])
            bucket = coef if row["kind"] == "coefficient" else param
            bucket.setdefault(row["group"], {})[row["variable"]] = value
    return coef, param


def design(profile):
    """The 13 model terms for one person, on the scale the coefficients expect."""
    la = math.log(profile["age"])
    ltc = math.log(profile["tc"])
    lhdl = math.log(profile["hdl"])
    lsbp = math.log(profile["sbp"])
    treated = profile["treated"]
    return {
        "ln_age": la,
        "ln_age_squared": la ** 2,
        "ln_total_cholesterol": ltc,
        "ln_age_x_ln_total_cholesterol": la * ltc,
        "ln_hdl_c": lhdl,
        "ln_age_x_ln_hdl_c": la * lhdl,
        "ln_treated_systolic_bp": lsbp if treated else 0.0,
        "ln_age_x_ln_treated_systolic_bp": la * lsbp if treated else 0.0,
        "ln_untreated_systolic_bp": 0.0 if treated else lsbp,
        "ln_age_x_ln_untreated_systolic_bp": 0.0 if treated else la * lsbp,
        "current_smoker": profile["smoker"],
        "ln_age_x_current_smoker": la * profile["smoker"],
        "diabetes": profile["diabetes"],
    }


def test_every_group_declares_every_variable(table):
    """Absent covariates are written NA, never omitted.

    An omitted row and a zero coefficient are not the same claim, and a loader
    that silently tolerates missing rows is how a dropped covariate becomes a
    plausible-looking number instead of a crash.
    """
    coef, _ = table
    assert set(coef) == set(GROUPS)
    for group in GROUPS:
        assert tuple(coef[group]) == VARIABLES, f"{group} variable set drifted"


def test_every_group_has_both_parameters(table):
    _, param = table
    for group in GROUPS:
        assert set(param[group]) == {"mean_linear_predictor", "baseline_survival_10y"}
        assert 0.0 < param[group]["baseline_survival_10y"] < 1.0


@pytest.mark.parametrize("group", GROUPS)
def test_coefficients_reproduce_published_linear_predictor(table, group):
    coef, _ = table
    terms = design(PROFILE)
    total = sum(c * terms[v] for v, c in coef[group].items() if c is not None)
    assert total == pytest.approx(PUBLISHED[group][0], abs=0.02)


@pytest.mark.parametrize("group", GROUPS)
def test_baseline_survival_reproduces_published_risk(table, group):
    _, param = table
    published_sum, published_risk = PUBLISHED[group]
    lp = published_sum - param[group]["mean_linear_predictor"]
    risk = 100 * (1 - param[group]["baseline_survival_10y"] ** math.exp(lp))
    assert risk == pytest.approx(published_risk, abs=0.05)
