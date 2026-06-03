SELECT
  '${table_name}' AS table_name,
  COUNT(1) AS silver_rows,
  COUNT(DISTINCT id) AS distinct_ids
FROM ${silver_hudi_table_name}
