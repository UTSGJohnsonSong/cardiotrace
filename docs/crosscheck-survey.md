# Cross-check against R's `survey` package

> **Status: proposed.** This is drafted for the methods appendix and is
> deliberately *not* wired into `render_report.py`, the site, or
> `cardiotrace-report.html`. Nothing here has been approved for the report yet.
>
> Run: `python scripts/crosscheck_survey.py`
> Output: `reports/tables/crosscheck_part1.csv`, `reports/tables/crosscheck_part3.csv`
> Environment: R 4.5.2, survey 4.4.8, survival 3.8.3; lifelines 0.30.3, Python 3.11.9

## Why

Both variance estimators in this project are hand-written: the Taylor
linearisation in `src/descriptive.py` and the cluster-robust Cox in
`src/models.py`. Their unit tests were written by the same person who wrote the
formulas, so they can confirm the code does what its author intended and cannot
confirm that the intention was right. A design-based standard error gives no
sign when it is wrong — it stays positive, stays the right order of magnitude,
and moves in the right direction across cycles whether or not the between-band
covariance was kept or the `n_h/(n_h-1)` factor applied.

The missing evidence is an independent implementation. `survey` is that
implementation: written by someone else from the same published definitions, and
the package the NCHS analytic guidelines and the Stata/SAS survey procedures are
themselves checked against.

The harness exports the frames the shipped code path actually fits and hands
those same rows to R, rather than rebuilding the cohort in R. If R rebuilt it, a
disagreement could mean "different formula" or "different people", and the two
would be very hard to separate after the fact.

## Part 1 — age-standardised prevalence

Compared per cycle: `src.descriptive.by_cycle` against
`svydesign(ids=~psu, strata=~strata, weights=~weight, nest=TRUE)` +
`svyby(..., covmat=TRUE)` + `svycontrast`, using the standard-population weights
exported from `STD_2000` itself rather than retyped into the R file.

**They agree to machine precision.** Across all 11 cycles (62,877 respondents):

| quantity | largest absolute difference | largest relative difference |
|---|---|---|
| standardised prevalence | 4.2e-17 | — |
| standardised SE | 8.7e-17 | 2.1e-14 |
| crude prevalence | 5.6e-17 | — |
| crude SE | 9.2e-17 | — |

Three further checks, all of which had room to fail and did not:

- **`svystandardize` agrees with `svycontrast` exactly** (max SE difference
  0.0e+00). The two R routes linearise the standardisation differently —
  `svystandardize` post-stratifies the weights, `svycontrast` takes a fixed
  linear combination of domain means — so this rules out the possibility that
  the Python answer was being compared against one arbitrary choice among
  several R answers.
- **`survey.lonely.psu="adjust"` and `"average"` give identical results.** The
  overall by-cycle series has no singleton strata (13–16 strata and 27–32 PSUs
  per cycle, every stratum with at least two), so the collapse rule documented
  in `_linearised_variance` is inert here. It is not inert for the race
  subgroups, which is where it was written for and where it should be
  re-checked before those rows are quoted.
- **Design degrees of freedom are 14 to 17 per cycle** (`degf()`), which is what
  the hardcoded 1.96 in `by_cycle` is standing in for. For 1999-2000 (df = 14)
  the interval half-width is 0.0119 with 1.96 and 0.0130 with t(14) — 9% wider.
  The cross-check does not resolve that question, it just supplies the df.

## Part 3 — cause-specific Cox

Compared term by term: `models._fit` (lifelines, `weights_col=wtmec2yr`,
`cluster_col=design_cluster`, `robust=True`) against `svycoxph` on the same
design and the same nine covariates, on the identical 17,890 rows the Python fit
uses (768 CVD deaths, 118 strata, 241 PSUs, design df 123).

**Coefficients agree to 3.3e-12** — largest absolute difference across all nine
terms. Both sides maximise the same weighted Efron partial likelihood, and they
find the same maximum.

**The standard errors differ, and the reason is identified.** The R side also
fits plain `coxph` with `cluster()`, which is the *same* estimator lifelines
computes. That third fit splits the difference into two parts:

| comparison | what it measures | median relative difference | max |
|---|---|---|---|
| lifelines vs `coxph` + `cluster()` | implementation | 0.06% | 0.13% |
| lifelines vs `svycoxph` | choice of estimator | 1.20% | 9.36% |

So the implementation is right, and the gap is a difference of estimator:

- lifelines sums squared cluster-level score residuals, `sum_c u_c u_c'`, with no
  reference to strata;
- `svycoxph` uses the stratified ultimate-cluster estimator,
  `sum_h n_h/(n_h-1) * sum_i (u_hi - u_h.)(u_hi - u_h.)'`.

Neither is a bug. The second removes between-stratum variation and pays an
`n_h/(n_h-1) = 2` inflation for it at two PSUs per stratum; the first keeps that
variation and pays nothing. But only the second is the design-based variance the
NHANES analytic guidelines describe, and this project reports its intervals as
design-based.

The difference is not one-directional — the lifelines SE is larger on 7 of 9
terms and smaller on 2 — so it cannot be described as uniformly conservative or
uniformly anti-conservative. The two largest gaps are `education` (lifelines
9.4% larger) and `male` (lifelines 8.1% smaller). For the headline exposure the
gap is 0.2%:

| | HR per 10 mmHg systolic | 95% CI |
|---|---|---|
| lifelines | 1.1216 | 1.0788 – 1.1661 |
| `svycoxph` | 1.1216 | 1.0789 – 1.1660 |

No term changes sign, and no term crosses zero in one fit and not the other:
`education` and `smoke_former` include zero under both, the other seven exclude
it under both. `survey`'s own `confint.svycoxph` uses 1.96 here as well, so this
CI comparison is not confounded by a different multiplier.

`survey.lonely.psu="adjust"` and `"average"` give identical Part 3 results too —
after listwise deletion, none of the 118 strata is left with a single PSU.

## What this does and does not license

**Does:** the Taylor-linearised variance in `src/descriptive.py` reproduces
`survey` to machine precision, and the Cox point estimates reproduce `survival`
to 12 decimal places. Those two claims no longer rest on the project's own unit
tests.

**Does not:** it says nothing about whether the estimand is the right one. The
weight choice, the age bands, the 1.96 multiplier, the complete-case deletion
and the exclusion of 2,846 people from the Cox fit are all upstream of anything
checked here, and R agrees with Python on all of them because it was handed the
same rows. An independent implementation certifies arithmetic, not design.

**Open:** the Part 3 robust SE should be reconciled — either by reporting the
design-based `svycoxph` variance, or by stating explicitly that the published
intervals use an unstratified cluster sandwich and are therefore not
design-based in the NHANES sense. The 9.4% and 8.1% gaps are on covariates, not
on the exposure, so the headline hazard ratio is unaffected either way.
