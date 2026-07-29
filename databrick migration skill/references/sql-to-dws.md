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
- Validate every CTE header. A Spark SQL CTE must use `cte_name AS (...)`
  unless an explicit column-alias list appears before `AS`; a source fragment
  such as `padron_completo(` followed directly by `SELECT` is incomplete.

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

1. Add or identify a key that uniquely represents each original outer row.
2. Build a staged `LEFT JOIN` between the outer table and
   `TEMP_PADRON_ARSE_RESICO`, keeping the equality and date-range predicates in
   the `ON` clause so unmatched outer rows are preserved.
3. Aggregate by the original outer-row key and compute the marker with
   `MAX(CASE WHEN B.<non_null_key> IS NOT NULL THEN 1 ELSE 0 END)`.
4. Join the marker back to the outer projection, or explicitly group by every
   selected outer column.

Example rewrite:

```sql
WITH PADRON_CON_ID AS (
  SELECT
    p.*,
    ROW_NUMBER() OVER (
      ORDER BY C_IDC_RFCEEOG1, C_IDC_ICDOENN1, Periodo_inicio, Perido_fin
    ) AS outer_row_id
  FROM padron_completo p
),
RESICO_MARCA AS (
  SELECT
    a.outer_row_id,
    MAX(
      CASE WHEN b.C_IDC_ICDOENN1 IS NOT NULL THEN 1 ELSE 0 END
    ) AS MARACA_REGIMEN_RESICO
  FROM PADRON_CON_ID a
  LEFT JOIN TEMP_PADRON_ARSE_RESICO b
    ON a.C_IDC_ICDOENN1 = b.C_IDC_ICDOENN1
   AND b.Fecha_Alta <= DATE_ADD(a.Perido_fin, -1)
   AND b.fecha_efectiva_baja >= a.Periodo_inicio
  GROUP BY a.outer_row_id
)
SELECT
  a.C_IDC_RFCEEOG1,
  a.C_IDC_ICDOENN1,
  a.Periodo_inicio,
  a.Perido_fin,
  m.MARACA_REGIMEN_RESICO
FROM PADRON_CON_ID a
LEFT JOIN RESICO_MARCA m
  ON a.outer_row_id = m.outer_row_id;
```

Use a stable source primary key instead of the example `ROW_NUMBER()` whenever
one exists. The rewrite avoids Catalyst's `LeftExistenceJoin` path for complex
non-equality correlated predicates and prevents multiple RESICO matches from
duplicating outer rows.

Grouping only by all projected outer columns, as in:

```sql
GROUP BY A.EJERCICIO, A.PERIODO, A.Periodo_inicio, A.Perido_fin,
         A.C_IDC_ICDOENN1, A.C_IDC_RFCEEOG1
```

is a reasonable small-demo fallback, but it can collapse duplicate outer rows
that the original correlated `EXISTS` would preserve. For production-equivalent
behavior, aggregate by a stable unique outer-row key and compare pre/post row
counts and duplicate multiplicity.

For the other observed Spark SQL incompatibilities:

```sql
-- SQL Server-style source
DATEADD(month, 1, Periodo_inicio)

-- Spark SQL
add_months(Periodo_inicio, 1)
```

```sql
-- Unsupported BigQuery/Snowflake-style shorthand
SELECT * EXCEPT(Periodo_inicio, Perido_fin, C_IDC_ICDOENN1)

-- Spark SQL: enumerate only the columns that must survive
SELECT C_IDC_RFCEEOG1, EJERCICIO, PERIODO, MARACA_REGIMEN_RESICO
```

Derive the explicit projection from the input schema and downstream consumers;
do not guess the omitted or retained columns.

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
