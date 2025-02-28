#!/usr/bin/python3

import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__)
if SCRIPT_PATH.is_symlink():
    SCRIPT_PATH = SCRIPT_PATH.readlink()
sys.path.append(str(SCRIPT_PATH.parent / "src"))

from mactime.cli import main  # type: ignore  # noqa: E402

if __name__ == "__main__":
    main()
