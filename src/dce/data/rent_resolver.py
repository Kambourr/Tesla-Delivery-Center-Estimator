"""Automatic commercial rent for one ZIP.

Contract
--------
``resolve_rent(zip_code, conn) -> RentResolution``

The user does not type rent. Read SQLite only. No HTTP, no LLM, and no
LoopNet, Crexi, CoStar, CompStak, Reonomy, ATTOM, or Cherre.

Fallback chain, first hit wins:

1. ``broker_county``: broker market-report asking rent for this ZIP's county
   (``rent_market``, a borough or submarket such as Brooklyn or Nassau).
2. ``cbsa_raw``: observed CBSA industrial seed (``rent_cbsa``, the Kidder
   Mathews Peninsula row for 41884), unadjusted.
3. ``broker_cbsa``: broker market-report asking rent for this ZIP's CBSA or
   metro division (``rent_market``).
4. County median of GSA ``rent_zip_obs`` (source ``gsa``). The frozen
   ``acs_rent_v1`` factor is applied here only, because this ZIP's CBSA
   has no industrial seed.
5. State median of ``rent_cbsa`` industrial seeds, only when at least three
   distinct CBSA seeds in that state exist. One metro headline is not a
   state rent. ``rent_market`` rows do not feed this rung, so a metro rent
   never spreads to rural ZIPs in the same state.
6. National industrial row. The shipped seed has none.
7. HUD SAFMR 2-bedroom.
8. This ZCTA's ACS median gross rent.
9. County median of ZCTA ACS gross rents, then the CBSA median.
10. State median of ZCTA ACS gross rents.
11. National median of ZCTA ACS gross rents.

Steps 1 to 3 are observed broker rents. A residential ACS factor is never
applied on top of them. ``rent_market`` stores the annual NNN equivalent
(``dce.data.rent_defaults.nnn_rent_psf_year``). Confidence is high for an
industrial row and medium for ``office_showroom_proxy`` (Manhattan, where
the reports track no industrial stock).

Steps 7 through 11 are residential proxies. ``unit_sqft`` and
``commercial_residential_ratio`` convert a monthly rent to dollars per
square foot. The shipped ratio is 1. Confidence ``low``.

A broker row is not applied outside its county or CBSA. A ZIP with no
crosswalk row still fails. A ZIP with a crosswalk row resolves as long as
any ACS gross rent exists in the file.

The result is written to ``rent_resolved_cache``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from dce.storage.repository import (
    RentCacheRecord,
    RentCbsaRecord,
    RentMarketRecord,
    RentModelRecord,
    SafmrRecord,
    ZctaAcsRecord,
    ZctaCentroidRecord,
    acs_positive_rents_for_county,
    acs_positive_rents_for_state,
    acs_positive_rents_national,
    acs_positive_values_for_cbsa,
    cbsas_for_state,
    get_latest_safmr,
    get_latest_zcta_acs,
    get_rent_market,
    get_rent_model,
    get_zcta_centroid,
    latest_acs_year,
    list_rent_cbsa,
    list_rent_cbsa_for_codes,
    list_rent_zip_obs_for_zips,
    list_zip_cbsas,
    list_zip_counties,
    list_zip_zctas,
    upsert_rent_cache,
    zips_in_county,
)

RENT_MODEL_ID = "acs_rent_v1"
_STATE_SEED_MINIMUM = 3
_INDUSTRIAL = "industrial"
_PROXY_TYPE = "office_showroom_proxy"


@dataclass(frozen=True)
class RentResolution:
    """Resolved asking rent for one ZIP."""

    zip_code: str
    rent_psf_year: float
    rent_psf_month: float
    property_type: str
    tier: str
    confidence: str
    as_of: str
    citation: str


class RentResolutionError(ValueError):
    """Rent could not be resolved for this ZIP from the local database."""

    def __init__(self, zip_code: str, message: str) -> None:
        self.zip_code = zip_code
        super().__init__(message)


@dataclass(frozen=True)
class _Coeffs:
    model_id: str
    b_income: float
    b_density: float
    b_home_value: float
    b_acs_rent: float
    clamp_low: float
    clamp_high: float
    unit_sqft: float
    commercial_residential_ratio: float
    trained_on: str
    as_of: str


def resolve_rent(
    zip_code: str, conn: sqlite3.Connection, *, write_cache: bool = True
) -> RentResolution:
    """Resolve asking rent from SQLite. See the module docstring for the chain.

    ``write_cache`` stores the row in ``rent_resolved_cache``. A batch caller
    can skip that write. The number does not change.
    """
    code = _zip(zip_code)
    zcta_rows = list_zip_zctas(conn, code)
    counties = list_zip_counties(conn, code)
    if not zcta_rows or not counties:
        raise RentResolutionError(
            code,
            f"ZIP {code} is not in the local crosswalk, so rent cannot be resolved.",
        )
    zcta = zcta_rows[0].zcta
    county = counties[0]
    cbsa_rows = list_zip_cbsas(conn, code)
    cbsa = cbsa_rows[0].cbsa if cbsa_rows else ""
    acs = get_latest_zcta_acs(conn, zcta)
    centroid = get_zcta_centroid(conn, zcta, "2024")
    coeffs = _coeffs(get_rent_model(conn, RENT_MODEL_ID))
    references = _references(conn, cbsa, acs.year if acs is not None else None)
    seed = _industrial(list_rent_cbsa(conn, cbsa)) if cbsa else None
    factor, clamped, adjusted_inputs = _factor(acs, centroid, references, coeffs)

    county_market = get_rent_market(conn, "county", county.county_fips)
    if county_market is not None:
        return _store(conn, write_cache, _from_market(code, county_market, tier="broker_county"))

    if seed is not None:
        return _store(
            conn,
            write_cache,
            _from_base(
                code,
                seed.rent_psf_year,
                property_type=seed.property_type,
                tier="cbsa_raw",
                confidence="high",
                as_of=seed.as_of,
                citation=(
                    f"{seed.citation} Observed industrial asking rent for CBSA {cbsa}. "
                    "Not scaled by residential ACS rent."
                ),
                components={"base_rent_psf_year": seed.rent_psf_year, "broker": seed.broker},
            ),
        )

    cbsa_market = get_rent_market(conn, "cbsa", cbsa) if cbsa else None
    if cbsa_market is not None:
        return _store(conn, write_cache, _from_market(code, cbsa_market, tier="broker_cbsa"))

    gsa = _county_gsa(conn, county.county_fips)
    if gsa is not None:
        base, gsa_as_of, gsa_citation = gsa
        amount = base * factor if adjusted_inputs else base
        citation = gsa_citation
        if adjusted_inputs:
            citation = (
                f"{gsa_citation} ZIP-adjusted with {coeffs.model_id} "
                f"(factor {factor:.4f}) because CBSA {cbsa or 'none'} has no industrial seed."
            )
        return _store(
            conn,
            write_cache,
            _from_base(
                code,
                amount,
                property_type=_INDUSTRIAL,
                tier="county_gsa",
                confidence="medium",
                as_of=gsa_as_of,
                citation=citation,
                components={
                    "base_rent_psf_year": base,
                    "factor": factor if adjusted_inputs else 1.0,
                    "clamped": clamped,
                    "model_id": coeffs.model_id,
                },
            ),
        )

    state_rent = _state_industrial(conn, county.state)
    if state_rent is not None:
        amount, state_as_of, citation = state_rent
        return _store(
            conn,
            write_cache,
            _from_base(
                code,
                amount,
                property_type=_INDUSTRIAL,
                tier="state",
                confidence="medium",
                as_of=state_as_of,
                citation=citation,
                components={"base_rent_psf_year": amount},
            ),
        )

    national = _industrial(list_rent_cbsa(conn, "00000"))
    if national is not None:
        return _store(
            conn,
            write_cache,
            _from_base(
                code,
                national.rent_psf_year,
                property_type=national.property_type,
                tier="national",
                confidence="low",
                as_of=national.as_of,
                citation=national.citation,
                components={
                    "base_rent_psf_year": national.rent_psf_year,
                    "broker": national.broker,
                },
            ),
        )

    safmr = get_latest_safmr(conn, code)
    if safmr is not None:
        return _store(
            conn,
            write_cache,
            _residential(code, safmr.rent_2br_month, coeffs, safmr, tier="hud_safmr"),
        )

    if acs is not None and acs.median_gross_rent is not None and acs.median_gross_rent > 0:
        return _store(
            conn,
            write_cache,
            _residential(
                code,
                acs.median_gross_rent,
                coeffs,
                None,
                tier="acs_gross_rent",
                as_of=f"{acs.year}-12-31",
                citation=_acs_citation(
                    coeffs,
                    acs.year,
                    f"ZCTA {zcta}",
                    acs.median_gross_rent,
                    1,
                ),
            ),
        )

    year = acs.year if acs is not None else latest_acs_year(conn)
    if year is not None:
        for tier, scope, values in _acs_rent_ladder(
            conn, county.county_fips, cbsa, county.state, year
        ):
            monthly = _median(values)
            if monthly is None:
                continue
            return _store(
                conn,
                write_cache,
                _residential(
                    code,
                    monthly,
                    coeffs,
                    None,
                    tier=tier,
                    as_of=f"{year}-12-31",
                    citation=_acs_citation(coeffs, year, scope, monthly, len(values)),
                ),
            )

    raise RentResolutionError(
        code,
        f"ZIP {code} has a crosswalk row but no industrial seed, no SAFMR, "
        "and no ACS gross rent at the ZCTA, county, CBSA, state, or nation.",
    )


def _acs_rent_ladder(
    conn: sqlite3.Connection, county_fips: str, cbsa: str, state: str, year: int
) -> tuple[tuple[str, str, tuple[float, ...]], ...]:
    """Return ACS gross-rent pools below the ZIP's own ZCTA, in ladder order."""
    return (
        (
            "acs_gross_rent_county",
            f"county {county_fips}",
            _cached_rents(conn, "county", county_fips, year, acs_positive_rents_for_county),
        ),
        (
            "acs_gross_rent_cbsa",
            f"CBSA {cbsa or 'none'}",
            () if cbsa == "" else _cached_rents(conn, "cbsa", cbsa, year, None),
        ),
        (
            "acs_gross_rent_state",
            f"state {state}",
            _cached_rents(conn, "state", state, year, acs_positive_rents_for_state),
        ),
        (
            "acs_gross_rent_national",
            "the US",
            _cached_rents(conn, "national", "US", year, None),
        ),
    )


def _cached_rents(
    conn: sqlite3.Connection,
    kind: str,
    scope_id: str,
    year: int,
    loader: _RentLoader | None,
) -> tuple[float, ...]:
    key = (id(conn), kind, scope_id, year)
    cached = _ACS_RENTS.get(key)
    if cached is not None:
        return cached
    if kind == "cbsa":
        found = acs_positive_values_for_cbsa(conn, scope_id, year, "median_gross_rent")
    elif kind == "national":
        found = acs_positive_rents_national(conn, year)
    elif loader is None:
        found = ()
    else:
        found = loader(conn, scope_id, year)
    _ACS_RENTS[key] = found
    return found


def _acs_citation(coeffs: _Coeffs, year: int, scope: str, monthly: float, count: int) -> str:
    return (
        f"ACS 5-year {year} B25064_001E median gross rent for {scope}, "
        f"${monthly:.0f} per month across {count} ZCTA"
        f"{'' if count == 1 else 's'}, converted with {coeffs.model_id} "
        f"unit_sqft {coeffs.unit_sqft:g} and commercial_residential_ratio "
        f"{coeffs.commercial_residential_ratio:g}. Residential proxy, confidence low."
    )


def _from_market(
    zip_code: str, row: RentMarketRecord, *, tier: str
) -> tuple[RentResolution, dict[str, object]]:
    unit = "per month" if row.reported_unit == "usd_psf_month" else "per year"
    basis = "full-service gross" if row.reported_basis == "full_service_gross" else "NNN"
    return _from_base(
        zip_code,
        row.rent_psf_year,
        property_type=row.property_type,
        tier=tier,
        confidence="medium" if row.property_type == _PROXY_TYPE else "high",
        as_of=row.as_of,
        citation=(
            f"{row.source} {row.report}, {row.submarket} ({row.market}): "
            f"${row.reported_rent:.2f} per square foot {unit}, {basis}, "
            f"= ${row.rent_psf_year:.2f} per square foot per year NNN. {row.note} "
            f"{row.url} Observed {row.property_type} asking rent for "
            f"{row.geography_level} {row.geography_id}. Not scaled by residential ACS rent."
        ),
        components={
            "base_rent_psf_year": row.rent_psf_year,
            "broker": row.source,
            "geography_level": row.geography_level,
            "geography_id": row.geography_id,
            "quarter": row.quarter,
            "reported_basis": row.reported_basis,
            "reported_rent": row.reported_rent,
            "reported_unit": row.reported_unit,
        },
    )


def _residential(
    zip_code: str,
    monthly: float,
    coeffs: _Coeffs,
    safmr: SafmrRecord | None,
    *,
    tier: str,
    as_of: str | None = None,
    citation: str | None = None,
) -> tuple[RentResolution, dict[str, object]]:
    if coeffs.unit_sqft <= 0:
        raise RentResolutionError(zip_code, "Rent model unit_sqft must be positive.")
    per_year = monthly * 12.0 / coeffs.unit_sqft * coeffs.commercial_residential_ratio
    if safmr is not None:
        as_of = safmr.as_of
        citation = (
            f"{safmr.citation} Converted with {coeffs.model_id} unit_sqft {coeffs.unit_sqft:g}."
        )
    if as_of is None or citation is None:
        raise RentResolutionError(zip_code, "Residential proxy is missing as_of or citation.")
    return _from_base(
        zip_code,
        per_year,
        property_type="residential_proxy",
        tier=tier,
        confidence="low",
        as_of=as_of,
        citation=citation,
        components={
            "monthly_rent": monthly,
            "unit_sqft": coeffs.unit_sqft,
            "commercial_residential_ratio": coeffs.commercial_residential_ratio,
            "model_id": coeffs.model_id,
        },
    )


def _from_base(
    zip_code: str,
    rent_psf_year: float,
    *,
    property_type: str,
    tier: str,
    confidence: str,
    as_of: str,
    citation: str,
    components: dict[str, object],
) -> tuple[RentResolution, dict[str, object]]:
    if rent_psf_year < 0:
        raise RentResolutionError(zip_code, "Resolved rent is negative.")
    stored = {"tier": tier, **components}
    resolution = RentResolution(
        zip_code=zip_code,
        rent_psf_year=rent_psf_year,
        rent_psf_month=rent_psf_year / 12.0,
        property_type=property_type,
        tier=tier,
        confidence=confidence,
        as_of=as_of,
        citation=citation,
    )
    return resolution, stored


def _store(
    conn: sqlite3.Connection,
    write_cache: bool,
    packed: tuple[RentResolution, dict[str, object]],
) -> RentResolution:
    resolution, components = packed
    if not write_cache:
        return resolution
    upsert_rent_cache(
        conn,
        RentCacheRecord(
            zip_code=resolution.zip_code,
            rent_psf_year=resolution.rent_psf_year,
            property_type=resolution.property_type,
            tier=resolution.tier,
            confidence=resolution.confidence,
            as_of=resolution.as_of,
            components_json=json.dumps(components, sort_keys=True),
            resolved_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            citation=resolution.citation,
        ),
    )
    return resolution


def _coeffs(record: RentModelRecord | None) -> _Coeffs:
    if record is None:
        return _Coeffs(
            model_id=RENT_MODEL_ID,
            b_income=0.0,
            b_density=0.0,
            b_home_value=0.0,
            b_acs_rent=1.0,
            clamp_low=0.5,
            clamp_high=2.0,
            unit_sqft=1000.0,
            commercial_residential_ratio=1.0,
            trained_on="Built-in acs_rent_v1. Not fit to the GSA Lease Inventory.",
            as_of="2026-11-09",
        )
    try:
        raw = json.loads(record.formula_json)
    except json.JSONDecodeError as exc:
        raise RentResolutionError("", f"Rent model {record.model_id} is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise RentResolutionError("", f"Rent model {record.model_id} must be an object.")
    return _Coeffs(
        model_id=record.model_id,
        b_income=_number(raw, "b_income", 0.0),
        b_density=_number(raw, "b_density", 0.0),
        b_home_value=_number(raw, "b_home_value", 0.0),
        b_acs_rent=_number(raw, "b_acs_rent", 1.0),
        clamp_low=_number(raw, "clamp_low", 0.5),
        clamp_high=_number(raw, "clamp_high", 2.0),
        unit_sqft=_number(raw, "unit_sqft", 1000.0),
        commercial_residential_ratio=_number(raw, "commercial_residential_ratio", 1.0),
        trained_on=record.trained_on,
        as_of=record.as_of,
    )


# sqlite3.Connection has no instance dict, so the CBSA median cache lives here.
_RENT_REFS: dict[tuple[int, str, int], dict[str, float | None]] = {}
_ACS_RENTS: dict[tuple[int, str, str, int], tuple[float, ...]] = {}
_RentLoader = Callable[[sqlite3.Connection, str, int], tuple[float, ...]]


def _references(conn: sqlite3.Connection, cbsa: str, year: int | None) -> dict[str, float | None]:
    if cbsa == "" or year is None:
        return {"rent": None, "income": None, "home": None}
    key = (id(conn), cbsa, year)
    cached = _RENT_REFS.get(key)
    if cached is not None:
        return cached
    found = {
        "rent": _median(acs_positive_values_for_cbsa(conn, cbsa, year, "median_gross_rent")),
        "income": _median(acs_positive_values_for_cbsa(conn, cbsa, year, "median_hh_income")),
        "home": _median(acs_positive_values_for_cbsa(conn, cbsa, year, "median_home_value")),
    }
    _RENT_REFS[key] = found
    return found


def _factor(
    acs: ZctaAcsRecord | None,
    centroid: ZctaCentroidRecord | None,
    references: dict[str, float | None],
    coeffs: _Coeffs,
) -> tuple[float, bool, bool]:
    """Return ``(factor, clamped, adjustment_applied)``."""
    if acs is None:
        return 1.0, False, False
    density = None
    if (
        acs.population is not None
        and acs.population > 0
        and centroid is not None
        and centroid.land_sqmi is not None
        and centroid.land_sqmi > 0
    ):
        density = acs.population / centroid.land_sqmi
    factor = 1.0
    applied = False
    for value, reference, exponent in (
        (acs.median_gross_rent, references.get("rent"), coeffs.b_acs_rent),
        (acs.median_hh_income, references.get("income"), coeffs.b_income),
        (acs.median_home_value, references.get("home"), coeffs.b_home_value),
        (density, None, coeffs.b_density),
    ):
        if exponent == 0 or value is None or reference is None or value <= 0 or reference <= 0:
            continue
        factor *= (value / reference) ** exponent
        applied = True
    clamped = False
    if factor < coeffs.clamp_low:
        factor = coeffs.clamp_low
        clamped = True
    elif factor > coeffs.clamp_high:
        factor = coeffs.clamp_high
        clamped = True
    return factor, clamped, applied


def _county_gsa(conn: sqlite3.Connection, county_fips: str) -> tuple[float, str, str] | None:
    observations = list_rent_zip_obs_for_zips(conn, zips_in_county(conn, county_fips), "gsa")
    amounts = [row.rent_psf_year for row in observations if row.rent_psf_year > 0]
    if not amounts:
        return None
    newest = max(row.as_of for row in observations)
    return (
        float(median(amounts)),
        newest,
        f"Median of {len(amounts)} GSA lease observations in county {county_fips}.",
    )


def _state_industrial(conn: sqlite3.Connection, state: str) -> tuple[float, str, str] | None:
    seeds = list_rent_cbsa_for_codes(conn, cbsas_for_state(conn, state))
    if len(seeds) < _STATE_SEED_MINIMUM:
        return None
    newest = max(row.as_of for row in seeds)
    amount = float(median([row.rent_psf_year for row in seeds]))
    return (
        amount,
        newest,
        f"Median industrial seed of {len(seeds)} CBSAs in {state}.",
    )


def _industrial(rows: tuple[RentCbsaRecord, ...]) -> RentCbsaRecord | None:
    for row in rows:
        if row.property_type == _INDUSTRIAL:
            return row
    return rows[0] if rows else None


def _median(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _number(raw: dict[str, object], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RentResolutionError("", f"Rent model {key} must be a number.")
    return float(value)


def _zip(zip_code: str) -> str:
    text = zip_code.strip()
    if len(text) != 5 or not text.isdigit():
        raise RentResolutionError(
            text,
            f"ZIP must be 5 digits, got {zip_code.strip()!r}.",
        )
    return text
