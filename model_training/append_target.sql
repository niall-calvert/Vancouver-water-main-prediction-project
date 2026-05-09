DROP TABLE IF EXISTS final_pipe_year_data_with_target;

CREATE TABLE final_pipe_year_data_with_target AS
WITH next_year_target AS (
    SELECT
        *,
        CASE
            WHEN LEAD(analysis_year) OVER (
                PARTITION BY pipe_id
                ORDER BY analysis_year
            ) = analysis_year + 1
            THEN LEAD(leaked_that_year) OVER (
                PARTITION BY pipe_id
                ORDER BY analysis_year
            )
            ELSE NULL
        END AS leaks_next_year
    FROM final_pipe_year_data
)

SELECT *
FROM next_year_target
WHERE leaks_next_year IS NOT NULL;


ALTER TABLE final_pipe_year_data_with_target
ADD COLUMN id BIGSERIAL PRIMARY KEY;


SELECT
    leaks_next_year,
    COUNT(*) AS row_count
FROM final_pipe_year_data_with_target
GROUP BY leaks_next_year
ORDER BY leaks_next_year;


SELECT COUNT(*) AS total_rows
FROM final_pipe_year_data_with_target;