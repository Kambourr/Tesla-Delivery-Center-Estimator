"""Round-trip the catchment tables."""

from __future__ import annotations

from pathlib import Path

from dce.data.ingest.delivery_centers import (
    DELIVERY_CENTER_SOURCE_ID,
    DELIVERY_CENTER_TTL_DAYS,
    delivery_center_citation_url,
    delivery_center_license_note,
    load_delivery_centers,
)
from dce.data.ingest.zcta_gazetteer import ZctaCentroid, gazetteer_license_note, gazetteer_url
from dce.data.ingest.zev_sales import (
    ZevCountySales,
    ZevSalesBatch,
    ZevZipSales,
    zev_catalog_url,
    zev_license_note,
)
from dce.data.persist import persist_delivery_centers, persist_zcta_centroids, persist_zev_sales
from dce.storage.connection import get_connection
from dce.storage.repository import (
    get_source,
    get_zcta_centroid,
    get_zev_county_sales,
    get_zev_zip_sales,
    list_delivery_centers,
)


def test_snapshot_centroids_and_zev_rows_round_trip(tmp_path: Path) -> None:
    conn = get_connection(tmp_path)
    try:
        centers = load_delivery_centers()
        persist_delivery_centers(
            conn,
            centers,
            source_id=DELIVERY_CENTER_SOURCE_ID,
            url=delivery_center_citation_url(),
            as_of="2026-11-08",
            fetched_at="2026-11-09T06:00:00Z",
            ttl_days=DELIVERY_CENTER_TTL_DAYS,
            license_note=delivery_center_license_note(),
            byte_count=100,
        )
        stored = {row.center_id: row for row in list_delivery_centers(conn, "2026-11-08")}
        assert set(stored) == {row.center_id for row in centers}
        assert stored["colma"].zip_code == "94014"
        assert stored["colma"].lat == next(row.lat for row in centers if row.center_id == "colma")
        source = get_source(conn, DELIVERY_CENTER_SOURCE_ID)
        assert source is not None
        assert source.as_of == "2026-11-08"
        assert source.url == delivery_center_citation_url()

        persist_zcta_centroids(
            conn,
            (ZctaCentroid("94402", 37.540103, -122.330103, "2024", "2024-01-01"),),
            source_id="census_zcta_gazetteer",
            url=gazetteer_url(2024),
            as_of="2024-01-01",
            fetched_at="2026-11-09T06:00:00Z",
            ttl_days=548,
            license_note=gazetteer_license_note(),
            byte_count=20,
        )
        point = get_zcta_centroid(conn, "94402", "2024")
        assert point is not None
        assert point.lat == 37.540103
        assert point.lon == -122.330103

        batch = ZevSalesBatch(
            as_of="2025-03-31",
            zip_sales=(ZevZipSales("94402", "CA", 2025, 1, "Electric", 10, "2025-03-31", "cec"),),
            county_sales=(
                ZevCountySales(
                    "San Mateo", "CA", 2025, 1, "Electric", "Tesla", 100, "2025-03-31", "cec"
                ),
            ),
            source_url=zev_catalog_url(),
            byte_count=32,
        )
        persist_zev_sales(
            conn,
            batch,
            source_id="cec_zev_sales",
            fetched_at="2026-11-09T06:00:00Z",
            ttl_days=548,
            license_note=zev_license_note(),
        )
        zip_row = get_zev_zip_sales(conn, "94402", 2025, 1, "Electric", "cec")
        assert zip_row is not None
        assert zip_row.vehicles == 10
        county = get_zev_county_sales(conn, "San Mateo", 2025, 1, "Electric", "Tesla", "cec")
        assert county is not None
        assert county.vehicles == 100
        registry = get_source(conn, "cec_zev_sales")
        assert registry is not None
        assert registry.as_of == "2025-03-31"
        replaced = ZevSalesBatch(
            as_of="2025-03-31",
            zip_sales=(ZevZipSales("94402", "CA", 2025, 1, "Electric", 12, "2025-03-31", "cec"),),
            county_sales=batch.county_sales,
            source_url=zev_catalog_url(),
            byte_count=32,
        )
        persist_zev_sales(
            conn,
            replaced,
            source_id="cec_zev_sales",
            fetched_at="2026-11-09T06:00:00Z",
            ttl_days=548,
            license_note=zev_license_note(),
        )
        updated = get_zev_zip_sales(conn, "94402", 2025, 1, "Electric", "cec")
        assert updated is not None
        assert updated.vehicles == 12
    finally:
        conn.close()
