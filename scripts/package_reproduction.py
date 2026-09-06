"""Archive an exact clean committed tree, plus checksums; never include raw data."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dest = args.output.resolve()
    if dest.is_relative_to(ROOT):
        raise SystemExit("Write the snapshot outside the repository")
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit all changes and the verification receipt before packaging")
    if dest.exists():
        raise SystemExit(f"Refusing to overwrite an existing snapshot: {dest}")
    sha = git("rev-parse", "HEAD").decode().strip()
    files = git("ls-tree", "-r", "--name-only", "-z", "HEAD").decode().strip("\0").split("\0")
    manifest = {"commit": sha, "files": {}}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.startswith(("data/raw/", "data/processed/", ".venv/")) or Path(path).name == ".env":
                raise SystemExit(f"Unexpected private/local tracked input: {path}")
            content = git("show", f"HEAD:{path}")
            manifest["files"][path] = hashlib.sha256(content).hexdigest()
            info = zipfile.ZipInfo(f"cardiotrace/{path}", date_time=(2026, 9, 6, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
        archive.writestr("cardiotrace/SNAPSHOT_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    print(f"{dest}: {len(files)} tracked files, source {sha}")


if __name__ == "__main__":
    main()
