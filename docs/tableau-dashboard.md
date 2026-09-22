# Tableau dashboards: maintenance

## Current delivery — 22 September 2026

The three dashboards in `docs/tableau/current/` are the primary visual overview
on `explore.html`. Individual Python figures remain available in expandable
sections. The native workbook and previews use the current aggregate results,
including weighted Aalen–Johansen calibration. The September 6 workbook and
previews remain unchanged in `docs/tableau/` as a separately labelled archive.

`python scripts/tableau_atlas.py --current` checks the new source hashes,
workbook and preview hashes, embedded connections and complete native-review
record. `--snapshot` independently verifies the original frozen September 6
sources. The default CLI retains the original strict current-source check for
the old artifact and correctly rejects its outdated calibration sources.

The current workbook was saved and reopened in Tableau Public 2026.2. Its
12 embedded tables (334 rows) were compared exactly with the generated Hyper
extract. Three previews were captured from the actual presentation canvas at
1380 × 940 pixels, and a native tooltip was inspected. `verification.json`
records the review and exact artifacts. The browser previews are static images;
the downloadable workbook provides editable native views. There is no Tableau
Public web view configured.

To regenerate the current workbook, first commit the aggregate results, then
run the optional generator with an explicit research commit:

```sh
python scripts/build_tableau_atlas.py --out build/tableau --source-commit 64dbdbd
```

For a later research revision, replace that commit only after reviewing the
changed result tables, captions and units. Repeat native save/reopen, all-table
comparison, tooltip inspection and preview review before replacing `current/`
as one set. Do not regenerate hashes alone to make stale output pass. A full
Python rebuild validates the frozen native artifacts but does not operate the
Tableau GUI or recreate its screenshots.

## September 18 presentation plan — superseded by the current delivery

## Current charts and the preserved native snapshot

[The current visual overview](explore.html) presents Python-generated charts
from current aggregate results. The main model calibration now uses
Aalen–Johansen observed risks to account for early censoring. Current charts
are the primary visual evidence linked from the report chapters.

The **6 September 2026 native Tableau snapshot** has three dashboards and twelve
worksheets, covering population burden, mortality risk and model evidence. Its
[portable workbook](tableau/cardiotrace-atlas.twbx) and three previews predate
that calibration correction. They are retained as a separate, labelled archive,
not presented as the current results. The complete HTML report embeds the
historical previews inside a collapsed appendix for offline provenance.

The workbook and reviewed PNGs live in `docs/tableau/`. They read published
aggregate CSV/JSON results, not participant records. `data-audit.json` records
the source research version and input hashes; `verification.json` records the
native save/reopen check, exact extract comparison and artifact hashes.
The original source digests are retained; `source_sha256_lf` normalises only
CRLF to LF so that a Windows review and Linux CI check the same source text.
The twelve original aggregate source files are preserved under
`docs/tableau/source-snapshot/`, with their repository-relative paths intact.
Neither the manifests nor the reviewed workbook and previews were refreshed to
accept the new calibration. `scripts/tableau_atlas.py` has two explicit checks:

- `validate()` / the default CLI compares the manifest with **current** source
  files. It still fails after any source change, including the calibration
  correction; it never falls back to historical files.
- `validate_snapshot()` / `python scripts/tableau_atlas.py --snapshot` compares
  the same original manifest with the **frozen** files. The labelled historical
  appendix and archive use this check. Both modes also validate exact preview
  and workbook hashes, worksheet inventory and portable embedded connections.

Tests cover changed current sources, changed frozen sources and changed reviewed
artifacts. Snapshot validation certifies preservation, not currency or native
Tableau re-review of new results.

The website provides current charts without requiring Tableau or a login. The
historical workbook remains an optional download. No Tableau Public publication
or current interactive workbook is implied: a real public view must be checked
against a newly reviewed native artifact before it can be linked as current.

### Preparing a future current native Tableau atlas

1. Install the optional `requirements-tableau.txt` dependencies in a separate
   environment. Normal analysis, site builds and CI do not need them.
2. Run `python scripts/build_tableau_atlas.py --out build/tableau`. Its frozen
   source check permits documentation commits, but rejects changed result bytes.
   If the research changes, review the source version, KPI text, captions,
   scientific limitations and fixed axes together before updating that check.
3. Open the generated TWBX in Tableau, inspect all dashboards and tooltips,
   save locally and reopen the packaged file. Check that every connection is
   embedded and compare each Hyper table with the generated extract.
4. Capture the three presentation canvases. Publish the new workbook, previews,
   sources and audit/verification records as one newly reviewed set in a separate
   versioned location. Preserve the 6 September snapshot. Only then change the
   site references and validation configuration to identify the new native set.
   Do not refresh a source hash solely to silence a stale-dashboard failure.
5. Run the suite, regenerate the report/site/README/handover/summary, commit
   the changes, and run `scripts/verify_clean_rebuild.py --full`. Commit only
   the new receipt afterward. CI and the receipt gate must pass before merging.

The generation script produces the initial native workbook; the committed
version is then saved by Tableau. Native XML and thumbnails may differ, so
exact numerical extract comparison and visual review are separate checks.

## Historical explorer proposal — not the delivered native atlas

The original prevalence-only proposal below is retained as design history.
Its four sheets, filters and 1000 × 720 sizing were not implemented as specified;
the historical 1380 × 940 native atlas follows the broader report. The original
187-cell prevalence extract remains a source, alongside the mortality and model
results listed in its frozen manifest. Do not describe the proposal's filters
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
