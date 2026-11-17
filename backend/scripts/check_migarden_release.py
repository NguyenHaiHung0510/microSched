"""Verify the final runtime filesystem excludes N01 provision and QA material."""

import argparse
import gzip
import os
from pathlib import Path

MARKER = b"N01_" + b"QA_ARTIFACT_CANARY"
DENIED_DIRECTORIES = {"tests", "e2e", "integrated", "fixtures", ".local", "qa", "test-results"}
DENIED_FILES = {"provision_migarden_qa.py", "migarden_qa_cell.py", "appcheck.env"}


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    for target in ("backend", "frontend/dist"):
        directory = root / target
        if not directory.is_dir():
            failures.append(f"missing {target}")
            continue
        for parent, folders, names in os.walk(directory):
            base = Path(parent)
            # Locked third-party distributions may legitimately ship their own tests.
            if base == directory and target == "backend" and ".venv" in folders:
                folders.remove(".venv")
            for name in set(folders) & DENIED_DIRECTORIES:
                failures.append(str((base / name).relative_to(root)))
                folders.remove(name)
            for name in names:
                path = base / name
                relative = path.relative_to(root)
                if (
                    name in DENIED_FILES
                    or name.endswith(".token")
                    or name.startswith("test_migarden_")
                    or name.startswith("n01-qa-")
                ):
                    failures.append(str(relative))
                    continue
                if path.suffix in {".js", ".mjs", ".json", ".html", ".webmanifest", ".py", ".gz"}:
                    content = path.read_bytes()
                    if path.suffix == ".gz":
                        content = gzip.decompress(content)
                    if MARKER in content:
                        failures.append(str(relative))
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    args = parser.parse_args()
    files = scan(args.app_root)
    if files:
        raise SystemExit("N01 release guard FAIL: " + ", ".join(sorted(files)))
    print("N01 release guard PASS: runtime and PWA exclude QA material")


if __name__ == "__main__":
    main()
