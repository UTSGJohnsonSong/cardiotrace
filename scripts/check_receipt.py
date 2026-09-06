"""Fail closed when a release no longer matches its full-rebuild evidence."""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "reports/verify_receipt.json"
STAGES = {"cohort", "descriptive", "learning", "benchmark", "models", "render"}


def check(root=ROOT):
    root = Path(root)
    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise ValueError(f"Cannot verify receipt history: {result.stderr.strip()}")
        return result.stdout.strip()
    try:
        full = json.loads((root / RECEIPT).read_text(encoding="utf-8"))["full"]
        sha = full["commit"]
        if full["result"] != "clean" or set(full["stages"]) != STAGES:
            raise ValueError("Full receipt does not cover the complete analysis")
        if not full["ran_at"] or not full["covers"]:
            raise ValueError("Full receipt lacks run metadata")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Missing or invalid full receipt; run verify_clean_rebuild.py --full") from exc
    if git("rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("Receipt gate requires full git history")
    git("merge-base", "--is-ancestor", sha, "HEAD")
    changed = set(git("diff", "--name-only", sha, "HEAD").splitlines()) - {RECEIPT}
    if changed:
        raise ValueError(f"Stale full receipt: changed since verification: {sorted(changed)}")
    dirty = set(git("diff", "HEAD", "--name-only").splitlines()) - {
        RECEIPT, "reports/test_summary.json"}
    if dirty:
        raise ValueError(f"Uncommitted changes are not verified: {sorted(dirty)}")
    return full


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        full = check()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Full receipt matches the release tree: {full['commit']}")


if __name__ == "__main__":
    main()

