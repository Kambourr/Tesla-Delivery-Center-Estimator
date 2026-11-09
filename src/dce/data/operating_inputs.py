"""Resolved rent and utility rates for the San Mateo demo.

The rent fallback chain and the EIA / OpenEI loaders are a later milestone.
Until they land, ``estimate`` reads this committed file so a ZIP alone still
produces a rent and a tariff. The figures are the public ones the San Mateo
research case used. This module does not open SQLite and does not use the
network.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from dce.config import demo_data_dir


class OperatingInputError(ValueError):
    """The committed San Mateo operating-input file is missing or malformed."""


@dataclass(frozen=True)
class OperatingInputs:
    """Dollars the cost model needs and that the user does not type."""

    rent_psf_month: float
    energy_rate_kwh: float
    demand_rate_kw: float
    rent_citation: str
    energy_citation: str
    as_of: str


def san_mateo_operating_path() -> Path:
    """Return ``data/demo/san_mateo/operating_inputs.json``."""
    return demo_data_dir() / "san_mateo" / "operating_inputs.json"


def load_san_mateo_operating_inputs(path: Path | None = None) -> OperatingInputs:
    """Read the committed San Mateo rent and PG&E B-10 rates."""
    source = san_mateo_operating_path() if path is None else path
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OperatingInputError(f"Could not read operating inputs: {source}.") from exc
    except json.JSONDecodeError as exc:
        raise OperatingInputError(f"Operating inputs are not valid JSON: {source}.") from exc
    if not isinstance(raw, dict):
        raise OperatingInputError("Operating inputs must be a JSON object.")
    return OperatingInputs(
        rent_psf_month=_non_negative(raw, "rent_psf_month"),
        energy_rate_kwh=_non_negative(raw, "energy_rate_kwh"),
        demand_rate_kw=_non_negative(raw, "demand_rate_kw"),
        rent_citation=_text(raw, "rent_citation"),
        energy_citation=_text(raw, "energy_citation"),
        as_of=_text(raw, "as_of"),
    )


def _non_negative(raw: dict[str, object], key: str) -> float:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise OperatingInputError(f"Operating inputs field {key} must be a finite number.")
    if value < 0:
        raise OperatingInputError(f"Operating inputs field {key} must be >= 0.")
    return float(value)


def _text(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise OperatingInputError(f"Operating inputs field {key} must be text.")
    return value.strip()
