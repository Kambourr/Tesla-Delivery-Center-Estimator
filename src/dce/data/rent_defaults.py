"""Curated industrial asking-rent seed (no scrapers).

Contract
--------
Load the bundled CBSA industrial asking-rent table. Each row has ``cbsa``,
``property_type`` (industrial / flex / retail / auto_service),
``rent_psf_year``, ``as_of``, ``citation``, and ``broker``.

Figures are manually curated headline rents with citations. This module
does not download, scrape, or parse LoopNet, Crexi, CoStar, or broker PDFs.
``read_rent_model`` loads the frozen ACS adjustment coefficients.

The shipped seed has the San Mateo Peninsula industrial headline and the
``acs_rent_v1`` coefficients. It does not invent a national industrial rent.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


class RentSeedError(ValueError):
    """The rent seed file is missing or malformed."""


@dataclass(frozen=True)
class CbsaRentSeed:
    """One metro industrial asking-rent headline from a cited public report."""

    cbsa: str
    property_type: str
    rent_psf_year: float
    as_of: str
    citation: str
    broker: str


@dataclass(frozen=True)
class RentModelSeed:
    """Frozen adjustment coefficients. See ``formula_json`` keys in the file."""

    model_id: str
    formula_json: str
    trained_on: str
    as_of: str


def read_rent_seed(path: Path) -> tuple[CbsaRentSeed, ...]:
    """Read the bundled rent CSV. Does not open SQLite and does not download."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RentSeedError(f"Could not read the rent seed: {path}.") from exc
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise RentSeedError(f"Rent seed {path} has no rows.")
    parsed: list[CbsaRentSeed] = []
    for row in rows:
        cbsa = _text(row, "cbsa")
        if len(cbsa) != 5 or not cbsa.isdigit():
            raise RentSeedError(f"Rent seed CBSA must be 5 digits, got {cbsa!r}.")
        parsed.append(
            CbsaRentSeed(
                cbsa=cbsa,
                property_type=_text(row, "property_type"),
                rent_psf_year=_positive(row, "rent_psf_year"),
                as_of=_text(row, "as_of"),
                citation=_text(row, "citation"),
                broker=_text(row, "broker"),
            )
        )
    return tuple(parsed)


def read_rent_model(path: Path) -> RentModelSeed:
    """Read the coefficient JSON. The whole object is stored as ``formula_json``."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RentSeedError(f"Could not read the rent model: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise RentSeedError(f"Rent model is not valid JSON: {path}.") from exc
    if not isinstance(raw, dict):
        raise RentSeedError("Rent model must be a JSON object.")
    model_id = raw.get("model_id")
    trained_on = raw.get("trained_on")
    as_of = raw.get("as_of")
    if not isinstance(model_id, str) or model_id.strip() == "":
        raise RentSeedError("Rent model needs model_id.")
    if not isinstance(trained_on, str) or trained_on.strip() == "":
        raise RentSeedError("Rent model needs trained_on.")
    if not isinstance(as_of, str) or as_of.strip() == "":
        raise RentSeedError("Rent model needs as_of.")
    return RentModelSeed(
        model_id=model_id.strip(),
        formula_json=json.dumps(raw, sort_keys=True),
        trained_on=trained_on.strip(),
        as_of=as_of.strip(),
    )


def _text(row: dict[str, str | None], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise RentSeedError(f"Rent seed is missing {key}.")
    return value.strip()


def _positive(row: dict[str, str | None], key: str) -> float:
    text = _text(row, key)
    try:
        number = float(text)
    except ValueError as exc:
        raise RentSeedError(f"Rent seed {key} is not a number: {text!r}.") from exc
    if number < 0:
        raise RentSeedError(f"Rent seed {key} must be >= 0.")
    return number
