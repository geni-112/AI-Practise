# Synthetic CDC Data

This dataset is generated from inferred table schemas because the Databricks script archive does not contain real customer DDL, schema checkpoint files, or raw CDC samples.

## Contents

- `raw/`: CDC JSON Lines files using the Databricks version 1 envelope: `before`, `after`, `op`, `source`, `ts_ms`.
- `schema/inferred-table-schemas.json`: inferred schema for all 21 task tables.
- `schema/inferred-table-ddl.sql`: SQL DDL for the inferred silver table shapes.
- `manifest.json`: table paths, event counts, and generation metadata.

## Generation Defaults

- Random seed: `20260602`
- Tables: `21`
- Events per table: `1250`
- Operation mix per table: `50 r`, `950 c`, `200 u`, `50 d`.
- Delete events set `after` to `null` and keep the deleted record in `before`.

## Compatibility Notes

- Every table includes `id`, `created_at`, `update_date`, `tenant_id`, and `source_system`.
- Non-delete events include `after.id`; delete events include `before.id`.
- The data is synthetic and contains no real PII.
- Replace this inferred dataset with real DDL or raw CDC samples if those become available.
