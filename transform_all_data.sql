-- ============================================================
-- TRANSFORM ALL RAW API TABLES INTO CLEAN SQL TABLES
-- ============================================================

-- This file assumes Python already created these raw tables:
--   raw_distribution_mains
--   raw_transmission_mains
--   raw_311_water_leaks_2009_2021
--   raw_311_water_leaks_2021_present
--
-- Each raw table has:
--   id
--   raw_json
--   imported_at


-- ============================================================
-- 1. CLEAN DISTRIBUTION MAINS
-- ============================================================

DROP TABLE IF EXISTS clean_distribution_mains;

CREATE TABLE clean_distribution_mains AS
SELECT
    id,
    (raw_json->>'diameter_mm')::INTEGER AS diameter_mm,
    (raw_json->>'installation_date')::DATE AS installation_date,
    raw_json->>'lining_material' AS lining_material,
    raw_json->>'material' AS material,
    (raw_json->'geo_point_2d'->>'lon')::DOUBLE PRECISION AS lon,
    (raw_json->'geo_point_2d'->>'lat')::DOUBLE PRECISION AS lat,
    raw_json->'geom' AS geom,
    imported_at
FROM raw_distribution_mains;


-- ============================================================
-- 2. CLEAN TRANSMISSION MAINS
-- ============================================================

DROP TABLE IF EXISTS clean_transmission_mains;

CREATE TABLE clean_transmission_mains AS
SELECT
    id,
    (raw_json->>'diameter_mm')::INTEGER AS diameter_mm,
    (raw_json->>'installation_date')::DATE AS installation_date,
    raw_json->>'lining_material' AS lining_material,
    raw_json->>'material' AS material,
    (raw_json->'geo_point_2d'->>'lon')::DOUBLE PRECISION AS lon,
    (raw_json->'geo_point_2d'->>'lat')::DOUBLE PRECISION AS lat,
    raw_json->'geom' AS geom,
    imported_at
FROM raw_transmission_mains;


-- ============================================================
-- 3. CLEAN 311 WATER LEAKS, 2009–2021 DATASET
-- ============================================================

DROP TABLE IF EXISTS clean_311_water_leaks_2009_2021;

CREATE TABLE clean_311_water_leaks_2009_2021 AS
SELECT
    id,

    raw_json->>'department' AS department,
    raw_json->>'service_request_type' AS service_request_type,
    raw_json->>'status' AS status,
    raw_json->>'closure_reason' AS closure_reason,

    NULLIF(raw_json->>'service_request_open_timestamp', '')::TIMESTAMPTZ AS service_request_open_timestamp,
    NULLIF(raw_json->>'service_request_close_date', '')::DATE AS service_request_close_date,
    NULLIF(raw_json->>'last_modified_timestamp', '')::TIMESTAMPTZ AS last_modified_timestamp,

    raw_json->>'address' AS address,
    raw_json->>'local_area' AS local_area,
    raw_json->>'channel' AS channel,

    NULLIF(raw_json->>'latitude', '')::DOUBLE PRECISION AS latitude,
    NULLIF(raw_json->>'longitude', '')::DOUBLE PRECISION AS longitude,

    raw_json->'geom' AS geom,
    raw_json AS raw_json,
    imported_at
FROM raw_311_water_leaks_2009_2021;


-- ============================================================
-- 4. CLEAN 311 WATER LEAKS, 2021–PRESENT DATASET
-- ============================================================

DROP TABLE IF EXISTS clean_311_water_leaks_2021_present;

CREATE TABLE clean_311_water_leaks_2021_present AS
SELECT
    id,

    raw_json->>'department' AS department,
    raw_json->>'service_request_type' AS service_request_type,
    raw_json->>'status' AS status,
    raw_json->>'closure_reason' AS closure_reason,

    NULLIF(raw_json->>'service_request_open_timestamp', '')::TIMESTAMPTZ AS service_request_open_timestamp,
    NULLIF(raw_json->>'service_request_close_date', '')::DATE AS service_request_close_date,
    NULLIF(raw_json->>'last_modified_timestamp', '')::TIMESTAMPTZ AS last_modified_timestamp,

    raw_json->>'address' AS address,
    raw_json->>'local_area' AS local_area,
    raw_json->>'channel' AS channel,

    NULLIF(raw_json->>'latitude', '')::DOUBLE PRECISION AS latitude,
    NULLIF(raw_json->>'longitude', '')::DOUBLE PRECISION AS longitude,

    raw_json->'geom' AS geom,
    raw_json AS raw_json,
    imported_at
FROM raw_311_water_leaks_2021_present;


-- ============================================================
-- 5. COMBINE BOTH 311 WATER LEAK TABLES
-- ============================================================

DROP TABLE IF EXISTS clean_311_water_leaks_all;

CREATE TABLE clean_311_water_leaks_all AS
SELECT
    '2009_2021' AS source_dataset,
    *,
    service_request_close_date - service_request_open_timestamp::DATE AS days_to_close
FROM clean_311_water_leaks_2009_2021

UNION ALL

SELECT
    '2021_present' AS source_dataset,
    *,
    service_request_close_date - service_request_open_timestamp::DATE AS days_to_close
FROM clean_311_water_leaks_2021_present;

-- ============================================================
-- 6. COMBINE DISTRIBUTION AND TRANSMISSION MAINS
-- ============================================================

DROP TABLE IF EXISTS clean_water_mains_all;

CREATE TABLE clean_water_mains_all AS
SELECT
    'distribution' AS source_dataset,
    id,
    diameter_mm,
    installation_date,
    lining_material,
    material,
    lon,
    lat,
    geom,
    imported_at
FROM clean_distribution_mains

UNION ALL

SELECT
    'transmission' AS source_dataset,
    id,
    diameter_mm,
    installation_date,
    lining_material,
    material,
    lon,
    lat,
    geom,
    imported_at
FROM clean_transmission_mains;


-- ============================================================
-- 7. QUICK CHECKS
-- ============================================================

-- Remove obsolete / accidental tables from earlier runs.
DROP TABLE IF EXISTS clean_water_mains;
DROP TABLE IF EXISTS raw_water_mains;
DROP TABLE IF EXISTS water_mains;
DROP TABLE IF EXISTS clean_mains_all;

SELECT 'clean_distribution_mains' AS table_name, COUNT(*) AS row_count
FROM clean_distribution_mains

UNION ALL

SELECT 'clean_transmission_mains' AS table_name, COUNT(*) AS row_count
FROM clean_transmission_mains

UNION ALL

SELECT 'clean_water_mains_all' AS table_name, COUNT(*) AS row_count
FROM clean_water_mains_all

UNION ALL

SELECT 'clean_311_water_leaks_2009_2021' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_2009_2021

UNION ALL

SELECT 'clean_311_water_leaks_2021_present' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_2021_present

UNION ALL

SELECT 'clean_311_water_leaks_all' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_all;




-- ============================================================
-- 8. Clean the water main table
-- ============================================================
DROP TABLE IF EXISTS main;

CREATE TABLE main AS
SELECT
    *,
    EXTRACT(YEAR FROM installation_date)::INTEGER AS installation_year
FROM clean_water_mains_all;

ALTER TABLE main
DROP COLUMN installation_date, 
DROP COLUMN imported_at;



--removes id and gives each row unique id
ALTER TABLE main
DROP COLUMN IF EXISTS id;

ALTER TABLE main
ADD COLUMN id BIGSERIAL PRIMARY KEY;


-- ============================================================
-- 9. Clean the 311 data
-- ============================================================
DROP TABLE IF EXISTS leakdata;

CREATE TABLE leakdata AS
SELECT
    *,
    EXTRACT(YEAR FROM service_request_open_timestamp):: INTEGER AS leak_year
FROM clean_311_water_leaks_all;

ALTER TABLE leakdata
DROP COLUMN source_dataset,
DROP COLUMN department,
DROP COLUMN service_request_type,
DROP COLUMN status,
DROP COLUMN closure_reason,
DROP COLUMN service_request_close_date,
DROP COLUMN service_request_open_timestamp,
DROP COLUMN last_modified_timestamp,
DROP COLUMN address,
DROP COLUMN channel,
DROP COLUMN imported_at;

-- drop the duplicate entries in the table (There will be years with multiple leaks)
DROP TABLE IF EXISTS leakdata_deduped;

CREATE TABLE leakdata_deduped AS
SELECT DISTINCT *
FROM leakdata;

DROP TABLE leakdata;

ALTER TABLE leakdata_deduped
RENAME TO leakdata;

-- drops id column and gives each row unique id
ALTER TABLE leakdata
DROP COLUMN IF EXISTS id;

ALTER TABLE leakdata
ADD COLUMN id BIGSERIAL PRIMARY KEY;




-- ============================================================
-- CREATE GEOMETRY COLUMNS FOR SPATIAL MATCHING
-- ============================================================

ALTER TABLE main
ADD COLUMN IF NOT EXISTS geom_utm geometry(Point, 26910);

UPDATE main
SET geom_utm = ST_Transform(
    ST_SetSRID(ST_MakePoint(lon, lat), 4326),
    26910
)
WHERE lon IS NOT NULL
  AND lat IS NOT NULL
  AND geom_utm IS NULL;


ALTER TABLE leakdata
ADD COLUMN IF NOT EXISTS geom_utm geometry(Point, 26910);

UPDATE leakdata
SET geom_utm = ST_Transform(
    ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
    26910
)
WHERE longitude IS NOT NULL
  AND latitude IS NOT NULL
  AND geom_utm IS NULL;


CREATE INDEX IF NOT EXISTS idx_main_geom_utm
ON main
USING GIST (geom_utm);

CREATE INDEX IF NOT EXISTS idx_leakdata_geom_utm
ON leakdata
USING GIST (geom_utm);

ANALYZE main;
ANALYZE leakdata;




-- ============================================================
-- 10. Note: At this point, we have all the water mains together in one dataset.
-- we have another datset with all the 311 requests and the year that each happened
-- we need to create our final dataset with the columns that we want, This dataset will link 
-- the mains with the leaks data. For each year for each pipe between 2009 and 2026,
-- there will be an entry and there will be a 1 for each year that has an entry
-- ============================================================

DROP TABLE IF EXISTS pipe_year_data;

CREATE TABLE pipe_year_data AS
SELECT
    m.id AS pipe_id,
    years.feature_year,

    m.source_dataset,
    m.diameter_mm,
    m.lining_material,
    m.material,
    m.lon,
    m.lat,
    m.geom,
    m.installation_year,

    years.feature_year - m.installation_year AS pipe_age

FROM main m
CROSS JOIN generate_series(2009, 2026) AS years(feature_year)
WHERE m.installation_year IS NULL
   OR years.feature_year >= m.installation_year;



--



