"""``python -m dce.app`` opens the desktop window. ``--smoke`` stays headless."""

from __future__ import annotations

import sys
import time

_PROCESS_START = time.perf_counter()

from dce.app.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], started=_PROCESS_START))
