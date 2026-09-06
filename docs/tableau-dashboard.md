# Tableau research atlas: publication and maintenance

## Current delivered atlas

The delivered atlas has **three dashboards and twelve native worksheets**, covering
population burden, mortality risk and model evidence. [Open the atlas](explore.html)
or [download the portable workbook](tableau/cardiotrace-atlas.twbx). The report
chapters link to the corresponding dashboard, and the atlas links back to their
methods and limitations. The complete HTML report also embeds all three preview
images so that a saved copy remains self-contained.

The workbook and reviewed PNGs live in `docs/tableau/`. They read published
aggregate CSV/JSON results, not participant records. `data-audit.json` records
the source research version and input hashes; `verification.json` records the
native save/reopen check, exact extract comparison and artifact hashes.
The original source digests are retained; `source_sha256_lf` normalises only
CRLF to LF so that a Windows review and Linux CI check the same source text.
`scripts/tableau_atlas.py` runs during report/site generation and rejects a changed
source, an altered reviewed image/workbook or a non-portable data connection.
This guard also runs in tests and the render rebuild in CI.

The website publishes previews and a downloadable workbook even without a
Tableau Public account. `TABLEAU_VIZ` in `scripts/build_site.py` remains optional:
only set it after verifying a real, published view. Without it, no Tableau
script loads and the page clearly identifies its images as previews.

### Rebuilding a changed atlas

1. Install the optional `requirements-tableau.txt` dependencies in a separate
   environment. Normal analysis, site builds and CI do not need them.
2. Run `python scripts/build_tableau_atlas.py --out build/tableau`. Its frozen
   source check permits documentation commits, but rejects changed result bytes.
   If the research changes, review the source version, KPI text, captions,
   scientific limitations and fixed axes together before updating that check.
3. Open the generated TWBX in Tableau, inspect all dashboards and tooltips,
   save locally and reopen the packaged file. Check that every connection is
   embedded and compare each Hyper table with the generated extract.
4. Capture the three presentation canvases. Update the workbook, previews and
   audit/verification records in `docs/tableau/` as one reviewed set. Do not
   refresh a source hash solely to silence a stale-dashboard failure.
5. Run the suite, regenerate the report/site/README/handover/summary, commit
   the changes, and run `scripts/verify_clean_rebuild.py --full`. Commit only
   the new receipt afterward. CI and the receipt gate must pass before merging.

The generation script produces the initial native workbook; the committed
version is then saved by Tableau. Native XML and thumbnails may differ, so
exact numerical extract comparison and visual review are separate checks.

## Historical explorer proposal — not the delivered atlas

The original prevalence-only proposal below is retained as design history.
Its four sheets, filters and 1000 × 720 sizing were not implemented as specified;
the delivered 1380 × 940 atlas follows the broader report. The original
187-cell prevalence extract remains a source, alongside the mortality and model
results listed in the current manifest. Do not describe the proposal's filters
as features of the delivered workbook.

### Original proposal

The report chooses six views because an argument needs a spine. The estimates
underneath cover far more: six conditions, eleven cycles, six age bands and five
race-ethnicity groups, which is 187 published cells. This dashboard exists to let
a reader ask a question the report did not, and for no other reason — it must not
restate a figure that already exists.

Everything it plots comes from one file, written by `scripts/build_tableau_extract.py`:

```bash
.venv/Scripts/python.exe scripts/build_tableau_extract.py
```

→ `data/tableau/cardiotrace_prevalence.csv`, 187 rows.

The extract copies values out of `reports/tables/`; it never recomputes one. That
is deliberate. If the dashboard and the report ever disagree, the cause is this
one file, not two analyses that drifted — which is a bug with a single place to
look rather than a discrepancy nobody can adjudicate.

## The columns, and which are deliberately empty

| Column | Meaning |
|---|---|
| `cycle`, `year` | Survey cycle, and its midpoint for a continuous axis |
| `dimension` | `Overall` · `Race and ethnicity` · `Age band` · `Condition` |
| `level` | The category within that dimension |
| `outcome` | The condition estimated |
| `n`, `n_cases`, `n_psu` | Unweighted denominator, cases, sampling units |
| `pct_standardised` | Age-standardised to the 2000 U.S. standard population |
| `se_pct`, `ci_lo_pct`, `ci_hi_pct` | Design-based standard error and 95% interval. The interval is **t(`design_dof`)**, not normal — see the next two rows |
| `design_dof` | Design degrees of freedom for that row: PSUs − strata. Single-digit for most cycles |
| `ci_crit` | The critical value actually used, so a workbook can state its own convention. t(8) = 2.306 against z = 1.96 is an 18% wider band, and a legend that says only "95% CI" hides which one is on the screen |
| `pct_crude` | Unstandardised, for the comparison the report makes in §2 |
| `deff`, `n_effective` | Design effect and effective sample size |

**Age-band rows carry no standardised estimate and no interval, on purpose.**
An age-specific rate has nothing left to standardise, and no design-based
interval was computed for those cells. A workbook that plots a band there is
drawing an interval that does not exist. Guard it in Tableau with

```
IIF(ISNULL([Ci Lo Pct]), NULL, [Ci Lo Pct])
```

and, better, filter the confidence-band mark to `dimension != "Age band"`.

**`n_psu` is the honest denominator for "how much independent information is
here", not `n`.** A cell with n = 1,199 built from 26 sampling units is not
1,199 independent observations. Put `n_psu` in every tooltip.

## Sheets

1. **Trend** — `year` on columns, `pct_standardised` on rows, `level` on colour,
   filtered by `dimension`. Add a band mark for `ci_lo_pct`/`ci_hi_pct`.
   This is the sheet that earns the dashboard: the report shows race and age
   separately in two static figures, and here they are one control.
2. **Crude vs standardised** — a dual axis of `pct_crude` and `pct_standardised`
   for `dimension = Overall`. The whole of §2 in one interaction.
3. **Conditions small multiple** — `dimension = Condition`, `level` on rows as
   trellis. Six sparklines the report has no room for.
4. **Design quality** — `deff` and `n_effective` by cycle, as a bar with a
   reference line at DEFF = 1. Nobody publishes this; it is the sheet that shows
   the analysis knows what its own precision is.

## Dashboard assembly

- Size **fixed 1000 × 720**, which fits the site's 1080 px content column with
  room for the container border. Do *not* use Automatic: Tableau's responsive
  behaviour inside an iframe is unreliable and the embed will clip.
- Controls: a `dimension` selector, a `level` multi-select, a cycle range.
- Title, caption and legend fonts: **Tableau's `Georgia`** for headings and
  `Arial` for labels. The site uses a serif/sans pair; Georgia is the closest
  match Tableau ships and avoids a web-font dependency.
- Palette, to match the site exactly — set these as a **custom sequential /
  categorical palette** in `Preferences.tps`:

| Role | Hex | Where it appears on the site |
|---|---|---|
| Series (primary) | `#2a78d6` | the standardised line, links |
| Comparison / flag | `#eb6834` | the crude line, caveats |
| Ink | `#0b0b0b` | text |
| Ink, secondary | `#52514e` | captions |
| Gridline | `#e1e0d9` | gridlines |
| Axis | `#c3c2b7` | spines |
| Plate | `#fcfcfb` | plot background |

  For a sequential ramp (age bands, quintiles) use the site's own five steps:
  `#86b6ef` `#5598e7` `#2a78d6` `#1c5cab` `#104281`.

  If any of these is used behind **text** in the workbook rather than as a mark,
  substitute the darker text variants the site uses for the same reason —
  `#1c5cab` for the blue and `#ba4212` for the orange. As marks they are fine:
  `#eb6834` on `#fcfcfb` is 3.12:1, which clears the 3:1 that WCAG 1.4.11 asks of
  a graphical object, but only 2.96:1 on the page ground, which is under the
  4.5:1 that text needs.

  Set the worksheet background to `#fcfcfb` and the dashboard background to
  `#f7f6f2`. Turn **off** the column and row dividers; the site's figures use
  bottom-and-left spines only.

## Publishing, and what it costs

Tableau Public is the only free path and it is public by definition — the extract
here is already published CDC data, so that is fine, but note it in the workbook
description so nobody assumes otherwise later.

1. Open `data/tableau/cardiotrace_prevalence.csv` in **Tableau Desktop Public
   Edition** (free; Tableau Public in the browser also works but has fewer
   formatting controls).
2. Build the four sheets and the dashboard.
3. **Server → Tableau Public → Save to Tableau Public As…**, name it
   `CardioTrace — Prevalence Explorer`.
4. On the published page, **Share → Embed Code**. Take the `name` parameter out
   of it — it looks like `CardioTraceExplorer/Dashboard1`.
5. Put that value in `TABLEAU_VIZ` at the top of `scripts/build_site.py` and run
   `make site`. The explorer page renders it; until then that page shows the
   static fallback and says so.

**The tradeoff worth knowing before you do it.** The embed loads
`public.tableau.com/javascripts/api/tableau.embedding.3.latest.min.js`, so the
explorer page becomes the one page on this site that makes an external request,
depends on a third party being up, and cannot be viewed offline. Every other page
is self-contained static HTML. That is why the explorer is its own page rather
than a panel inside `burden.html`: one page carries the dependency, and the
report itself stays intact if Tableau Public changes its embed API or goes away.

The static fallback is not a placeholder for that reason — it is what the page
degrades to, and it should stay accurate.
