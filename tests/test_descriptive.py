"""Regressions for the Part 1 / Part 2 estimators.

These run on constructed frames rather than NHANES files, because the properties
worth pinning are arithmetic ones that a real extract would hide: whether the
standard weights are the published ones, whether standardisation collapses to
the crude estimate when it should, and whether the variance actually uses the
design rather than quietly treating everyone as independent.
"""

import numpy as np
import pandas as pd
import pytest

from src.descriptive import (
    AGE_LABELS, STD_2000, age_standardised_prevalence, crude_prevalence,
    cycle_midpoint, design_effect, srs_variance_standardised,
    _linearised_variance,
)


def frame(rows):
    """rows: (age_group, weight, outcome, strata, psu)"""
    df = pd.DataFrame(rows, columns=["age_group", "weight", "prev_cvd", "strata", "psu"])
    df["age_group"] = pd.Categorical(df["age_group"], categories=AGE_LABELS)
    return df


def test_standard_weights_are_the_published_numbers():
    """The six bands are the 2000 standard aggregated to the NHANES groupings.

    Each is a sum of Master List five-year weights (Klein & Schoenborn, NCHS
    Statistical Notes No. 20, Table 1). The total must reproduce the separately
    published 20+ base -- 195,850 of 274,634 thousand, from Table 2 of the same
    document, Age Distributions #11 and #12. Because that ratio is published
    independently of the twelve constants below, agreement means they were
    transcribed correctly rather than merely summed consistently.

    Every band is asserted individually. Checking only the ends and the total
    left the middle four unconstrained: swapping two of them preserves the sum,
    changes every published standardised number, and passed the whole suite.
    """
    assert set(STD_2000) == set(AGE_LABELS)
    assert STD_2000["20-34"] == pytest.approx(0.066478 + 0.064530 + 0.071044)
    assert STD_2000["35-44"] == pytest.approx(0.080762 + 0.081851)
    assert STD_2000["45-54"] == pytest.approx(0.072118 + 0.062716)
    assert STD_2000["55-64"] == pytest.approx(0.048454 + 0.038793)
    assert STD_2000["65-74"] == pytest.approx(0.034264 + 0.031773)
    assert STD_2000["75+"] == pytest.approx(0.027000 + 0.017842 + 0.015508)
    assert sum(STD_2000.values()) == pytest.approx(195_850 / 274_634, abs=5e-6)


def test_age_floor_is_twenty_not_twenty_five():
    """Regression for a real error: the 25+ floor rested on a false premise.

    The claim was that no published weight splits at 20. The Master List carries
    an explicit 20-24 weight of 0.066478, and NCHS assigns NHANES a 20+ base. If
    someone reinstates a 25+ floor, this test should stop them until they have a
    better reason than the one that was wrong.
    """
    from src.descriptive import AGE_BINS, AGE_MIN_DESC
    assert AGE_MIN_DESC == 20
    assert AGE_BINS[0] == 20
    assert AGE_LABELS[0] == "20-34"


def test_standardised_equals_crude_when_composition_matches_the_standard():
    """With the sample's weighted age composition equal to the standard, direct
    standardisation must be a no-op. If it is not, the renormalisation is wrong."""
    # Prevalence must differ across bands. The earlier version gave every band
    # the same 50/50 split, which makes p_std = 0.5 for ANY normalised weights --
    # uniform, reversed, or one band carrying everything all passed it. The
    # comment claimed to vary the outcome by group; the code did not.
    prevalence = {"20-34": 0.02, "35-44": 0.04, "45-54": 0.08,
                  "55-64": 0.15, "65-74": 0.25, "75+": 0.40}
    rows = []
    for i, g in enumerate(AGE_LABELS):
        w = 1000 * STD_2000[g]
        rows.append((g, w * prevalence[g], 1.0, i, 1))
        rows.append((g, w * (1 - prevalence[g]), 0.0, i, 2))
    df = frame(rows)
    p_std, _ = age_standardised_prevalence(df)
    p_crude, _ = crude_prevalence(df)
    expected = (sum(STD_2000[g] * prevalence[g] for g in AGE_LABELS)
                / sum(STD_2000.values()))
    assert p_std == pytest.approx(p_crude)
    assert p_std == pytest.approx(expected)


def test_standardisation_moves_the_estimate_when_composition_differs():
    """An old-skewed sample with age-rising prevalence must standardise downward."""
    rows = [
        ("20-34", 100.0, 0.0, 0, 1), ("20-34", 100.0, 0.0, 0, 2),
        ("75+",   900.0, 1.0, 1, 1), ("75+",   900.0, 1.0, 1, 2),
    ]
    df = frame(rows)
    p_std, _ = age_standardised_prevalence(df)
    p_crude, _ = crude_prevalence(df)
    # Crude is dominated by the oversampled old group; the standard population
    # gives 20-34 more than three times the share of 75+ (0.2021 vs 0.0604).
    assert p_crude == pytest.approx(0.9)
    expected = STD_2000["75+"] / (STD_2000["20-34"] + STD_2000["75+"])
    assert p_std == pytest.approx(expected)
    assert p_std < p_crude


def test_variance_uses_clusters_not_individuals():
    """Two people in one PSU must not count as two independent observations.

    Splitting the same data across more PSUs changes the variance; if it does
    not, the estimator is ignoring the design and every interval is too narrow.
    """
    same_psu = frame([("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, 1.0, 0, 1),
                      ("45-54", 1.0, 0.0, 0, 2), ("45-54", 1.0, 0.0, 0, 2)])
    split = frame([("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, 1.0, 0, 2),
                   ("45-54", 1.0, 0.0, 0, 3), ("45-54", 1.0, 0.0, 0, 4)])
    _, se_same = age_standardised_prevalence(same_psu)
    _, se_split = age_standardised_prevalence(split)
    assert se_same > se_split > 0


def test_singleton_strata_are_collapsed_rather_than_dropped():
    """A lone PSU has no within-stratum degrees of freedom, so it borrows one.

    This test previously pinned the opposite behaviour -- that such a stratum
    contributes nothing -- and that was the bug. Dropping it removes its
    contribution entirely instead of pooling it, which understates the variance.
    The overall series has no singleton strata, but the race subgroups have 47
    across 44 published subgroup-cycles, and in the worst of them the dropped
    strata held a third of the sample.

    Two singleton strata therefore pool into one pseudo-stratum of two units and
    contribute (u1 - u2)^2, not zero.
    """
    df = frame([("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, 0.0, 1, 1)])
    var = _linearised_variance(df, pd.Series([0.5, -0.5]))
    assert var == pytest.approx(1.0)          # (0.5 - (-0.5))^2


def test_collapsing_never_understates_against_dropping():
    """The remedy has to move the variance up, never down.

    A stratum that contributes one unit to the domain carries information the
    dropped version discards. Pooling is mildly conservative -- it treats
    between-stratum differences as sampling variation -- which is the right
    direction to err in for an interval nobody should read as too tight.
    """
    rows = [("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, 0.0, 0, 2),   # a real stratum
            ("45-54", 1.0, 1.0, 1, 1),                              # singleton
            ("45-54", 1.0, 0.0, 2, 1)]                              # singleton
    df = frame(rows)
    z = pd.Series([0.4, -0.4, 0.6, -0.6])
    pooled = _linearised_variance(df, z)
    intact_only = _linearised_variance(df.iloc[:2], z.iloc[:2])
    assert pooled > intact_only


def test_absent_age_groups_renormalise_rather_than_shrink_the_estimate():
    """A subgroup present in only some age bands must still standardise to 1.

    Without renormalisation over the observed bands, any group missing an age
    band would be biased toward zero by exactly the missing share -- which is
    the kind of error that looks like a real health disparity.
    """
    df = frame([("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, 1.0, 0, 2)])
    p_std, _ = age_standardised_prevalence(df)
    assert p_std == pytest.approx(1.0)


def test_cycle_midpoint_puts_cycles_on_a_real_time_axis():
    """The final cycle is not two years long and is not centred where its key says.

    NCHS names it "NHANES August 2021-August 2023", so its field midpoint is
    August 2022. The project keys on the folder name "2021-2022" because that is
    what the files sit under, and taking 2021.5 from that key understated the
    extrapolation in section 3 by more than a year -- 4.0 instead of 5.1. A rule
    that derives the midpoint from the key is right for every other cycle and
    wrong for this one, which is why there is an override rather than a cleverer
    rule.
    """
    assert cycle_midpoint("1999-2000") == 1999.5
    assert cycle_midpoint("2017-2018") == 2017.5
    assert cycle_midpoint("2021-2022") == 2022.6
    assert cycle_midpoint("2021-2022") - cycle_midpoint("2017-2018") == pytest.approx(5.1)


def test_a_nan_outcome_produces_a_nan_estimate_not_a_confident_zero():
    """Records what actually happens, which is not what the estimator promises.

    The previous version of this test built no NaN at all -- both outcomes were
    0.0 and 1.0 -- and asserted finiteness on clean data while its docstring
    claimed the estimator survives a stray NaN. It does not: the point estimate
    comes back NaN and the standard error comes back 0.0, so a by_cycle row would
    read as an unknown prevalence with a perfectly precise interval. The real
    guarantee is upstream, in build_descriptive's filter.
    """
    df = frame([("45-54", 1.0, 1.0, 0, 1), ("45-54", 1.0, np.nan, 0, 2)])
    p_std, se = age_standardised_prevalence(df)
    assert np.isnan(p_std)
    assert se == 0.0          # documented, not endorsed -- see build_descriptive


def test_design_effect_compares_against_the_standardised_srs_variance():
    """The denominator must be the SRS variance of the STANDARDISED estimator.

    It was originally p(1-p)/n, the SRS variance of a CRUDE proportion. Those
    are variances of different estimators: standardisation applies fixed weights
    to within-band proportions, so its SRS variance omits the between-band
    component. The reference was systematically too large, which pushed the
    ratio below one in two of eleven cycles and nineteen of forty-four subgroup
    rows -- an artefact of the comparison, not a property of the design.

    With everyone in one band the two coincide, so this frame pins the
    denominator to an independently computed value.
    """
    df = frame([("45-54", 1.0, 1.0, 0, 1)] * 50 + [("45-54", 1.0, 0.0, 0, 2)] * 50)
    srs_var = srs_variance_standardised(df)
    assert srs_var == pytest.approx(0.5 * 0.5 / len(df))

    deff, n_eff = design_effect(df, se=srs_var ** 0.5)
    assert deff == pytest.approx(1.0)
    assert n_eff == pytest.approx(len(df))


def test_design_effect_above_one_shrinks_the_effective_sample():
    """A clustered design inflates the variance, so n_eff must fall below n."""
    df = frame([("45-54", 1.0, 1.0, 0, 1)] * 50 + [("45-54", 1.0, 0.0, 0, 2)] * 50)
    srs_se = srs_variance_standardised(df) ** 0.5
    deff, n_eff = design_effect(df, se=srs_se * 2)      # twice the SRS error
    assert deff == pytest.approx(4.0)                   # variance ratio, not SE
    assert n_eff == pytest.approx(len(df) / 4)


def test_the_standardised_srs_reference_is_below_the_crude_one():
    """The between-band component is exactly what standardisation removes.

    This is the arithmetic behind the correction above: when prevalence varies
    across bands, the standardised SRS variance is strictly below p(1-p)/n, so
    dividing by the crude reference understates the design effect.
    """
    prevalence = {"20-34": 0.02, "35-44": 0.04, "45-54": 0.08,
                  "55-64": 0.15, "65-74": 0.25, "75+": 0.40}
    rows = []
    for i, g in enumerate(AGE_LABELS):
        n_yes = int(round(50 * prevalence[g]))
        for k in range(50):
            rows.append((g, 1.0, 1.0 if k < n_yes else 0.0, i, 1 + k % 2))
    df = frame(rows)
    p_std, _ = age_standardised_prevalence(df)
    assert srs_variance_standardised(df) < p_std * (1 - p_std) / len(df)
