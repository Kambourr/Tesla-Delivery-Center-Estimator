"""Print dist/app-report.json and, on GitHub Actions, the step summary.

The macOS app workflow runs this after ``make app-bundle``. It does not
build or upload anything.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    path = Path("dist/app-report.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(report, indent=2)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if summary:
        rows = report.get("rows")
        clicks = report.get("click_ms")
        lines = [
            "## Delivery Center Estimator app",
            "",
            f"- .app size: {report.get('app_bytes')} bytes",
            f"- Results database: {report.get('results_db_bytes')} bytes",
            f"- Precompute runtime: {report.get('precompute_seconds')} seconds",
            f"- Rows: `{json.dumps(rows)}`",
            f"- Cold start: {report.get('cold_start_ms')} ms",
            f"- Click latency: `{json.dumps(clicks)}`",
            f"- Opened from: {report.get('opened_from')}",
            "",
        ]
        Path(summary).write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
