"""
Assert that regenerating every artefact changes nothing tracked.

The point is not tidiness. Every published number on the site and in the README
is read out of a file in reports/ or data/tableau/, and those files are
committed. If a committed artefact and the code that writes it disagree, the
pages are showing a number no current script produces -- and nothing anywhere
says so. That is not hypothetical: docs/consistency-audit.md found nine such
numbers, and the mechanism was always the same, an artefact that outlived the
code.

    python scripts/verify_clean_rebuild.py --render   # ~1 min, needs no data
    python scripts/verify_clean_rebuild.py            # + tables and models
    python scripts/verify_clean_rebuild.py --full     # + Part 4, ~15 min

THREE SCOPES, BECAUSE ONLY ONE OF THEM CAN RUN IN CI. data/processed/ and
data/raw/ are gitignored -- the cohort is 5 MB of derived NHANES data and the
raw files are 376 MB -- so a checkout has the ARTEFACTS but not the inputs that
produced them.

  --render   The report, the site and the README. These read only tracked files
             in reports/, so this runs anywhere, and it catches the failure that
             actually happened: a published page showing a number that no
             current script produces. This is what CI runs.
  (default)  Adds the tables, the figures and the survival models. Needs
             data/processed/cohort_part3.csv.gz.
  --full     Adds Part 4. Fifteen minutes, so it is opt-in.

WHAT NONE OF THEM CHECK. Rebuilding the cohort itself from raw NHANES files
needs ~1 GB of downloads and a Postgres instance. Even --full therefore proves
the artefacts are internally consistent, not that they agree with the raw data;
the cohort builder is pinned separately by tests/ against synthetic fixtures.
Saying this out loud matters: a check whose limits are unstated gets read as
covering more than it does, and then relied on for the part it never covered.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PY).exists():
    PY = sys.executable

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# subprocess decodes with the system codepage, which on a Chinese Windows
# install is GBK. Several of these scripts print en dashes and Chinese, so the
# reader thread raised UnicodeDecodeError and the captured output came back
# empty -- meaning a genuine failure would have been reported with no message
# under it. errors="replace" so a mangled character never costs a diagnostic.
RUN = {"capture_output": True, "text": True,
       "encoding": "utf-8", "errors": "replace",
       "env": {**os.environ, "PYTHONIOENCODING": "utf-8"}}

# Ordered, because several of these read what the previous one wrote.
# render_report reads part4_learning_results.json; build_site reads the report;
# render_readme reads crosscheck_part3.csv and test_summary.json.
NEEDS_COHORT = ROOT / "data" / "processed" / "cohort_part3.csv.gz"

RENDER_STAGE = [("render", ["scripts/render_report.py",
                            "scripts/build_site.py",
                            "scripts/render_readme.py"])]
STAGES = [
    ("cohort", ["scripts/build_cohort_results.py"]),
    ("descriptive", ["scripts/build_descriptive_results.py",
                     "scripts/build_ascertainment_results.py",
                     "scripts/build_missingness_results.py",
                     "scripts/make_descriptive_figures.py"]),
    ("benchmark", ["scripts/pce_variable_cascade.py",
                   "scripts/check_fouryear_weights.py",
                   "scripts/build_tableau_extract.py"]),
    ("models", ["scripts/fit_survival_models.py",
                "scripts/make_survival_figures.py"]),
] + RENDER_STAGE
FULL_ONLY = [("learning", ["scripts/build_learning_results.py",
                           "scripts/make_learning_figures.py"])]

# PNGs are excluded from the diff. Matplotlib embeds a creation timestamp and
# the exact bytes depend on the freetype build, so a byte comparison would fail
# on a clean machine for reasons that have nothing to do with the numbers. The
# figures are driven by the same tables this check does compare, so a real
# change shows up there.
IGNORE_SUFFIXES = {".png", ".jpg", ".pdf"}
# Written by the test suite, not by the pipeline; its value depends on whether
# tests ran, which is not what this check is about.
IGNORE_PATHS = {"reports/test_summary.json"}


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, **RUN)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout


def dirty() -> list[str]:
    """Tracked files that differ from HEAD, excluding what cannot be compared."""
    out = []
    for line in git("status", "--porcelain").splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:                       # a rename; take the destination
            path = path.split(" -> ", 1)[1]
        if path in IGNORE_PATHS:
            continue
        if Path(path).suffix.lower() in IGNORE_SUFFIXES:
            continue
        out.append(f"{line[:2]} {path}")
    return sorted(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true",
                    help="rebuild only the report, site and README; needs no "
                         "data beyond what is committed")
    ap.add_argument("--full", action="store_true",
                    help="also rebuild Part 4 (~15 minutes)")
    args = ap.parse_args()
    if args.render and args.full:
        raise SystemExit("--render and --full ask for different scopes; pick one.")
    if not args.render and not NEEDS_COHORT.exists():
        raise SystemExit(
            f"{NEEDS_COHORT.relative_to(ROOT)} is not present, and every stage "
            f"except the renderers reads it. It is gitignored, so a fresh "
            f"checkout will never have it.\n\n"
            f"Run `python scripts/verify_clean_rebuild.py --render` for the "
            f"part that needs no data, or `make cohort` to build it.")

    before = dirty()
    if before:
        # Running the rebuild on a dirty tree would report the user's own edits
        # as a rebuild failure, which is the fastest way to teach someone that
        # this check cries wolf.
        raise SystemExit(
            "the working tree already has uncommitted changes, so a diff after "
            "the rebuild would not mean anything:\n  "
            + "\n  ".join(before)
            + "\n\nCommit or stash them first.")

    if args.render:
        stages = RENDER_STAGE
    elif args.full:
        stages = STAGES[:2] + FULL_ONLY + STAGES[2:]
    else:
        stages = STAGES
    for name, scripts in stages:
        log.info(f"── {name}")
        for s in scripts:
            log.info(f"   {s}")
            r = subprocess.run([PY, s], cwd=ROOT, **RUN)
            if r.returncode != 0:
                tail = "\n".join((r.stderr or r.stdout).splitlines()[-25:])
                raise SystemExit(f"\n{s} failed:\n{tail}")

    after = dirty()
    if after:
        log.error("\nA clean rebuild changed tracked files:\n  " + "\n  ".join(after))
        log.error("\nEvery one of these is a committed artefact that no longer "
                  "matches the code that writes it. Either the artefact is "
                  "stale -- commit the regenerated one -- or the code changed "
                  "and the published pages have been showing the old number "
                  "since. Diff them before deciding which.")
        if not args.full:
            log.error("\n(Part 4 was not rebuilt. Re-run with --full if a "
                      "part4_* artefact is in the list above.)")
        raise SystemExit(1)

    scope = "including Part 4" if args.full else "excluding Part 4 (use --full)"
    log.info(f"\nClean rebuild reproduces every tracked artefact, {scope}.")


if __name__ == "__main__":
    main()
