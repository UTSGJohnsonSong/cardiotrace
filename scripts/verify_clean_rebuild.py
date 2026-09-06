"""
Verify that rebuilding the selected scope changes no tracked text artefacts.

--render needs only committed inputs: report, site, README and handover.
Default/full scopes verify raw NHANES and mortality SHA-256 manifests, then
rebuild the cohort from raw files, descriptive results, benchmarks, models and
renderers. --full additionally rebuilds Part 4 before the benchmark/renderers.
They do not redownload data or run R/Postgres/dbt. Raw-data truth and scientific
validity are not established by a reproducible build. Image/PDF bytes are
excluded because font/rendering environments vary; numerical tables are checked.

A successful run records scope, commit, environment and time in the receipt.
Commit only that receipt afterward. check_receipt.py independently enforces
freshness in CI and packaging; unit tests alone are not a release gate.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import platform
from importlib.metadata import version, PackageNotFoundError
from datetime import datetime, timezone
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
RENDER_STAGE = [("render", ["scripts/render_report.py",
                            "scripts/build_site.py",
                            "scripts/render_readme.py",
                            "scripts/render_handover.py",
                            "scripts/render_research_summary.py"])]
STAGES = [
    ("cohort", ["scripts/build_cohort_results.py"]),
    ("descriptive", ["scripts/build_descriptive_results.py",
                     "scripts/build_ascertainment_results.py",
                     "scripts/build_missingness_results.py",
                     "scripts/make_descriptive_figures.py"]),
    ("benchmark", ["scripts/pce_variable_cascade.py",
                   "scripts/build_pce_results.py",
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
IGNORE_PATHS = {"reports/test_summary.json", "reports/verify_receipt.json"}

# What ran, when, at which commit, over which scope. Written because
# docs/impact-tracking.md carried a hand-maintained table of exactly those four
# facts, and the first version of that table was wrong: it cited a --full run
# four commits stale, one of which had changed a renderer. A merge gate whose
# evidence is somebody's memory is the failure this project keeps rediscovering.
# Excluded from the diff for the same reason test_summary.json is: it describes
# the run rather than being produced by the pipeline.
RECEIPT = ROOT / "reports" / "verify_receipt.json"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, **RUN)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr}")
    return r.stdout


def dirty() -> tuple[list[str], list[str]]:
    """(changed tracked files, untracked files), excluding the incomparable.

    The two are kept apart because they mean different things and the same
    sentence cannot explain both. A modified tracked file is an artefact that no
    longer matches the code. An untracked file is something the rebuild
    PRODUCED that nobody committed -- or, just as often, an unrelated file
    someone left in the tree, which is not a rebuild failure at all. Reporting
    the second as the first is how a check earns a reputation for false alarms.
    """
    changed, untracked = [], []
    for line in git("status", "--porcelain").splitlines():
        code, path = line[:2], line[3:].strip().strip('"')
        if " -> " in path:                       # a rename; take the destination
            path = path.split(" -> ", 1)[1]
        if path in IGNORE_PATHS:
            continue
        if Path(path).suffix.lower() in IGNORE_SUFFIXES:
            continue
        (untracked if code == "??" else changed).append(f"{code} {path}")
    return sorted(changed), sorted(untracked)


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
    if not args.render and not (ROOT / "data/raw").exists():
        raise SystemExit(
            f"data/raw is not present. The cohort stage rebuilds from raw inputs. "
            f"Raw files are gitignored, so a fresh checkout will not have them.\n\n"
            f"Run `python scripts/verify_clean_rebuild.py --render` for the "
            f"part that needs no data, or `make data` to download the inputs.")

    before, before_untracked = dirty()
    if before:
        # Running the rebuild on a dirty tree would report the user's own edits
        # as a rebuild failure, which is the fastest way to teach someone that
        # this check cries wolf.
        raise SystemExit(
            "the working tree already has uncommitted changes, so a diff after "
            "the rebuild would not mean anything:\n  "
            + "\n  ".join(before)
            + "\n\nCommit or stash them first.")
    # Untracked files present BEFORE the run are the user's, not the rebuild's.
    # Recorded rather than refused, so that a file created while a fifteen-minute
    # rebuild is running does not get reported as a stale artefact afterwards --
    # which is exactly what happened the first time this ran to completion.
    preexisting = set(before_untracked)

    if not args.render:
        for script in ["data/download_from_catalog.py", "data/download_mortality.py"]:
            r = subprocess.run([PY, script, "--verify"], cwd=ROOT, **RUN)
            if r.returncode:
                raise SystemExit(f"Raw input verification failed: {script}\n{r.stdout}\n{r.stderr}")
        log.info("Raw NHANES and mortality files match their SHA-256 manifests.")

    if args.render:
        stages = RENDER_STAGE
    elif args.full:
        # Spliced by NAME, not by index. `STAGES[:2] + FULL_ONLY + STAGES[2:]`
        # was correct only while "benchmark" happened to sit at index 2, and
        # inserting any stage above it would have moved `learning` after
        # `render` -- so render_report.py would read the PREVIOUS
        # part4_learning_results.json and the check would report a clean rebuild
        # having rebuilt in the wrong order. Naming it raises instead.
        at = [n for n, _ in STAGES].index("benchmark")
        stages = STAGES[:at] + FULL_ONLY + STAGES[at:]
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

    after, after_untracked = dirty()
    produced = [u for u in after_untracked if u not in preexisting]
    if produced:
        # Not a failure on its own: the rebuild wrote a file that is not in the
        # repository. That is worth saying -- a published number could be read
        # from it while no checkout has it -- but it is a different fault from a
        # stale artefact, so it gets its own sentence and does not exit 1.
        log.warning("\nThe rebuild produced files that are not tracked:\n  "
                    + "\n  ".join(produced))
        log.warning("If any of these feeds a published page, commit it; a fresh "
                    "checkout does not have it.")
    if after:
        log.error("\nA clean rebuild changed tracked files:\n  " + "\n  ".join(after))
        log.error("\nEvery one of these is a committed artefact that no longer "
                  "matches the code that writes it. Either the artefact is "
                  "stale -- commit the regenerated one -- or the code changed "
                  "and the published pages have been showing the old number "
                  "since. Diff them before deciding which.")
        if args.render:
            log.error("\nOnly the renderers ran. A table or a JSON result in "
                      "the list above means that artefact is stale relative to "
                      "the code that writes it, and this scope cannot tell you "
                      "which -- rerun without --render on a machine that has "
                      "data/processed/cohort_part3.csv.gz.")
        elif not args.full:
            log.error("\n(Part 4 was not rebuilt. Re-run with --full if a "
                      "part4_* artefact is in the list above.)")
        raise SystemExit(1)

    # Naming the scope is the point. A pass that says more than it checked is
    # worse than no check: the render scope touches three files and would
    # happily report "every tracked artefact" while every table went unexamined.
    scope = ("the report, site, README, handover status and research summary, and nothing else"
             if args.render else
             "generated text from cohort, descriptive, learning, benchmark, models and render stages; "
             "image bytes, independent R and optional warehouse excluded" if args.full else
             "generated text from cohort, descriptive, benchmark, models and render stages; "
             "Part 4, image bytes, independent R and optional warehouse excluded")
    log.info(f"\nClean rebuild reproduces {scope}.")

    # Keyed BY SCOPE, so a one-minute --render in CI cannot erase the evidence
    # of a fifteen-minute --full. The first version of this file wrote a single
    # object and the very next --render overwrote the --full receipt the merge
    # gate had just been pointed at -- turning the cheapest run into the one
    # that decides what the repository claims to have verified.
    name = "render" if args.render else "full" if args.full else "default"
    book = {}
    if RECEIPT.exists():
        try:
            book = json.loads(RECEIPT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            book = {}
        if not isinstance(book, dict) or "scope" in book:
            book = {}          # the old single-object shape; start the book over
    book[name] = {
        "commit": git("rev-parse", "HEAD").strip(),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stages": [s for s, _ in stages],
        "result": "clean",
        "covers": scope,
        "environment": environment(),
        "raw_manifest_checks": not args.render,
    }
    RECEIPT.write_text(
        json.dumps(dict(sorted(book.items())), indent=2) + "\n",
        encoding="utf-8")
    log.info(f"receipt -> {RECEIPT.relative_to(ROOT)} [{name}]")


def environment():
    packages = {}
    for name in ["numpy", "pandas", "scipy", "scikit-learn", "lifelines",
                 "statsmodels", "pyreadstat", "matplotlib", "seaborn",
                 "pytest", "formulaic", "autograd"]:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not installed"
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": packages}


if __name__ == "__main__":
    main()
