SELECT
    leaked_that_year,
    COUNT(*) AS row_count
FROM final_pipe_year_data
GROUP BY leaked_that_year
ORDER BY leaked_that_year;