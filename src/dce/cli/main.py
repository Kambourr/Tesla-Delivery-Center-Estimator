"""Headless command-line entry.

Contract
--------
``python -m dce --help`` prints usage and exits 0.

When estimation exists, the only required input is a US ZIP code. Scenario
controls are presets, not free-text rent. This module must not import
``dce.extract.pdf_llm`` and must not put an LLM on the calculate path.

Milestone M0 parses arguments and prints a stub line. It does not estimate,
read SQLite, or make network calls.
"""

from __future__ import annotations

import argparse

from dce import __version__


def build_parser() -> argparse.ArgumentParser:
    """Return the M0 argument parser. ``--help`` exits 0 via argparse."""
    parser = argparse.ArgumentParser(
        prog="dce",
        description=(
            "Tesla Delivery-Center Estimator (public data only). "
            "Given a US ZIP, a later milestone will estimate cost per delivery, "
            "the top three cost drivers, and a customer-base map. "
            "This M0 build is a stub and does not estimate anything."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and print the M0 stub notice.

    ``--help`` and ``--version`` are handled by argparse and raise
    ``SystemExit`` before this function returns.
    """
    build_parser().parse_args(argv)
    print(
        "dce: stub CLI (milestone M0). Estimation is not implemented. No network calls were made."
    )
    return 0
