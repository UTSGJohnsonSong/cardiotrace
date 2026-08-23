"""Shared fixtures: a synthetic NHANES tree, so cohort tests need no real data.

`pyreadstat.write_xport` round-trips through both paths `src.cohort._read` uses
(`metadataonly=True` and `usecols=`), so these files exercise the real reader
rather than a stub.
"""

import sys
from pathlib import Path

import pandas as pd
import pyreadstat
import json

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_sessionfinish(session, exitstatus):
    """Record the size of this suite where the site can read it.

    The published site states how many automated tests there are. No statistic
    on that site may be typed by hand, and the only thing that knows this one is
    the suite itself -- so the suite writes it, on every full run.

    A filtered run would record a smaller number than the suite really has, so
    selective invocations are skipped rather than allowed to overwrite it. The
    option name for --last-failed is `lf`, not `last_failed`; getattr on the
    long name silently returns the default and lets a filtered run through.
    """
    o = session.config.option
    if (getattr(o, "file_or_dir", None) or getattr(o, "keyword", "")
            or getattr(o, "markexpr", "") or getattr(o, "lf", False)
            or getattr(o, "failedfirst", False) or o.collectonly):
        return
    out = Path(__file__).parent.parent / "reports"
    out.mkdir(exist_ok=True)
    (out / "test_summary.json").write_text(
        json.dumps({"collected": session.testscollected,
                    "failed": session.testsfailed,
                    "exit_status": int(exitstatus)}, indent=2) + "\n",
        encoding="utf-8")


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
