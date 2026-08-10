"""Shared fixtures: a synthetic NHANES tree, so cohort tests need no real data.

`pyreadstat.write_xport` round-trips through both paths `src.cohort._read` uses
(`metadataonly=True` and `usecols=`), so these files exercise the real reader
rather than a stub.
"""

import sys
from pathlib import Path

import pandas as pd
import pyreadstat
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def fake_raw(tmp_path, monkeypatch):
    """Write synthetic XPT files into a temporary data/raw tree."""
    from src import cohort

    monkeypatch.setattr(cohort, "RAW", tmp_path)

    def write(cycle: str, filename: str, cols: dict):
        (tmp_path / cycle).mkdir(parents=True, exist_ok=True)
        pyreadstat.write_xport(
            pd.DataFrame(cols),
            str(tmp_path / cycle / f"{filename}.XPT"),
            table_name=filename[:8],
        )

    write.root = tmp_path
    return write


@pytest.fixture
def fake_crosswalk(tmp_path, monkeypatch):
    """Write a crosswalk CSV and point src.cohort at it."""
    from src import cohort

    path = tmp_path / "variable_crosswalk.csv"
    monkeypatch.setattr(cohort, "CROSSWALK", path)

    def write(rows: list[dict]):
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    return write


CROSSWALK_COLUMNS = ["analyte", "cycle", "source_module", "variable",
                     "unit", "canonical_unit", "to_canonical"]


def crosswalk_row(analyte, cycle, module, variable,
                  unit="mg/dL", canonical="mg/dL", factor=1.0):
    return dict(zip(CROSSWALK_COLUMNS,
                    [analyte, cycle, module, variable, unit, canonical, factor]))
