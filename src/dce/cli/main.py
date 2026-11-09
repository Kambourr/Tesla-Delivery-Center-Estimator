"""Headless command-line entry.

Contract
--------
``python -m dce --help`` prints usage and exits 0.

``dce estimate 94402`` runs :func:`dce.orchestrator.estimate` and prints a
text summary. ``--json`` prints the same result as JSON, including both
DCF yearly tables. The only required input is a US ZIP. This module must
not import ``dce.extract.pdf_llm``.
"""

from __future__ import annotations

import argparse
import sys

from dce import __version__
from dce.cli.report import render_json, render_text
from dce.data.catchment_demand import CatchmentDemandError
from dce.data.operating_inputs import OperatingInputError
from dce.geo.resolve import ZipResolutionError
from dce.model.errors import ModelError
from dce.orchestrator import EstimateDataError, estimate


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser. ``--help`` exits 0 via argparse."""
    parser = argparse.ArgumentParser(
        prog="dce",
        description=(
            "Tesla Delivery-Center Estimator (public data only). "
            "Given a US ZIP, estimate the gravity catchment, cost per delivery, "
            "the top three cost drivers, and a discounted cash flow with both "
            "benefit views. No Tesla internal data and no network on this path."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command")
    estimate_parser = commands.add_parser(
        "estimate",
        help="Estimate a delivery center for one US ZIP.",
    )
    estimate_parser.add_argument("zip_code", help="5-digit US ZIP, for example 94402.")
    estimate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full result as JSON, including both yearly cash-flow tables.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and, for ``estimate``, print the result.

    ``--help`` and ``--version`` are handled by argparse and raise
    ``SystemExit`` before this function returns.
    """
    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().print_help()
        return 0
    try:
        result = estimate(args.zip_code)
    except (
        ZipResolutionError,
        EstimateDataError,
        CatchmentDemandError,
        OperatingInputError,
        ModelError,
    ) as exc:
        print(f"dce: {exc}", file=sys.stderr)
        return 2
    print(render_json(result) if args.json else render_text(result))
    return 0
