"""
ETL utilities for CardioTrace: read NHANES XPT files and load them into the
PostgreSQL `raw` schema.

Two pieces of real-world NHANES messiness are handled here:

1. Several source files map to one raw table. Cholesterol lives in three files
   (TCHOL, HDL, TRIGLY); glucose in two (GLU, GHB); etc. These must be MERGED
   per participant (outer join on SEQN) into a single row, not appended — the
   (seqn, cycle) primary key would reject the extra rows otherwise.

2. CDC changed instruments mid-series. Oscillometric blood pressure (BPXO,
   columns BPXOSY1..) replaced the manual sphygmomanometer (BPX, BPXSY1..) from
   2017 on, and high-sensitivity CRP (HSCRP, LBXHSCRP in mg/L) replaced the old
   CRP assay (CRP, LBXCRP in mg/dL). `harmonize()` maps both onto one set of
   column names / units so a single downstream model sees a continuous series.
"""

import logging
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"

# Source module → raw table (schema-qualified). Several modules share a table.
MODULE_TABLE_MAP = {
    "DEMO":   "raw.demographics",
    "MCQ":    "raw.cardiovascular_questionnaire",
    "BPX":    "raw.blood_pressure_exam",
    "BPXO":   "raw.blood_pressure_exam",
    "BPQ":    "raw.blood_pressure_questionnaire",
    "BMX":    "raw.body_measures",
    "DIQ":    "raw.diabetes_questionnaire",
    "SMQ":    "raw.smoking_questionnaire",
    "TCHOL":  "raw.labs_cholesterol",
    "HDL":    "raw.labs_cholesterol",
    "TRIGLY": "raw.labs_cholesterol",
    "GHB":    "raw.labs_glucose",
    "GLU":    "raw.labs_glucose",
    "BIOPRO": "raw.labs_biochemistry",
    "HSCRP":  "raw.labs_crp",
    "CRP":    "raw.labs_crp",
    "PAQ":    "raw.physical_activity",
}


def get_engine(db_url: str | None = None):
    url = db_url or os.environ.get(
        "DATABASE_URL",
        "postgresql://cardiotrace:cardiotrace@localhost:5435/cardiotrace",
    )
    return create_engine(url)


def module_of(xpt_path: Path) -> str:
    """Module code from a filename, e.g. DEMO_J.XPT → DEMO, TCHOL.XPT → TCHOL."""
    return xpt_path.stem.split("_")[0].upper()


# Extra source columns (beyond the raw-table columns) that harmonize() needs.
HARMONIZE_SOURCES = {
    "BPXO":  ["bpxosy1", "bpxosy2", "bpxosy3", "bpxodi1", "bpxodi2", "bpxodi3"],
    "HSCRP": ["lbxhscrp"],
}


def read_xpt(path: Path, usecols: list[str] | None = None) -> pd.DataFrame:
    """Read a NHANES XPT (SAS transport) file into a tidy DataFrame.

    Uses pyreadstat's C reader (fast and robust; pandas' pure-Python XPORT
    reader MemoryErrors on some NHANES files). `usecols` (original-case column
    names) limits the read to the columns we actually keep — NHANES files carry
    up to ~90 columns and reading them all wastes memory across 140+ files.
    """
    import pyreadstat

    # NHANES variable labels use Latin-1 (e.g. the µ in "µmol/L"), not UTF-8.
    kwargs = {"encoding": "LATIN1"}
    if usecols:
        kwargs["usecols"] = usecols
    df, _ = pyreadstat.read_xport(str(path), **kwargs)
    df.columns = [c.lower() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    if "seqn" in df.columns:
        df["seqn"] = pd.to_numeric(df["seqn"], errors="coerce").astype("Int64")
    return df


def _wanted_original_cols(path: Path, module: str, table_cols: set[str]) -> list[str]:
    """Original-case column names in this file that map to the target table."""
    import pyreadstat

    _, meta = pyreadstat.read_xport(str(path), encoding="LATIN1", metadataonly=True)
    wanted = set(table_cols) | {"seqn"} | set(HARMONIZE_SOURCES.get(module, []))
    return [c for c in meta.column_names if c.lower() in wanted]


def harmonize(df: pd.DataFrame, module: str) -> pd.DataFrame:
    """Map instrument-specific columns onto the canonical raw-table columns."""
    if module == "BPXO":
        # Oscillometric → manual column names (same clinical quantity).
        rename = {
            "bpxosy1": "bpxsy1", "bpxosy2": "bpxsy2", "bpxosy3": "bpxsy3",
            "bpxodi1": "bpxdi1", "bpxodi2": "bpxdi2", "bpxodi3": "bpxdi3",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    elif module == "HSCRP":
        # hs-CRP is already mg/L; store it in the shared lbxcrp column.
        if "lbxhscrp" in df.columns:
            df = df.rename(columns={"lbxhscrp": "lbxcrp"})
    elif module == "CRP":
        # Legacy CRP assay is mg/dL; convert to mg/L (×10) to match hs-CRP.
        if "lbxcrp" in df.columns:
            df["lbxcrp"] = pd.to_numeric(df["lbxcrp"], errors="coerce") * 10.0
    return df


def table_columns(engine, schema: str, table: str) -> list[str]:
    q = text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = :t"
    )
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(q, {"s": schema, "t": table})]


def load_cycle(cycle: str, engine, truncate: bool = False):
    """Read every XPT for one cycle, merge files that share a table, and load."""
    cycle_dir = RAW_DIR / cycle
    if not cycle_dir.exists():
        log.warning(f"No data directory for cycle {cycle}")
        return

    # Group source files by their destination table.
    by_table: dict[str, list[Path]] = {}
    for xpt in sorted(cycle_dir.glob("*.XPT")):
        table = MODULE_TABLE_MAP.get(module_of(xpt))
        if table:
            by_table.setdefault(table, []).append(xpt)
        else:
            log.debug(f"No table mapping for {xpt.name}, skipping")

    for table, files in by_table.items():
        schema, tbl = table.split(".")
        cols = set(table_columns(engine, schema, tbl))

        # Merge all files for this table on SEQN (outer), coalescing overlaps.
        # Read only the columns this table needs — keeps memory flat across the
        # 140+ files, and skips any single unreadable file rather than aborting.
        merged = pd.DataFrame()
        for xpt in files:
            module = module_of(xpt)
            try:
                usecols = _wanted_original_cols(xpt, module, cols)
                part = harmonize(read_xpt(xpt, usecols=usecols), module)
            except Exception as e:
                log.warning(f"[{cycle}] skipping {xpt.name}: {type(e).__name__}: {e}")
                continue
            if "seqn" not in part.columns:
                continue
            part = part.set_index("seqn")
            merged = part if merged.empty else merged.combine_first(part)

        if merged.empty:
            continue
        merged = merged.reset_index()
        merged["cycle"] = cycle

        keep = [c for c in merged.columns if c in cols]
        out = merged[keep].drop_duplicates(subset=["seqn"])

        if truncate:
            with engine.begin() as conn:
                conn.execute(text(f'TRUNCATE TABLE {schema}.{tbl}'))

        out.to_sql(tbl, engine, schema=schema, if_exists="append",
                   index=False, method="multi", chunksize=500)
        log.info(f"[{cycle}] {tbl}: {len(out)} rows  ({', '.join(f.name for f in files)})")


def load_all_cycles(engine, truncate: bool = True):
    """Load every downloaded cycle. Truncates raw tables first for idempotency."""
    cycles = sorted(d.name for d in RAW_DIR.iterdir() if d.is_dir())
    log.info(f"Found {len(cycles)} cycles: {cycles}")

    if truncate:
        tables = sorted(set(MODULE_TABLE_MAP.values()))
        with engine.begin() as conn:
            for t in tables:
                conn.execute(text(f"TRUNCATE TABLE {t}"))
        log.info(f"Truncated {len(tables)} raw tables")

    import gc
    for cycle in cycles:
        load_cycle(cycle, engine, truncate=False)
        gc.collect()


def get_master_df(engine) -> pd.DataFrame:
    """Load the mart.mart_cv_master table for modeling."""
    return pd.read_sql("SELECT * FROM mart.mart_cv_master", engine)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%H:%M:%S")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_all_cycles(get_engine())
