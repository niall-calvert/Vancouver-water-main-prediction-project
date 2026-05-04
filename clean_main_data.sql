-- ============================================================
-- CLEAN WATER MAIN DATA
--
-- Input tables:
--   raw_distribution_mains
--   raw_transmission_mains
--
-- Final output table:
--   main
--
-- Final columns:
--   id
--   source_dataset
--   diameter_mm
--   installation_year
--   lining_material
--   material
--   lon
--   lat
--   geom
-- ============================================================


-- ============================================================
-- 1. CLEAN DISTRIBUTION MAINS
-- ============================================================

DROP TABLE IF EXISTS clean_distribution_mains;

CREATE TABLE clean_distribution_mains AS
SELECT
    id,
    NULLIF(raw_json->>'diameter_mm', '')::INTEGER AS diameter_mm,

    -- Vancouver Open Data values may look like 'January 1, 1962'.
    -- PostgreSQL can cast this format to DATE.
    NULLIF(raw_json->>'installation_date', '')::DATE AS installation_date,

    NULLIF(raw_json->>'lining_material', '') AS lining_material,
    NULLIF(raw_json->>'material', '') AS material,

    NULLIF(raw_json->'geo_point_2d'->>'lon', '')::DOUBLE PRECISION AS lon,
    NULLIF(raw_json->'geo_point_2d'->>'lat', '')::DOUBLE PRECISION AS lat,

    raw_json->'geom' AS geom,
    raw_json AS raw_json,
    imported_at
FROM raw_distribution_mains
WHERE raw_json->'geom' IS NOT NULL
  AND raw_json->'geo_point_2d' IS NOT NULL;


-- ============================================================
-- 2. CLEAN TRANSMISSION MAINS
-- ============================================================

DROP TABLE IF EXISTS clean_transmission_mains;

CREATE TABLE clean_transmission_mains AS
SELECT
    id,
    NULLIF(raw_json->>'diameter_mm', '')::INTEGER AS diameter_mm,

    -- Vancouver Open Data values may look like 'January 1, 1962'.
    -- PostgreSQL can cast this format to DATE.
    NULLIF(raw_json->>'installation_date', '')::DATE AS installation_date,

    NULLIF(raw_json->>'lining_material', '') AS lining_material,
    NULLIF(raw_json->>'material', '') AS material,

    NULLIF(raw_json->'geo_point_2d'->>'lon', '')::DOUBLE PRECISION AS lon,
    NULLIF(raw_json->'geo_point_2d'->>'lat', '')::DOUBLE PRECISION AS lat,

    raw_json->'geom' AS geom,
    raw_json AS raw_json,
    imported_at
FROM raw_transmission_mains
WHERE raw_json->'geom' IS NOT NULL
  AND raw_json->'geo_point_2d' IS NOT NULL;


-- ============================================================
-- 3. COMBINE DISTRIBUTION AND TRANSMISSION MAINS
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
    raw_json,
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
    raw_json,
    imported_at
FROM clean_transmission_mains;


-- ============================================================
-- 4. CREATE FINAL MAIN TABLE
--
-- Keeps only useful modelling / mapping fields.
-- Converts installation_date to installation_year.
-- Removes duplicate rows before assigning a fresh primary key.
-- ============================================================

DROP TABLE IF EXISTS main;

CREATE TABLE main AS
SELECT DISTINCT
    source_dataset,
    diameter_mm,
    EXTRACT(YEAR FROM installation_date)::INTEGER AS installation_year,
    lining_material,
    material,
    lon,
    lat,
    geom
FROM clean_water_mains_all
WHERE geom IS NOT NULL
  AND lon IS NOT NULL
  AND lat IS NOT NULL;


-- Add clean unique id after deduplication.
ALTER TABLE main
ADD COLUMN id BIGSERIAL PRIMARY KEY;


-- ============================================================
-- 5. REMOVE OBSOLETE / ACCIDENTAL TABLES FROM EARLIER RUNS
-- ============================================================

DROP TABLE IF EXISTS clean_water_mains;
DROP TABLE IF EXISTS raw_water_mains;
DROP TABLE IF EXISTS water_mains;
DROP TABLE IF EXISTS clean_mains_all;


-- ============================================================
-- 6. QUICK CHECKS
-- ============================================================

SELECT 'clean_distribution_mains' AS table_name, COUNT(*) AS row_count
FROM clean_distribution_mains

UNION ALL

SELECT 'clean_transmission_mains' AS table_name, COUNT(*) AS row_count
FROM clean_transmission_mains

UNION ALL

SELECT 'clean_water_mains_all' AS table_name, COUNT(*) AS row_count
FROM clean_water_mains_all

UNION ALL

SELECT 'main' AS table_name, COUNT(*) AS row_count
FROM main;


-- Preview final output.
SELECT *
FROM main
LIMIT 20;
