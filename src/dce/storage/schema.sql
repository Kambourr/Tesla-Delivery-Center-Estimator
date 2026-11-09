-- Delivery-Center Estimator physical schema (milestone M1).
-- Apply with dce.storage.migrate. Repeating the script is safe:
-- every CREATE is IF NOT EXISTS, and the version insert runs once.
--
-- Staleness is not a stored column. source_registry keeps as_of,
-- fetched_at, and ttl_days so a later milestone can classify a source
-- as fresh, aging, stale, or missing.
--
-- ZIP geography used to build GeoContext:
--   zip_county   HUD ZIP -> county
--   zip_cbsa     HUD ZIP -> CBSA (metropolitan division code when OMB
--                splits the metro; see docs/OPEN_QUESTIONS.md)
--   zip_zcta     Census ZIP -> ZCTA
--
-- The rent milestone adds rent_cbsa, rent_zip_obs, rent_model_coeffs,
-- and rent_resolved_cache from docs/DATA_SOURCES.md section 8.
-- This file ships inside the package. Applying it does not use the network.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    as_of TEXT,
    fetched_at TEXT,
    ttl_days INTEGER NOT NULL CHECK (ttl_days >= 0),
    license_note TEXT NOT NULL,
    bytes INTEGER CHECK (bytes IS NULL OR bytes >= 0)
);

CREATE TABLE IF NOT EXISTS zcta_acs (
    zcta TEXT NOT NULL,
    year INTEGER NOT NULL,
    population REAL,
    median_hh_income REAL,
    vehicles_available REAL,
    mean_commute REAL,
    PRIMARY KEY (zcta, year)
);

CREATE TABLE IF NOT EXISTS oews_wage (
    area_code TEXT NOT NULL,
    area_name TEXT NOT NULL,
    soc TEXT NOT NULL,
    soc_title TEXT NOT NULL,
    mean_annual REAL,
    median_annual REAL,
    as_of TEXT NOT NULL,
    PRIMARY KEY (area_code, soc, as_of)
);

CREATE TABLE IF NOT EXISTS ev_zip (
    zip TEXT NOT NULL,
    state TEXT NOT NULL,
    bev INTEGER,
    phev INTEGER,
    fcev INTEGER,
    total_ldv INTEGER,
    as_of TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('cec', 'dmv', 'fallback')),
    PRIMARY KEY (zip, as_of, source)
);

CREATE TABLE IF NOT EXISTS utility_rate (
    utility_id TEXT NOT NULL,
    schedule TEXT NOT NULL,
    geography TEXT NOT NULL,
    energy_rate_kwh REAL,
    demand_rate_kw REAL,
    as_of TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('pge_pdf', 'eia', 'openei')),
    PRIMARY KEY (utility_id, schedule, geography, as_of, source)
);

CREATE TABLE IF NOT EXISTS rent_default (
    geo_key TEXT NOT NULL,
    rent_psf_month REAL NOT NULL,
    citation TEXT NOT NULL,
    as_of TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low', 'fmr_weak')),
    PRIMARY KEY (geo_key, as_of)
);

CREATE TABLE IF NOT EXISTS extract_cache (
    pdf_sha256 TEXT PRIMARY KEY,
    extractor TEXT NOT NULL CHECK (extractor IN ('manual', 'llm')),
    json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- HUD-USPS ZIP to county. One ZIP can fall in several counties; the
-- ratios allocate residential, business, other, and total addresses.
CREATE TABLE IF NOT EXISTS zip_county (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    county_fips TEXT NOT NULL CHECK (length(county_fips) = 5),
    state TEXT NOT NULL CHECK (length(state) = 2),
    res_ratio REAL,
    bus_ratio REAL,
    oth_ratio REAL,
    tot_ratio REAL,
    as_of TEXT,
    PRIMARY KEY (zip, county_fips)
);

-- HUD-USPS ZIP to CBSA. When OMB splits a metro into divisions, the
-- CBSA column on this crosswalk is the metropolitan division code.
CREATE TABLE IF NOT EXISTS zip_cbsa (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    cbsa TEXT NOT NULL CHECK (length(cbsa) = 5),
    res_ratio REAL,
    bus_ratio REAL,
    oth_ratio REAL,
    tot_ratio REAL,
    as_of TEXT,
    PRIMARY KEY (zip, cbsa)
);

-- Census ZIP to ZCTA. HUD does not publish ZCTAs. The demo ZIPs
-- 94401-94404 are each their own ZCTA.
CREATE TABLE IF NOT EXISTS zip_zcta (
    zip TEXT NOT NULL CHECK (length(zip) = 5),
    zcta TEXT NOT NULL CHECK (length(zcta) = 5),
    PRIMARY KEY (zip, zcta)
);

INSERT INTO schema_migrations (version, applied_at)
SELECT 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE NOT EXISTS (
    SELECT 1 FROM schema_migrations WHERE version = 1
);
