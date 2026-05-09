-- ============================================================
-- BUILD FINAL PIPE-YEAR MODELING TABLE
-- ============================================================
--
-- Purpose:
--   Combine pipe_year_data with matched leak data.
--
-- Required input tables:
--   pipe_year_data
--   leak_pipe_match
--
-- Final output table:
--   final_pipe_year_data
--
-- Final output includes:
--   pipe_id
--   analysis_year
--   pipe_age
--   pipe attributes
--   leaked_that_year
--   leak_count_that_year
--   years_since_last_leak
--
-- ============================================================

BEGIN;

-- ============================================================
-- 1. AGGREGATE LEAKS BY PIPE-YEAR
-- ============================================================

DROP TABLE IF EXISTS leak_pipe_year_agg;

CREATE TABLE leak_pipe_year_agg AS
SELECT
    pipe_id,
    leak_year AS analysis_year,

    COUNT(*) AS leak_count_that_year,
    MIN(distance_m) AS nearest_leak_distance_m,
    AVG(distance_m) AS average_leak_distance_m

FROM leak_pipe_match
GROUP BY
    pipe_id,
    leak_year;

CREATE INDEX IF NOT EXISTS idx_leak_pipe_year_agg_pipe_year
ON leak_pipe_year_agg (pipe_id, analysis_year);

ANALYZE leak_pipe_year_agg;


-- ============================================================
-- 2. JOIN LEAK COUNTS ONTO PIPE-YEAR DATA
-- ============================================================

DROP TABLE IF EXISTS pipe_year_with_leaks;

CREATE TABLE pipe_year_with_leaks AS
SELECT
    p.id AS pipe_year_row_id,
    p.pipe_id,
    p.analysis_year,

    p.source_dataset,
    p.diameter_mm,
    p.installation_year,
    p.lining_material,
    p.material,
    p.lon,
    p.lat,
    p.geom,
    p.pipe_age,

    CASE
        WHEN COALESCE(a.leak_count_that_year, 0) > 0 THEN 1
        ELSE 0
    END AS leaked_that_year,

    COALESCE(a.leak_count_that_year, 0) AS leak_count_that_year,

    a.nearest_leak_distance_m,
    a.average_leak_distance_m

FROM pipe_year_data p
LEFT JOIN leak_pipe_year_agg a
    ON p.pipe_id = a.pipe_id
   AND p.analysis_year = a.analysis_year;

CREATE INDEX IF NOT EXISTS idx_pipe_year_with_leaks_pipe_year
ON pipe_year_with_leaks (pipe_id, analysis_year);

CREATE INDEX IF NOT EXISTS idx_pipe_year_with_leaks_year
ON pipe_year_with_leaks (analysis_year);

ANALYZE pipe_year_with_leaks;


-- ============================================================
-- 3. CALCULATE YEARS SINCE LAST LEAK
-- ============================================================
--
-- Logic:
--   - If the pipe leaked in the current year, years_since_last_leak = 0.
--   - If the pipe leaked in a previous year, subtract that previous leak year.
--   - If the pipe has never leaked before or during that year, return NULL.
--
-- Example:
--   pipe leaked in 2018 and 2021
--
--   2017 -> NULL
--   2018 -> 0
--   2019 -> 1
--   2020 -> 2
--   2021 -> 0
--   2022 -> 1
--
-- ============================================================

DROP TABLE IF EXISTS final_pipe_year_data;

CREATE TABLE final_pipe_year_data AS
WITH leak_history AS (
    SELECT
        *,

        MAX(
            CASE
                WHEN leaked_that_year = 1 THEN analysis_year
                ELSE NULL
            END
        ) OVER (
            PARTITION BY pipe_id
            ORDER BY analysis_year
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS most_recent_leak_year

    FROM pipe_year_with_leaks
)

SELECT
    pipe_year_row_id,
    pipe_id,
    analysis_year,

    source_dataset,
    diameter_mm,
    installation_year,
    lining_material,
    material,
    lon,
    lat,
    geom,
    pipe_age,

    leaked_that_year,
    leak_count_that_year,

    CASE
        WHEN most_recent_leak_year IS NULL THEN NULL
        ELSE analysis_year - most_recent_leak_year
    END AS years_since_last_leak,

    most_recent_leak_year,

    nearest_leak_distance_m,
    average_leak_distance_m

FROM leak_history
ORDER BY
    pipe_id,
    analysis_year;

ALTER TABLE final_pipe_year_data
ADD COLUMN id BIGSERIAL PRIMARY KEY;

CREATE INDEX IF NOT EXISTS idx_final_pipe_year_data_pipe_id
ON final_pipe_year_data (pipe_id);

CREATE INDEX IF NOT EXISTS idx_final_pipe_year_data_analysis_year
ON final_pipe_year_data (analysis_year);

CREATE INDEX IF NOT EXISTS idx_final_pipe_year_data_pipe_year
ON final_pipe_year_data (pipe_id, analysis_year);

CREATE INDEX IF NOT EXISTS idx_final_pipe_year_data_leaked_that_year
ON final_pipe_year_data (leaked_that_year);

ANALYZE final_pipe_year_data;


-- ============================================================
-- 4. QUICK CHECKS
-- ============================================================

SELECT
    'pipe_year_data' AS table_name,
    COUNT(*) AS row_count
FROM pipe_year_data

UNION ALL

SELECT
    'leak_pipe_match' AS table_name,
    COUNT(*) AS row_count
FROM leak_pipe_match

UNION ALL

SELECT
    'leak_pipe_year_agg' AS table_name,
    COUNT(*) AS row_count
FROM leak_pipe_year_agg

UNION ALL

SELECT
    'final_pipe_year_data' AS table_name,
    COUNT(*) AS row_count
FROM final_pipe_year_data;

SELECT
    analysis_year,
    COUNT(*) AS pipe_year_rows,
    SUM(leaked_that_year) AS pipe_years_with_leak,
    SUM(leak_count_that_year) AS total_matched_leaks
FROM final_pipe_year_data
GROUP BY analysis_year
ORDER BY analysis_year;

SELECT *
FROM final_pipe_year_data
ORDER BY pipe_id, analysis_year
LIMIT 30;

COMMIT;