# Current Tableau dashboards

Reviewed on 22 September 2026 in Tableau Public 2026.2. The workbook contains
three dashboards, twelve worksheets and published aggregate data only.

- `cardiotrace-atlas.twbx`: locally saved native workbook; reopened successfully.
- `01-population-burden.png`, `02-mortality-risk.png`, `03-model-evidence.png`:
  captures of the native presentation canvas at 1380 × 940 pixels.
- `data-audit.json`: research commit and exact source manifests.
- `verification.json`: workbook/image hashes, complete embedded-table comparison,
  native reopen and tooltip review.

The data are based on research commit `64dbdbd`. All 334 rows across the twelve
embedded tables match the generated extract. Calibration uses survey-weighted
Aalen–Johansen observed risk, including early censoring. Captions and titles
were revised for the website; models and selection rules were not changed.

Run `python scripts/tableau_atlas.py --current` from the repository root to
check this reviewed set. The September 6 originals remain one directory above,
with independent frozen sources and `--snapshot` validation. These files are
not a Tableau Public web upload; the website shows static previews and links
to the editable native workbook.
