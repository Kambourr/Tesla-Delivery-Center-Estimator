"""``python -m dce`` entry point. Delegates to :func:`dce.cli.main`."""

from __future__ import annotations

import sys

from dce.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
