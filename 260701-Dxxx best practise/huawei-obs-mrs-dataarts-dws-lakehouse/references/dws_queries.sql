-- DockOne Golden DWS validation and BI examples.
-- Keep these read-only unless the user explicitly asks for a warehouse mutation.

-- 1. List DockOne Golden tables/views.
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'dockone_golden'
ORDER BY table_type, table_name;

-- 2. Count Golden metric rows.
SELECT COUNT(*) AS metric_rows
FROM dockone_golden.table_metrics;

-- 3. BI-ready domain aggregate.
SELECT
  domain,
  COUNT(*) AS table_count,
  SUM(record_count) AS total_records,
  SUM(active_count) AS active_records,
  SUM(delete_count) AS deleted_records
FROM dockone_golden.table_metrics_bi
GROUP BY domain
ORDER BY total_records DESC;

-- 4. Table-level quality/status view.
SELECT
  domain,
  table_name,
  table_category,
  table_type,
  record_count,
  active_count,
  delete_count,
  latest_event_time,
  loaded_at
FROM dockone_golden.table_metrics_bi
ORDER BY domain, table_name;

-- 5. Latest load timestamp.
SELECT MAX(loaded_at) AS latest_loaded_at
FROM dockone_golden.table_metrics;

-- 6. Largest active tables.
SELECT
  domain,
  table_name,
  active_count
FROM dockone_golden.table_metrics_bi
ORDER BY active_count DESC
LIMIT 20;

-- 7. Delete ratio by domain.
SELECT
  domain,
  SUM(delete_count) AS deleted_records,
  SUM(record_count) AS total_records,
  CASE
    WHEN SUM(record_count) = 0 THEN 0
    ELSE ROUND(SUM(delete_count)::numeric / SUM(record_count), 6)
  END AS delete_ratio
FROM dockone_golden.table_metrics_bi
GROUP BY domain
ORDER BY delete_ratio DESC;
