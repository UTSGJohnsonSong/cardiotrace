# CardioTrace historical Tableau snapshot — 6 September 2026

[View current charts](../explore.html) · [Read the complete report](../cardiotrace-report.html)
· [Download the historical workbook](cardiotrace-atlas.twbx)

**This native Tableau atlas is a historical snapshot, not the current results.**
It predates the Aalen–Johansen correction for censoring in the main model's
calibration. The website's current charts are generated from current aggregate
results with Python; these original Tableau previews and workbook remain
available separately for provenance. They have not been updated or re-reviewed
in Tableau for that correction.

The workbook contains three dashboards and twelve editable native worksheets,
with an embedded Hyper extract of published aggregate results. No participant
records or connection to the analysis environment are included. It was saved
and reopened in Tableau Public 2026.2; all extract rows were compared with the
generated data before release.

Open `cardiotrace-atlas.twbx` in Tableau Public or Desktop. Select a dashboard
from the bottom tabs. F7 enters/exits presentation mode; Ctrl+PageUp/PageDown
changes sheets. Hover a mark for exact estimates, sample details and provenance.
Use **File → Save to Computer** to keep local edits.

| Dashboard | Report chapters |
| --- | --- |
| 01 Population burden | [Burden](../burden.html), [Pandemic](../pandemic.html) |
| 02 Mortality risk | [Cohort](../cohort.html) |
| 03 Model evidence | [Historical PCE benchmark](../methods.html), [Part 4](../learning.html) |

The three PNG files are actual Tableau presentation-canvas captures at
2760 × 1880 pixels. They are previews; interaction lives in the workbook.
`Condition trends` is an additional worksheet retained outside the dashboards.

The atlas describes source research version `9517c6f`. Its twelve original
aggregate inputs are preserved under `source-snapshot/`, using the paths in
[data-audit.json](data-audit.json). The manifest, workbook, previews and
[verification.json](verification.json) retain their original reviewed bytes.
`python scripts/tableau_atlas.py --snapshot`, run from the repository root,
checks the frozen source hashes, reviewed workbook/image hashes and portable
connections. It does not certify current-source freshness. The default command
without `--snapshot` still compares against current research files and rejects
the updated calibration results. CI requires neither Tableau nor Hyper.

The 334 extract rows include interval vertices and calibration identity guides;
they are not participants. Parts 1/2 use interview weights; mortality analyses
use examination weights. The BP strata use n=19,831, the complete mortality
cohort n=20,736, and adjusted Cox n=17,890. HR intervals are R survey-design t
intervals. Age cells and BP cumulative incidence carry no exported intervals.
The latest survey is August 2021–August 2023; 2022 is its display reference year.

PCE is a prespecified historical benchmark, with hard ASCVD rather than CVD
mortality as its endpoint. Its ten-year score is used only for ranking at five
years. Paired PCE differences do not establish CardioTrace superiority. Part 4
uses a separate common sample. Decision curves omit treat-all in this zoom,
include no uncertainty intervals and make no clinical-utility claim.

For a future native Tableau update, follow [the maintenance guide](../tableau-dashboard.md):
rebuild, open, save, reopen, compare the extract and review the canvases before
publishing a new reviewed set. Retain this historical snapshot. Updating hashes
alone cannot turn it into a current atlas.
