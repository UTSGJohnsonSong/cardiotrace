# Independent re-estimation of Part 1 and Part 3 in R's `survey` package.
#
# WHY THIS FILE EXISTS
# --------------------
# It is the other implementation. Everything it computes is already computed in
# `src/descriptive.py` and `src/models.py`; the point is that it was written
# from the published definitions by a different codebase, so when the two agree
# the agreement is evidence and not a tautology. Nothing in here may be adjusted
# to make a number match. If a number does not match, that IS the output.
#
# WHAT WOULD SILENTLY GO WRONG IF THIS FILE WERE SLOPPY
# -----------------------------------------------------
# Three things, each of which produces a plausible-looking wrong answer rather
# than an error:
#
#   nest=TRUE. NHANES numbers PSUs 1,2 INSIDE each stratum. Without nest=TRUE,
#   survey reads every "PSU 1" in the file as the same cluster, pools people
#   from unrelated strata into one ultimate cluster, and returns a standard
#   error that is wrong in an unsignposted direction. The design object is built
#   without complaint either way.
#
#   The standard population is read from part1_stdpop.csv, which Python writes
#   out of STD_2000. It is not typed in here. Two copies of eleven decimal
#   constants in two languages will eventually disagree, and the symptom would
#   be a variance discrepancy in a run whose real fault is a transcription.
#
#   The analytic frames are read, never rebuilt. If this file re-derived the
#   cohort, a disagreement could mean "different formula" or "different people",
#   and telling those apart afterwards is close to impossible.
#
# LONELY PSUs
# -----------
# Run under both survey.lonely.psu="adjust" (the analogue of the collapse rule
# `_linearised_variance` documents: centre the lone unit on the grand mean) and
# "average" (substitute the average within-stratum variance). Both are emitted.
# Where they are identical, the sample has no singleton strata and the project's
# collapse rule is inert for that estimate -- which is worth stating explicitly,
# because "our rule differs from the default" only matters when it fires.
#
#   Rscript scripts/crosscheck_survey.R <exchange_dir> [part1|part3|both]

suppressPackageStartupMessages({
  library(survey)
  library(survival)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1L) stop("usage: crosscheck_survey.R <exchange_dir> [part]")
exchange <- args[1L]
part <- if (length(args) >= 2L) args[2L] else "both"

LONELY <- c("adjust", "average")

cat(sprintf("survey %s | survival %s | %s\n",
            packageVersion("survey"), packageVersion("survival"),
            R.version.string))


# ------------------------------------------------------------------ part 1 ---

part1_one <- function(d, std, lonely) {
  options(survey.lonely.psu = lonely)

  # Levels come from the standard-population file, so the contrast vector and
  # the domain means are in the same order by construction rather than by luck.
  d$age_group <- droplevels(factor(d$age_group, levels = std$age_group))
  des <- svydesign(ids = ~psu, strata = ~strata, weights = ~weight,
                   data = d, nest = TRUE)

  # covmat=TRUE keeps the covariance BETWEEN age bands. Dropping it and adding
  # per-band variances is the mistake the Python docstring warns about: one
  # person's PSU contributes to several bands, and treating the bands as
  # independent throws that dependence away silently.
  a <- svyby(~prev_cvd, ~age_group, des, svymean, covmat = TRUE)

  w <- std$std_weight[match(levels(d$age_group), std$age_group)]
  w <- w / sum(w)          # renormalise over the bands present -- Master List
  names(w) <- names(coef(a))
  ctr <- svycontrast(a, list(p_std = w))

  crude <- svymean(~prev_cvd, des)

  # Second, independent R route to the same estimand. svystandardize rescales
  # the weights and post-stratifies; svycontrast linearises a fixed combination
  # of domain means. They should land in the same place, and reporting the gap
  # is how a reader knows the Python number is not being compared against one
  # arbitrary choice among several R answers.
  pop <- std$std_weight[match(levels(d$age_group), std$age_group)]
  sdes <- svystandardize(des, by = ~age_group, over = ~1, population = pop)
  sm <- svymean(~prev_cvd, sdes)

  data.frame(
    lonely_psu   = lonely,
    n            = nrow(d),
    n_psu        = nrow(unique(d[, c("strata", "psu")])),
    n_strata     = length(unique(d$strata)),
    design_df    = degf(des),
    p_std        = as.numeric(coef(ctr)),
    se_std       = as.numeric(SE(ctr)),
    p_std_svystd = as.numeric(coef(sm)),
    se_std_svystd = as.numeric(SE(sm)),
    p_crude      = as.numeric(coef(crude)),
    se_crude     = as.numeric(SE(crude)),
    stringsAsFactors = FALSE
  )
}

run_part1 <- function() {
  d <- read.csv(file.path(exchange, "part1_input.csv"), stringsAsFactors = FALSE)
  std <- read.csv(file.path(exchange, "part1_stdpop.csv"), stringsAsFactors = FALSE)
  cat(sprintf("part1: %d rows, %d cycles\n", nrow(d), length(unique(d$cycle))))

  out <- do.call(rbind, lapply(LONELY, function(lp) {
    do.call(rbind, lapply(sort(unique(d$cycle)), function(cy) {
      # One design per cycle. The stratum codes do not repeat across cycles, so
      # a pooled design subset to a cycle would give the same answer; building
      # per cycle mirrors what by_cycle() does with design=None and removes the
      # question of whether the domain machinery is what is being compared.
      cbind(cycle = cy, part1_one(d[d$cycle == cy, , drop = FALSE], std, lp))
    }))
  }))
  write.csv(out, file.path(exchange, "part1_r.csv"), row.names = FALSE)
  cat(sprintf("part1: wrote %d rows\n", nrow(out)))
}


# ------------------------------------------------------------------ part 3 ---

part3_terms <- function(m, label, design_df = NA_integer_) {
  b <- coef(m)
  se <- sqrt(diag(vcov(m)))

  # NOT confint(m). survey's confint for a svycoxph returns a NORMAL interval,
  # so Part 3's primary interval was built on z = 1.96 while Part 1, the
  # ascertainment series and the Tableau extract all use a t on the design
  # degrees of freedom. Two conventions under one "95% CI" legend, with nothing
  # in the artefact recording which was which -- and design_df was printed to
  # the console rather than written to the file, so the Python loader could not
  # have checked it even if it had wanted to.
  #
  # Pooling eight cycles does buy a lot of df: 123 here, against 8-17 per cycle
  # in Part 1. So the correction is small -- on the exposure, 1.0789-1.1660
  # against 1.0785-1.1664 per 10 mmHg. That is one printed digit in the
  # headline stat card, and being small is not a reason to use a different rule
  # from the rest of the project without saying so.
  crit <- if (is.na(design_df)) qnorm(0.975) else qt(0.975, design_df)
  data.frame(
    fit  = label,
    term = names(b),
    coef = as.numeric(b),
    se   = as.numeric(se),
    lo95 = as.numeric(b - crit * se),
    hi95 = as.numeric(b + crit * se),
    crit = crit,
    # Written, not printed. A multiplier the loader cannot re-derive is a
    # multiplier the loader cannot check.
    design_df = design_df,
    stringsAsFactors = FALSE
  )
}

run_part3 <- function() {
  d <- read.csv(file.path(exchange, "part3_input.csv"), stringsAsFactors = FALSE)
  covs <- readLines(file.path(exchange, "part3_covariates.txt"))
  covs <- covs[nzchar(covs)]
  f <- as.formula(paste("Surv(followup_years, cvd_death) ~",
                        paste(covs, collapse = " + ")))
  cat(sprintf("part3: %d rows, %d events, %d covariates\n",
              nrow(d), sum(d$cvd_death), length(covs)))

  psu_per_stratum <- tapply(d$psu, d$strata, function(x) length(unique(x)))
  cat(sprintf("part3: %d strata, %d singleton strata after listwise deletion\n",
              length(psu_per_stratum), sum(psu_per_stratum < 2)))

  out <- list()
  for (lp in LONELY) {
    options(survey.lonely.psu = lp)
    des <- svydesign(ids = ~psu, strata = ~strata, weights = ~wtmec2yr,
                     data = d, nest = TRUE)
    m <- svycoxph(f, design = des)
    lab <- if (lp == "adjust") "svycoxph" else paste0("svycoxph_", lp)
    ddf <- degf(des)
    if (lp == "adjust") {
      cat(sprintf("part3: design df = %d (PSUs - strata), t = %.5f\n",
                  ddf, qt(0.975, ddf)))
    }
    out[[length(out) + 1L]] <- part3_terms(m, lab, ddf)
  }

  # The same estimator lifelines computes: cluster-robust sandwich, no strata,
  # no n_h/(n_h-1). Fitting it here is what separates "the two implementations
  # disagree" from "the two are estimating different variances on purpose".
  fc <- as.formula(paste("Surv(followup_years, cvd_death) ~",
                         paste(covs, collapse = " + "),
                         "+ cluster(design_cluster)"))
  mc <- coxph(fc, data = d, weights = d$wtmec2yr, robust = TRUE)
  # No design object, so no design df: this one keeps the normal quantile,
  # and the NA in the column is what says so rather than leaving a reader to
  # guess which multiplier produced it.
  out[[length(out) + 1L]] <- part3_terms(mc, "coxph_cluster")

  res <- do.call(rbind, out)
  write.csv(res, file.path(exchange, "part3_r.csv"), row.names = FALSE)
  cat(sprintf("part3: wrote %d rows (%s)\n", nrow(res),
              paste(unique(res$fit), collapse = ", ")))
}


if (part %in% c("part1", "both")) run_part1()
if (part %in% c("part3", "both")) run_part3()
