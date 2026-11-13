"""Pick the version for the next release and write it into deadlock_advisor/__init__.py.

Used by .github/workflows/release.yml: every push to main ships a release, so the
version has to move even when nobody bumped it by hand.
  * __init__.py ahead of every v* tag  -> use it as is (a manual minor/major bump).
  * otherwise                          -> latest tag with the patch number + 1.
Prints `version=X.Y.Z` (the GITHUB_OUTPUT format). The bump is not committed back:
the release tag records it, so CI never pushes to main and never loops.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parent.parent / "src" / "deadlock_advisor" / "__init__.py"
VERSION_RE = re.compile(r'__version__ = "([^"]+)"')


def parse(v: str) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def next_version(declared: str, tags: list[str]) -> str:
    base = parse(declared)
    if base is None:
        raise ValueError(f"__version__ inválida: {declared!r}")
    released = sorted(t for t in map(parse, tags) if t)
    if not released or base > released[-1]:
        return "%d.%d.%d" % base
    major, minor, patch = released[-1]
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    text = INIT.read_text(encoding="utf-8")
    declared = VERSION_RE.search(text).group(1)
    tags = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True, text=True,
                          check=True).stdout.split()
    version = next_version(declared, tags)
    INIT.write_text(VERSION_RE.sub(f'__version__ = "{version}"', text), encoding="utf-8")
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
