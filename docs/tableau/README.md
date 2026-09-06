# CardioTrace Tableau research atlas

[Open the visual atlas](../explore.html) · [Read the complete report](../cardiotrace-report.html)
· [Download the workbook](cardiotrace-atlas.twbx)

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

The atlas describes source research version `9517c6f`. It remains current only
while the input hashes in [data-audit.json](data-audit.json) match the repository.
The site/report build checks these hashes and the reviewed workbook/image hashes
in [verification.json](verification.json). CI requires neither Tableau nor Hyper.

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

For changes, follow [the maintenance guide](../tableau-dashboard.md).
