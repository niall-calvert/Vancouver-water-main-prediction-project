-- ============================================================
-- CREATE FINAL MODEL DATASET
-- ============================================================
--
-- Purpose:
--   Create a filtered modeling dataset from final_pipe_year_data_with_target.
--
-- This script:
--   1. Removes rows from analysis_year = 2026
--   2. Drops columns that are not needed for modeling
--   3. Keeps leaks_next_year as the target column
--
-- Input table:
--   final_pipe_year_data_with_target
--
-- Output table:
--   final_model_data
--
-- ============================================================

DROP TABLE IF EXISTS final_model_data;

CREATE TABLE final_model_data AS
SELECT
    pipe_id,
    analysis_year,

    source_dataset,
    diameter_mm,
    installation_year,
    lining_material,
    material,
    lon,
    lat,

    pipe_age,
    leaked_that_year,
    leak_count_that_year,
    years_since_last_leak,
    most_recent_leak_year,
    nearest_leak_distance_m,
    average_leak_distance_m,

    leaks_next_year
FROM final_pipe_year_data_with_target
WHERE analysis_year <> 2026;


-- Add a fresh primary key.
ALTER TABLE final_model_data
ADD COLUMN id BIGSERIAL PRIMARY KEY;


-- Optional indexes.
CREATE INDEX IF NOT EXISTS idx_final_model_data_pipe_id
ON final_model_data (pipe_id);

CREATE INDEX IF NOT EXISTS idx_final_model_data_analysis_year
ON final_model_data (analysis_year);

CREATE INDEX IF NOT EXISTS idx_final_model_data_target
ON final_model_data (leaks_next_year);


-- ============================================================
-- QUICK CHECKS
-- ============================================================

SELECT COUNT(*) AS total_rows
FROM final_model_data;

SELECT
    analysis_year,
    COUNT(*) AS row_count
FROM final_model_data
GROUP BY analysis_year
ORDER BY analysis_year;

SELECT
    leaks_next_year,
    COUNT(*) AS row_count
FROM final_model_data
GROUP BY leaks_next_year
ORDER BY leaks_next_year;

SELECT *
FROM final_model_data
LIMIT 20;
