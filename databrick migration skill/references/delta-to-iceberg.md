# Delta Lake to Iceberg Reference

## Scope

Use this reference for Databricks notebooks, PySpark, Scala Spark, Spark SQL, Auto Loader, Delta Live Tables-like demos, CDC merge scripts, and any code using `delta`, `DeltaTable`, `_delta_log`, `MERGE INTO`, `OPTIMIZE`, `VACUUM`, or Delta time travel.

## Table and Catalog Mapping

- Map Delta storage to OBS-backed Iceberg tables managed by MRS Spark.
- Replace `format("delta")` with Iceberg table writes through `saveAsTable`, `writeTo`, or `spark.sql("CREATE TABLE ... USING iceberg")`.
- Prefer explicit catalog configuration in Spark submit or session setup. Keep catalog names stable across scripts, for example `spark_catalog` for local/Hive-compatible demos or `iceberg_catalog` for configured Iceberg demos.
- Use fully qualified table names consistently: `<catalog>.<database>.<table>` when the demo depends on catalog behavior.
- Replace direct path table reads with table-name reads when possible. Use OBS paths for raw/bronze files and Iceberg table locations for managed lake tables.

## Common Rewrite Patterns

Delta write:

```python
df.write.format("delta").mode("append").save(delta_path)
```

Iceberg rewrite:

```python
df.writeTo("iceberg_catalog.demo.orders_bronze").append()
```

Delta table creation:

```sql
CREATE TABLE demo.orders USING DELTA LOCATION 'obs://bucket/path/orders'
```

Iceberg rewrite:

```sql
CREATE TABLE IF NOT EXISTS iceberg_catalog.demo.orders (
  order_id STRING,
  updated_at TIMESTAMP,
  amount DECIMAL(18,2)
) USING iceberg
PARTITIONED BY (days(updated_at));
```

Delta merge:

```sql
MERGE INTO target t
USING source s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

Iceberg rewrite:

```sql
MERGE INTO iceberg_catalog.demo.target t
USING staging_view s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

Check the MRS Spark/Iceberg version. If `MERGE INTO` is unavailable or unstable, rewrite CDC as:

1. Deduplicate source changes by primary key and sequence/timestamp.
2. Anti-join current target rows by affected keys.
3. Union unaffected current rows with latest non-delete changes.
4. Overwrite the affected partition set or replace the whole small demo table.

## Databricks Script Rewrite Checklist

Use this checklist when converting Databricks PySpark notebooks/scripts into MRS Spark + Iceberg scripts:

- Replace `df.write.format("delta")` with Iceberg writes. Prefer table writes such as `writeTo(...).append()` or `saveAsTable(...)` over path-only writes for migrated demos.
- Replace `spark.read.format("delta")` with Iceberg table reads. Prefer `spark.table("db.table")` or `spark.read.format("iceberg").load("db.table")` when the source config can hold table names.
- Remove or rewrite Delta-only options such as `.option("overwriteSchema", "true")`. Use explicit Iceberg DDL evolution, `ALTER TABLE ADD COLUMN`, or controlled overwrite behavior instead.
- Update source configuration files so format declarations change from `delta` to `iceberg`.
- Convert Databricks storage paths such as `dbfs:/mnt/...` or mounted paths into the target table namespace or HDFS/OBS path used by the MRS demo.
- If a source CSV/config maps table names to paths, prefer changing path columns into `database.table` names for Iceberg tables. Path-style Iceberg reads can fail with missing metadata such as `version-hint.text` when the path is not a valid Iceberg table root.
- For generated demo data, create missing Iceberg DDL explicitly before inserts. Do not assume source Databricks notebooks contain all required `CREATE TABLE` statements.

## CDC Semantics

Preserve these fields when present:

- primary key or composite merge key
- operation code such as `I`, `U`, `D`
- event timestamp and ingestion timestamp
- sequence, log position, or batch id
- before/after images

For demo CDC, prefer deterministic small batches and explicit validation queries:

```sql
SELECT op, count(*) FROM staging_changes GROUP BY op;
SELECT count(*) AS duplicate_keys
FROM (
  SELECT id, count(*) c FROM iceberg_catalog.demo.target GROUP BY id HAVING c > 1
) d;
```

## Delta Features and Replacements

- Time travel: replace `VERSION AS OF` or `TIMESTAMP AS OF` with snapshot inspection if Iceberg metadata is available; otherwise materialize before/after demo tables.
- Change Data Feed: replace with explicit CDC source files or staged change tables.
- `OPTIMIZE` and ZORDER: remove for small demos; use partitioning, file-size write options, or compaction procedures only when MRS supports them.
- `VACUUM`: replace with Iceberg snapshot expiration only when configured and safe for the demo.
- Schema evolution: prefer explicit DDL migrations. Use `ALTER TABLE ADD COLUMN` rather than relying on implicit merge schema behavior.
- Generated columns and constraints: materialize generated values in Spark transforms unless DWS or Iceberg target supports them directly.

## Validation Checklist

- Confirm row counts by table and CDC operation.
- Confirm delete semantics by checking missing deleted keys.
- Confirm latest-version semantics for updated keys.
- Confirm partition pruning columns still exist.
- Confirm OBS paths and Iceberg table names are parameterized for the demo environment.
