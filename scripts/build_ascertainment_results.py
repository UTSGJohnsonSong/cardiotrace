"""Produce the diagnostic-ascertainment table.

This table is read by the figure module and by the report. It previously had no
producer in the repository at all -- it was made once in an interactive session
-- so nobody could regenerate it, and nothing would have detected it drifting
out of step with the code after the age base changed. That is the same
condition under which every other silent defect in this project's history went
unnoticed, so it gets a script.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ascertainment import ascertained_by_cycle, build_ascertainment  # noqa: E402

ROOT = Path(__file__).parent.parent
TABLES = ROOT / "reports" / "tables"


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    df = build_ascertainment()
    table = ascertained_by_cycle(df)
    table.to_csv(TABLES / "part1_ascertainment.csv", index=False)

    aus = table[table["instrument"] == "auscultatory"]
    peak = aus.loc[aus["ascertained_std"].idxmax()]
    print(f"ascertainment: {len(df):,} adults with a usable BP and questionnaire answer")
    print(f"  auscultatory {100 * aus['ascertained_std'].iloc[0]:.1f}% -> "
          f"{100 * aus['ascertained_std'].iloc[-1]:.1f}%   "
          f"peak {100 * peak['ascertained_std']:.1f}% in {peak['cycle']}")
    osc = table[table["instrument"] == "oscillometric"]
    for _, r in osc.iterrows():
        print(f"  {r['cycle']} ({r['instrument']}, not on the series): "
              f"{100 * r['ascertained_std']:.1f}%")


if __name__ == "__main__":
    main()
