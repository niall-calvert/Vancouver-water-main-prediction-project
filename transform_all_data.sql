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
-- 6. QUICK CHECKS
-- ============================================================

SELECT 'clean_distribution_mains' AS table_name, COUNT(*) AS row_count
FROM clean_distribution_mains

UNION ALL

SELECT 'clean_transmission_mains' AS table_name, COUNT(*) AS row_count
FROM clean_transmission_mains

UNION ALL

SELECT 'clean_311_water_leaks_2009_2021' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_2009_2021

UNION ALL

SELECT 'clean_311_water_leaks_2021_present' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_2021_present

UNION ALL

SELECT 'clean_311_water_leaks_all' AS table_name, COUNT(*) AS row_count
FROM clean_311_water_leaks_all;