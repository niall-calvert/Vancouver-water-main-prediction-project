-- ============================================================
-- CLEAN 311 WATER LEAK DATA
-- ============================================================

DROP TABLE IF EXISTS leakdata;

CREATE TABLE leakdata AS
WITH combined_raw AS (
    SELECT raw_json
    FROM raw_311_water_leaks_2009_2021

    UNION ALL

    SELECT raw_json
    FROM raw_311_water_leaks_2021_present
),

cleaned AS (
    SELECT
        raw_json->>'service_request_type' AS service_request_type,
        raw_json->>'closure_reason' AS closure_reason,

        NULLIF(raw_json->>'service_request_open_timestamp', '')::TIMESTAMPTZ AS service_request_open_timestamp,
        NULLIF(raw_json->>'longitude', '')::DOUBLE PRECISION AS longitude,
        NULLIF(raw_json->>'latitude', '')::DOUBLE PRECISION AS latitude,

        raw_json->'geom' AS geom
    FROM combined_raw
)

SELECT DISTINCT
    EXTRACT(YEAR FROM service_request_open_timestamp)::INTEGER AS leak_year,
    longitude,
    latitude,
    COALESCE(
        geom,
        jsonb_build_object(
            'type', 'Point',
            'coordinates', jsonb_build_array(longitude, latitude)
        )
    ) AS geom
FROM cleaned
WHERE service_request_type = 'Water Leak Case'
  AND closure_reason = 'Service provided'
  AND service_request_open_timestamp IS NOT NULL
  AND longitude IS NOT NULL
  AND latitude IS NOT NULL;

ALTER TABLE leakdata
ADD COLUMN id BIGSERIAL PRIMARY KEY;


-- ============================================================
-- QUICK CHECKS
-- ============================================================

SELECT 'raw_311_water_leaks_2009_2021' AS table_name, COUNT(*) AS row_count
FROM raw_311_water_leaks_2009_2021

UNION ALL

SELECT 'raw_311_water_leaks_2021_present' AS table_name, COUNT(*) AS row_count
FROM raw_311_water_leaks_2021_present

UNION ALL

SELECT 'leakdata' AS table_name, COUNT(*) AS row_count
FROM leakdata;


SELECT
    leak_year,
    COUNT(*) AS leak_count
FROM leakdata
GROUP BY leak_year
ORDER BY leak_year;