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

``read_rent_market_seed`` loads ``rent_market.csv``: broker market-report
asking rents by county or CBSA (CBRE, Cushman & Wakefield, Colliers, JLL,
Newmark). Each row keeps the figure exactly as the report prints it
(``reported_rent``, ``reported_unit``, ``reported_basis``) and the annual NNN
equivalent the resolver uses (``rent_psf_year``). The reader recomputes that
equivalent with :func:`nnn_rent_psf_year` and rejects a row that disagrees:

- ``usd_psf_month`` is multiplied by 12. ``usd_psf_year`` is used as is.
- ``nnn`` (net, triple net, industrial gross treated as net by the report)
  is used as is.
- ``full_service_gross`` is divided by ``1 + GROSS_TO_NNN_LOAD`` (0.15, the
  shipped ``facility.opex_load`` base). The model adds the NNN load back on
  top of rent, so the base lease line equals the gross asking figure instead
  of counting operating costs and taxes twice.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

GROSS_TO_NNN_LOAD = 0.15
"""Operating-cost share removed from a full-service gross asking rent.

Equal to the shipped ``facility.opex_load`` base in ``assumptions.yaml``.
Fixed here so the seed conversion does not move when a ZIP's NNN load does.
"""

MARKET_LEVELS = ("county", "cbsa")
MARKET_UNITS = ("usd_psf_year", "usd_psf_month")
MARKET_BASES = ("nnn", "full_service_gross")
MARKET_PROPERTY_TYPES = ("industrial_flex", "industrial_overall", "office_showroom_proxy")
_MARKET_TOLERANCE = 0.005


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
class MarketRentSeed:
    """One broker market-report asking rent for a county or CBSA.

    ``rent_psf_year`` is the annual NNN equivalent. The ``reported_*`` fields
    are the figure as printed. ``property_type`` is ``industrial_flex`` (the
    report's flex / R&D / high-tech rent), ``industrial_overall`` (all
    industrial types, used when the report has no flex rent for that
    geography), or ``office_showroom_proxy`` (a market with no tracked
    industrial inventory, such as Manhattan).
    """

    geography_level: str
    geography_id: str
    market: str
    submarket: str
    property_type: str
    rent_psf_year: float
    reported_rent: float
    reported_unit: str
    reported_basis: str
    source: str
    report: str
    quarter: str
    as_of: str
    url: str
    note: str


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


def nnn_rent_psf_year(reported_rent: float, unit: str, basis: str) -> float:
    """Convert a printed asking rent to annual NNN dollars per square foot."""
    if unit not in MARKET_UNITS:
        raise RentSeedError(f"Market rent unit must be one of {MARKET_UNITS}, got {unit!r}.")
    if basis not in MARKET_BASES:
        raise RentSeedError(f"Market rent basis must be one of {MARKET_BASES}, got {basis!r}.")
    annual = reported_rent * 12.0 if unit == "usd_psf_month" else reported_rent
    if basis == "full_service_gross":
        annual = annual / (1.0 + GROSS_TO_NNN_LOAD)
    return annual


def read_rent_market_seed(path: Path) -> tuple[MarketRentSeed, ...]:
    """Read ``rent_market.csv``. Does not open SQLite and does not download.

    Rows come back sorted by ``(geography_level, geography_id)``. A geography
    may appear once. ``rent_psf_year`` must match :func:`nnn_rent_psf_year`
    of the reported figure to within half a cent.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RentSeedError(f"Could not read the market rent seed: {path}.") from exc
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise RentSeedError(f"Market rent seed {path} has no rows.")
    parsed: dict[tuple[str, str], MarketRentSeed] = {}
    for row in rows:
        level = _text(row, "geography_level")
        if level not in MARKET_LEVELS:
            raise RentSeedError(f"Market rent geography_level must be county or cbsa: {level!r}.")
        geo_id = _text(row, "geography_id")
        if len(geo_id) != 5 or not geo_id.isdigit():
            raise RentSeedError(f"Market rent geography_id must be 5 digits, got {geo_id!r}.")
        property_type = _text(row, "property_type")
        if property_type not in MARKET_PROPERTY_TYPES:
            raise RentSeedError(
                f"Market rent property_type must be one of {MARKET_PROPERTY_TYPES}, "
                f"got {property_type!r}."
            )
        reported = _positive(row, "reported_rent")
        unit = _text(row, "reported_unit")
        basis = _text(row, "reported_basis")
        expected = nnn_rent_psf_year(reported, unit, basis)
        stored = _positive(row, "rent_psf_year")
        if reported <= 0 or abs(stored - expected) > _MARKET_TOLERANCE:
            raise RentSeedError(
                f"Market rent for {level} {geo_id} is {stored:g}, but {reported:g} "
                f"{unit} {basis} converts to {expected:.4f}."
            )
        key = (level, geo_id)
        if key in parsed:
            raise RentSeedError(f"Market rent seed lists {level} {geo_id} twice.")
        parsed[key] = MarketRentSeed(
            geography_level=level,
            geography_id=geo_id,
            market=_text(row, "market"),
            submarket=_text(row, "submarket"),
            property_type=property_type,
            rent_psf_year=stored,
            reported_rent=reported,
            reported_unit=unit,
            reported_basis=basis,
            source=_text(row, "source"),
            report=_text(row, "report"),
            quarter=_text(row, "quarter"),
            as_of=_text(row, "as_of"),
            url=_url(row),
            note=_text(row, "note"),
        )
    return tuple(parsed[key] for key in sorted(parsed))


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


def _url(row: dict[str, str | None]) -> str:
    value = _text(row, "url")
    if not value.startswith("https://"):
        raise RentSeedError(f"Market rent url must be https, got {value!r}.")
    return value


def _positive(row: dict[str, str | None], key: str) -> float:
    text = _text(row, key)
    try:
        number = float(text)
    except ValueError as exc:
        raise RentSeedError(f"Rent seed {key} is not a number: {text!r}.") from exc
    if number < 0:
        raise RentSeedError(f"Rent seed {key} must be >= 0.")
    return number
