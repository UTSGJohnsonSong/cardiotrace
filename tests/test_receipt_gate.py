"""A release gate must reject stale evidence even when unit tests pass."""
import json
import subprocess

import pytest

from scripts.check_receipt import check, STAGES


@pytest.fixture
def repository(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()
    git("init")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Receipt fixture")
    (tmp_path / "analysis.py").write_text("first\n")
    git("add", ".")
    git("commit", "-m", "analysis")
    sha = git("rev-parse", "HEAD")
    (tmp_path / "reports").mkdir()
    receipt = tmp_path / "reports/verify_receipt.json"
    receipt.write_text(json.dumps({"full": {"commit": sha, "result": "clean",
        "stages": sorted(STAGES), "ran_at": "fixture", "covers": "all stages"}}))
    git("add", ".")
    git("commit", "-m", "receipt only")
    return tmp_path, git, receipt, sha


def test_receipt_only_commit_preserves_verification(repository):
    root, _, _, sha = repository
    assert check(root)["commit"] == sha


@pytest.mark.parametrize("committed", [False, True])
def test_source_changes_invalidate_receipt(repository, committed):
    root, git, _, _ = repository
    (root / "analysis.py").write_text("different result\n")
    if committed:
        git("add", ".")
        git("commit", "-m", "changed after verification")
    with pytest.raises(ValueError, match="Stale|Uncommitted"):
        check(root)


@pytest.mark.parametrize("fault", ["absent", "missing_stage", "unknown_commit", "not_ancestor"])
def test_invalid_evidence_fails_closed(repository, fault):
    root, git, path, _ = repository
    book = json.loads(path.read_text())
    if fault == "absent":
        book = {}
    elif fault == "missing_stage":
        book["full"]["stages"] = ["render"]
    elif fault == "unknown_commit":
        book["full"]["commit"] = "f" * 40
    else:
        verified_head = git("rev-parse", "HEAD")
        (root / "analysis.py").write_text("future change\n")
        git("add", ".")
        git("commit", "-m", "future")
        book["full"]["commit"] = git("rev-parse", "HEAD")
        git("checkout", verified_head)
    path.write_text(json.dumps(book))
    with pytest.raises(ValueError):
        check(root)

