-- ============================================================
-- BUILD PIPE-YEAR TABLE, 2016–2026
-- ============================================================
--
-- Purpose:
--   Create one row for every pipe in main for every analysis year.
--
-- Required input table:
--   main
--
-- Final output table:
--   pipe_year_data
--
-- ============================================================

BEGIN;

DROP TABLE IF EXISTS pipe_year_data;

CREATE TABLE pipe_year_data AS
WITH years AS (
    SELECT generate_series(2016, 2026)::INTEGER AS analysis_year
)
SELECT
    m.id AS pipe_id,
    y.analysis_year,

    m.source_dataset,
    m.diameter_mm,
    m.installation_year,
    m.lining_material,
    m.material,
    m.lon,
    m.lat,
    m.geom,

    CASE
        WHEN m.installation_year IS NULL THEN NULL
        ELSE y.analysis_year - m.installation_year
    END AS pipe_age

FROM main m
CROSS JOIN years y
WHERE m.installation_year IS NULL
   OR y.analysis_year >= m.installation_year
ORDER BY
    m.id,
    y.analysis_year;

ALTER TABLE pipe_year_data
ADD COLUMN id BIGSERIAL PRIMARY KEY;

CREATE INDEX IF NOT EXISTS idx_pipe_year_data_pipe_id
ON pipe_year_data (pipe_id);

CREATE INDEX IF NOT EXISTS idx_pipe_year_data_analysis_year
ON pipe_year_data (analysis_year);

CREATE INDEX IF NOT EXISTS idx_pipe_year_data_pipe_year
ON pipe_year_data (pipe_id, analysis_year);

ANALYZE pipe_year_data;

-- ============================================================
-- QUICK CHECKS
-- ============================================================

SELECT
    'main' AS table_name,
    COUNT(*) AS row_count
FROM main

UNION ALL

SELECT
    'pipe_year_data' AS table_name,
    COUNT(*) AS row_count
FROM pipe_year_data;

SELECT
    analysis_year,
    COUNT(*) AS pipe_count
FROM pipe_year_data
GROUP BY analysis_year
ORDER BY analysis_year;

SELECT *
FROM pipe_year_data
LIMIT 20;

COMMIT;