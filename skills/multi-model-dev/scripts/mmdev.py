from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    if not (repo_root / "mmdev" / "cli.py").exists():
        print("Could not locate repository tokenpatch CLI.", file=sys.stderr)
        return 2
    args = [sys.executable, "-m", "mmdev.cli", *sys.argv[1:]]
    completed = subprocess.run(args, cwd=repo_root, timeout=3600, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
