"""Build offline ZCTA polygons for the MapLibre map.

Census has not published a national ZCTA cartographic file since 2020.
The input is ``cb_2020_us_zcta520_500k.zip`` (1:500,000). Each polygon is
Douglas-Peucker simplified by 0.001 degrees (about 111 meters) with
topology preserved, then written two ways:

* ``data/geo/zcta_bay_area.geojson`` is committed. It is the nine-county
  Bay Area (dominant county from ``data/seed/zip_crosswalk.csv``).
* ``data/geo/zcta_us.pmtiles`` is gitignored. MapLibre draws about 33,000
  polygons fastest as vector tiles, because only the tiles in view are
  decoded. A national GeoJSON would be parsed all at once. tippecanoe
  keeps every polygon (``--no-feature-limit`` and ``--no-tile-size-limit``)
  on layer ``zcta``, zooms 3 through 8. The only property is ``zcta``.

The curator downloads from ``www2.census.gov`` only. Redirects are refused.
Pass ``--cache`` when the zip is already on disk. Accessed 2026-11-09.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dce.data.ingest.census_geo import (
    ZCTA_SIMPLIFY_DEGREES,
    simplify_zcta_geojson,
    write_geojson,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "zip_crosswalk.csv"
GEO = ROOT / "data" / "geo"
BAY_COUNTIES = frozenset(
    {"06001", "06013", "06041", "06055", "06075", "06081", "06085", "06095", "06097"}
)
_URL = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
_ZIP_NAME = "cb_2020_us_zcta520_500k.zip"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "cache" / "zip_inputs")
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--record",
        action="store_true",
        help="Rewrite the tracked data/geo/boundary_build.json. Off by default.",
    )
    args = parser.parse_args(argv)
    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / _ZIP_NAME
    if not archive.is_file():
        if not args.download:
            raise SystemExit(f"Missing {archive}. Pass --download to fetch it.")
        _download(archive)
    bay = _bay_zctas(SEED)
    GEO.mkdir(parents=True, exist_ok=True)
    bay_geo = simplify_zcta_geojson(archive, zctas=bay, tolerance_degrees=ZCTA_SIMPLIFY_DEGREES)
    bay_path = write_geojson(bay_geo, GEO / "zcta_bay_area.geojson")
    national = simplify_zcta_geojson(archive, tolerance_degrees=ZCTA_SIMPLIFY_DEGREES)
    national_path = cache / "zcta_us.geojson"
    write_geojson(national, national_path)
    pmtiles = GEO / "zcta_us.pmtiles"
    _tippecanoe(national_path, pmtiles)
    summary = {
        "tolerance_degrees": ZCTA_SIMPLIFY_DEGREES,
        "bay_area_zctas": len(bay),
        "bay_area_geojson_bytes": bay_path.stat().st_size,
        "national_geojson_bytes": national_path.stat().st_size,
        "national_pmtiles_bytes": pmtiles.stat().st_size,
        "pmtiles_layer": "zcta",
        "pmtiles_zooms": "3-8",
        "source": _URL,
        "accessed": "2026-11-09",
    }
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    record = GEO / "boundary_build.json"
    # tippecanoe and the national GeoJSON are not byte-stable across machines.
    # Writing those sizes back marks a tracked file dirty after every build.
    if args.record:
        record.write_text(text, encoding="utf-8")
    elif record.is_file() and record.read_text(encoding="utf-8") != text:
        print(
            "boundary_build.json was not rewritten. Pass --record to replace the committed sizes.",
            file=sys.stderr,
        )
    print(text, end="")
    return 0


def _bay_zctas(path: Path) -> frozenset[str]:
    best: dict[str, tuple[float, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["zip"] != row["zcta"]:
                continue
            ratio = float(row["tot_ratio"])
            current = best.get(row["zcta"])
            if (
                current is None
                or ratio > current[0]
                or (ratio == current[0] and row["county_fips"] < current[1])
            ):
                best[row["zcta"]] = (ratio, row["county_fips"])
    return frozenset(zcta for zcta, (_ratio, county) in best.items() if county in BAY_COUNTIES)


def _tippecanoe(source: Path, destination: Path) -> None:
    program = shutil.which("tippecanoe")
    if program is None:
        raise SystemExit("tippecanoe is not installed.")
    destination.unlink(missing_ok=True)
    subprocess.run(
        [
            program,
            "-o",
            str(destination),
            "-l",
            "zcta",
            "--force",
            "--minimum-zoom=3",
            "--maximum-zoom=8",
            "--no-feature-limit",
            "--no-tile-size-limit",
            "--detect-shared-borders",
            str(source),
        ],
        check=True,
    )


def _download(path: Path) -> None:
    request = urllib.request.Request(_URL, headers={"User-Agent": "delivery-center-estimator"})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(  # type: ignore[override]
            self,
            req: urllib.request.Request,
            fp: object,
            code: int,
            msg: str,
            headers: object,
            newurl: str,
        ) -> urllib.request.Request | None:
            raise urllib.error.HTTPError(
                req.full_url,
                code,
                f"redirect refused to {newurl}",
                headers,  # type: ignore[arg-type]
                None,
            )

    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=180) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Boundary download failed: {exc}") from exc
    path.write_bytes(payload)


if __name__ == "__main__":
    raise SystemExit(main())
