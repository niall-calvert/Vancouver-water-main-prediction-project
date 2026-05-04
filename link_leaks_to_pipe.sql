-- ============================================================
-- FAST LINK 311 LEAKS TO NEAREST PIPE
-- ============================================================
--
-- Purpose:
--   Link each cleaned 311 leak to the nearest physical pipe.
--
-- Required input tables:
--   main
--   leakdata
--
-- Final output table:
--   leak_pipe_match
--
-- Notes:
--   - Uses EPSG:26910, UTM Zone 10N, appropriate for Vancouver-area
--     meter-based distance calculations.
--   - The search radius is currently 25 meters.
--   - This script assumes main.geom is valid GeoJSON for pipe lines.
--   - Leak points are created from longitude/latitude, not leakdata.geom.
--
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. ADD PROJECTED PIPE GEOMETRY TO MAIN
-- ============================================================

ALTER TABLE main
ADD COLUMN IF NOT EXISTS geom_line_utm geometry(Geometry, 26910);

UPDATE main
SET geom_line_utm = ST_Transform(
    ST_SetSRID(ST_GeomFromGeoJSON(geom::text), 4326),
    26910
)
WHERE geom IS NOT NULL
  AND geom <> 'null'::jsonb
  AND jsonb_typeof(geom) = 'object'
  AND geom->>'type' IS NOT NULL
  AND geom->'coordinates' IS NOT NULL
  AND geom_line_utm IS NULL;


-- ============================================================
-- 2. ADD PROJECTED GEOMETRY TO LEAKDATA
-- ============================================================

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


-- ============================================================
-- 3. INDEXES FOR FAST SPATIAL MATCHING
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_main_geom_line_utm
ON main
USING GIST (geom_line_utm);

CREATE INDEX IF NOT EXISTS idx_leakdata_geom_utm
ON leakdata
USING GIST (geom_utm);

CREATE INDEX IF NOT EXISTS idx_main_installation_year
ON main (installation_year);

CREATE INDEX IF NOT EXISTS idx_leakdata_leak_year
ON leakdata (leak_year);

ANALYZE main;
ANALYZE leakdata;


-- ============================================================
-- 4. MATCH EACH LEAK TO NEAREST VALID PIPE
-- ============================================================

DROP TABLE IF EXISTS leak_pipe_match;

CREATE TABLE leak_pipe_match AS
SELECT
    l.id AS leak_id,
    l.leak_year,
    m.id AS pipe_id,

    m.source_dataset,
    m.diameter_mm,
    m.installation_year,
    m.lining_material,
    m.material,
    m.lon AS pipe_lon,
    m.lat AS pipe_lat,

    l.longitude AS leak_longitude,
    l.latitude AS leak_latitude,

    ST_Distance(l.geom_utm, m.geom_line_utm) AS distance_m

FROM leakdata l
JOIN LATERAL (
    SELECT
        m.*
    FROM main m
    WHERE m.geom_line_utm IS NOT NULL

      -- IMPORTANT:
      -- Compare leak point to pipe line geometry.
      -- Do not use m.geom_utm here; main does not have that column.
      AND ST_DWithin(l.geom_utm, m.geom_line_utm, 25)

      AND (
          m.installation_year IS NULL
          OR l.leak_year >= m.installation_year
      )
    ORDER BY
        ST_Distance(l.geom_utm, m.geom_line_utm),
        m.id ASC
    LIMIT 1
) m ON true
WHERE l.geom_utm IS NOT NULL
  AND l.leak_year IS NOT NULL
  AND l.leak_year BETWEEN 2016 AND 2026;

ALTER TABLE leak_pipe_match
ADD COLUMN id BIGSERIAL PRIMARY KEY;

CREATE INDEX IF NOT EXISTS idx_leak_pipe_match_pipe_id
ON leak_pipe_match (pipe_id);

CREATE INDEX IF NOT EXISTS idx_leak_pipe_match_leak_year
ON leak_pipe_match (leak_year);

CREATE INDEX IF NOT EXISTS idx_leak_pipe_match_pipe_year
ON leak_pipe_match (pipe_id, leak_year);

CREATE INDEX IF NOT EXISTS idx_leak_pipe_match_leak_id
ON leak_pipe_match (leak_id);

ANALYZE leak_pipe_match;


-- ============================================================
-- 5. QUICK CHECKS
-- ============================================================

SELECT
    'leakdata' AS table_name,
    COUNT(*) AS row_count
FROM leakdata

UNION ALL

SELECT
    'leak_pipe_match' AS table_name,
    COUNT(*) AS row_count
FROM leak_pipe_match;

SELECT
    leak_year,
    COUNT(*) AS matched_leak_count
FROM leak_pipe_match
GROUP BY leak_year
ORDER BY leak_year;

SELECT
    COUNT(*) AS matched_leaks,
    MIN(distance_m) AS min_distance_m,
    AVG(distance_m) AS avg_distance_m,
    MAX(distance_m) AS max_distance_m
FROM leak_pipe_match;

COMMIT;
