# Snowflake/Databricks SQL to DWS Reference

## Scope

Use this reference when converting Snowflake SQL, Databricks SQL, Spark SQL, warehouse DDL/DML, BI queries, or ELT scripts into GaussDB(DWS)-compatible demo SQL.

## General Rules

- Translate syntax conservatively and preserve query intent.
- Prefer explicit schemas, column types, and casts.
- Replace platform-specific convenience functions with DWS/PostgreSQL-style equivalents where possible.
- For unsupported syntax, split into staging CTEs or temp tables.
- Add validation queries after transformed DDL/DML.

## Type Mapping

| Source | DWS demo target |
| --- | --- |
| STRING, VARCHAR | VARCHAR(n) or TEXT for demo staging |
| NUMBER(p,s), DECIMAL | DECIMAL(p,s) |
| DOUBLE, FLOAT | DOUBLE PRECISION |
| BOOLEAN | BOOLEAN |
| TIMESTAMP_NTZ | TIMESTAMP |
| TIMESTAMP_LTZ/TZ | TIMESTAMPTZ if needed, otherwise TIMESTAMP plus timezone note |
| VARIANT, OBJECT, ARRAY | JSON/text staging or normalized columns |
| BINARY | BYTEA |

## Syntax Mapping

| Source pattern | DWS rewrite |
| --- | --- |
| `QUALIFY row_number() ... = 1` | Wrap in CTE and filter by `rn` |
| `IFF(cond,a,b)` | `CASE WHEN cond THEN a ELSE b END` |
| `NVL(a,b)` | `COALESCE(a,b)` |
| `DATEADD(day, n, d)` | `d + (n * INTERVAL '1 day')` or DWS-supported date function |
| `DATEDIFF(day, a, b)` | Date arithmetic or DWS-supported date diff |
| `TRY_TO_NUMBER(x)` | guarded cast with regex or staging cleanup |
| `::TYPE` | `CAST(x AS TYPE)` when portability matters |
| `MERGE` | Use DWS-supported `MERGE` if available; otherwise update then insert |
| `COPY INTO` Snowflake | OBS-to-DWS load command or external table/load script used by the demo |
| `CREATE OR REPLACE TABLE` | `DROP TABLE IF EXISTS` then `CREATE TABLE`, or `CREATE TABLE IF NOT EXISTS` |
| `DATEADD(month, 1, col)` in SQL Server-style SQL | Use Spark `add_months(col, 1)` before lake processing; use DWS-compatible date arithmetic in warehouse SQL |
| `SELECT * EXCEPT(col1, col2)` | Explicitly enumerate required columns |

## QUALIFY Rewrite

Source:

```sql
SELECT *
FROM orders
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) = 1;
```

DWS:

```sql
WITH ranked AS (
  SELECT
    o.*,
    ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) AS rn
  FROM orders o
)
SELECT *
FROM ranked
WHERE rn = 1;
```

## MERGE Fallback

When native `MERGE` is unsuitable for a demo, use explicit update/insert:

```sql
UPDATE target t
SET amount = s.amount,
    updated_at = s.updated_at
FROM staging_latest s
WHERE t.order_id = s.order_id;

INSERT INTO target (order_id, amount, updated_at)
SELECT s.order_id, s.amount, s.updated_at
FROM staging_latest s
LEFT JOIN target t ON t.order_id = s.order_id
WHERE t.order_id IS NULL;
```

Handle deletes separately:

```sql
DELETE FROM target t
USING staging_latest s
WHERE t.order_id = s.order_id
  AND s.op = 'D';
```

## Spark SQL Compatibility Before DWS/Iceberg Output

Some Databricks/Snowflake migrations pass through Spark SQL on MRS before data reaches DWS. Capture these rewrites in migration docs:

- Avoid complex correlated `EXISTS` subqueries with non-equality predicates such as `<=` and `>=` when Spark Catalyst produces missing-attribute errors. Rewrite to `LEFT JOIN` plus `GROUP BY` or a staged CTE.
- Rewrite SQL Server-style `DATEADD(month, 1, Periodo_inicio)` to Spark `add_months(Periodo_inicio, 1)`.
- Rewrite `SELECT * EXCEPT(...)` by explicitly listing the projected columns. Spark SQL does not support this BigQuery/Snowflake-style shorthand natively.

Example risky source:

```sql
CASE WHEN EXISTS (
  SELECT 1
  FROM TEMP_PADRON_ARSE_RESICO B
  WHERE A.C_IDC_ICDOENN1 = B.C_IDC_ICDOENN1
    AND B.Fecha_Alta <= DATE_ADD(A.Perido_fin, -1)
    AND B.fecha_efectiva_baja >= A.Periodo_inicio
) THEN 1 END AS MARACA_REGIMEN_RESICO
```

Preferred migration direction:

1. Build a staged join between the outer table and `TEMP_PADRON_ARSE_RESICO`.
2. Evaluate the non-equality date predicates in the join or filter stage.
3. Aggregate by the original row key and compute the marker with `MAX(CASE WHEN ... THEN 1 ELSE 0 END)`.

## DDL Guidance

- Add distribution and sort choices only when the demo needs performance realism. Otherwise keep DDL portable and readable.
- Use schema names such as `demo_raw`, `demo_curated`, and `demo_mart`.
- Keep object names lowercase unless source compatibility requires quoting.
- Avoid quoted identifiers in generated DWS SQL unless the source relies on case-sensitive names.

## Validation Queries

Include compact checks:

```sql
SELECT COUNT(*) AS row_count FROM demo_mart.orders;
SELECT COUNT(DISTINCT order_id) AS distinct_orders FROM demo_mart.orders;
SELECT order_status, COUNT(*) FROM demo_mart.orders GROUP BY order_status ORDER BY 2 DESC;
```
