"""HUD–USPS ZIP crosswalk fetch.

Contract
--------
Allowlisted host: ``huduser.gov``. ZIP to county (API type 2) and ZIP to
CBSA (API type 3). Token: ``HUD_TOKEN`` from the environment, never from git.
The token is a bearer header and is not written into ``source_registry``.

The nationwide offline crosswalk is the Census and HRSA seed, not this call.
HUD's bulk files require a login, and the API needs the token. Refresh
quarterly when the token is set. Stale after 2 quarters. Does not open SQLite.

A ZIP in several counties returns one :class:`ZipCrosswalk` per county. The
CBSA is the type-3 row with the greatest ``tot_ratio``. ``GeoContext`` still
uses the Census division code from the seed when that seed is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass

from dce.config import api_key as read_api_key
from dce.data.ingest.http import IngestError, encode_query, request_json
from dce.data.ingest.zip_geography import STATE_ABBR

HUD_CROSSWALK_SOURCE_ID = "hud_usps_crosswalk"
_API = "https://www.huduser.gov/hudapi/public/usps"
_TYPE_COUNTY = "2"
_TYPE_CBSA = "3"
_LICENSE = (
    "HUD-USPS ZIP Code Crosswalk. US Department of Housing and Urban Development. "
    "US government work."
)


@dataclass(frozen=True)
class ZipCrosswalk:
    """One ZIP row from the HUD crosswalk. Codes are text."""

    zip_code: str
    county_fips: str
    cbsa: str
    state: str
    tot_ratio: float = 1.0


class HudCrosswalkError(IngestError):
    """A HUD ZIP crosswalk response could not be used."""


class HudTokenError(HudCrosswalkError):
    """``HUD_TOKEN`` is required for a live crosswalk fetch and was not set."""


def hud_license_note() -> str:
    """Return the ``source_registry`` license note for the HUD crosswalk."""
    return _LICENSE


def hud_crosswalk_url() -> str:
    """Return the API URL stored in ``source_registry`` (no token)."""
    return _API


def fetch_zip_crosswalk(zip_code: str, *, token: str | None = None) -> tuple[ZipCrosswalk, ...]:
    """Download HUD county and CBSA rows for one ZIP.

    ``token`` overrides the environment. A missing token raises
    :class:`HudTokenError` before any socket is opened.
    """
    code = _zip(zip_code)
    secret = _resolve_token(token)
    counties = _fetch_type(code, _TYPE_COUNTY, secret)
    cbsas = _fetch_type(code, _TYPE_CBSA, secret)
    cbsa, _ratio = _dominant(cbsas)
    rows: list[ZipCrosswalk] = []
    for item in counties:
        geoid = item["geoid"]
        ratio = item["tot_ratio"]
        state_value = item.get("state", "")
        if not isinstance(geoid, str) or not isinstance(ratio, float):
            raise HudCrosswalkError(f"HUD county row for ZIP {code} is malformed.")
        state = state_value if isinstance(state_value, str) else ""
        if state == "":
            state = STATE_ABBR.get(geoid[:2], "")
        if len(state) != 2:
            raise HudCrosswalkError(f"HUD county row for ZIP {code} has no state.")
        rows.append(
            ZipCrosswalk(
                zip_code=code,
                county_fips=geoid,
                cbsa=cbsa,
                state=state,
                tot_ratio=ratio,
            )
        )
    if not rows and cbsa:
        rows.append(ZipCrosswalk(zip_code=code, county_fips="", cbsa=cbsa, state="", tot_ratio=1.0))
    if not rows:
        raise HudCrosswalkError(f"HUD returned no county or CBSA row for ZIP {code}.")
    return tuple(rows)


def parse_hud_results(payload: object) -> tuple[dict[str, str | float], ...]:
    """Return ``geoid``, ``tot_ratio``, and ``state`` dictionaries from one HUD body."""
    if not isinstance(payload, dict):
        raise HudCrosswalkError("HUD response was not a JSON object.")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise HudCrosswalkError("HUD response data was not an object.")
    results = data.get("results")
    if results is None and isinstance(payload.get("results"), list):
        results = payload.get("results")
    if not isinstance(results, list):
        raise HudCrosswalkError("HUD response has no results list.")
    rows: list[dict[str, str | float]] = []
    for item in results:
        if not isinstance(item, dict):
            raise HudCrosswalkError("HUD result row is not an object.")
        geoid = str(item.get("geoid", "")).strip()
        if len(geoid) == 4 and geoid.isdigit():
            geoid = geoid.zfill(5)
        if len(geoid) != 5 or not geoid.isdigit():
            raise HudCrosswalkError(f"HUD geoid must be 5 digits, got {geoid!r}.")
        state = item.get("state", "")
        rows.append(
            {
                "geoid": geoid,
                "tot_ratio": _ratio(item.get("tot_ratio", 0)),
                "state": state.strip().upper() if isinstance(state, str) else "",
            }
        )
    return tuple(rows)


def _fetch_type(zip_code: str, type_code: str, token: str) -> tuple[dict[str, str | float], ...]:
    query = encode_query({"type": type_code, "query": zip_code})
    try:
        payload = request_json(
            f"{_API}?{query}",
            headers={"Authorization": f"Bearer {token}"},
        )
    except IngestError as exc:
        raise HudCrosswalkError(
            "HUD crosswalk request failed. The token is not included here."
        ) from exc
    return parse_hud_results(payload)


def _dominant(rows: tuple[dict[str, str | float], ...]) -> tuple[str, float]:
    if not rows:
        return "", 0.0
    chosen = max(rows, key=lambda row: float(row["tot_ratio"]))
    return str(chosen["geoid"]), float(chosen["tot_ratio"])


def _resolve_token(explicit: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    found = read_api_key("HUD_TOKEN")
    if found is None:
        raise HudTokenError(
            "HUD crosswalk fetch needs HUD_TOKEN in the environment or a local .env file. "
            "The offline ZIP seed does not need the token."
        )
    return found


def _zip(zip_code: str) -> str:
    text = zip_code.strip()
    if len(text) != 5 or not text.isdigit():
        raise HudCrosswalkError(f"ZIP must be 5 digits, got {zip_code!r}.")
    return text


def _ratio(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise HudCrosswalkError(f"HUD tot_ratio must be a number, got {value!r}.")
    try:
        number = float(value)
    except ValueError as exc:
        raise HudCrosswalkError(f"HUD tot_ratio must be a number, got {value!r}.") from exc
    return number
