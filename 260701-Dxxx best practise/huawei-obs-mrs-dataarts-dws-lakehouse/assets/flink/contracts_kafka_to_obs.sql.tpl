-- MRS Flink SQL: DMS Kafka billing.contracts CDC stream to OBS raw JSON.
-- Render this file with scripts/streaming/render_contracts_flink_sql.py.
-- If DMS Kafka requires SASL, keep the password as a runtime secret and do
-- not commit rendered SQL containing a real password.

CREATE TABLE dms_billing_contracts_cdc (
  op STRING,
  ts_ms BIGINT,
  source ROW<db STRING, `schema` STRING, `table` STRING>,
  before ROW<
    id STRING,
    client_id STRING,
    product_id STRING,
    account_id STRING,
    person_id STRING,
    external_id STRING,
    description STRING,
    status STRING,
    overdue_at STRING,
    amount_asset_iso_code STRING,
    created_at STRING,
    updated_at STRING,
    profile_id STRING,
    cycle_id STRING,
    first_due_date STRING,
    effective_date STRING,
    contracted_amount STRING
  >,
  after ROW<
    id STRING,
    client_id STRING,
    product_id STRING,
    account_id STRING,
    person_id STRING,
    external_id STRING,
    description STRING,
    status STRING,
    overdue_at STRING,
    amount_asset_iso_code STRING,
    created_at STRING,
    updated_at STRING,
    profile_id STRING,
    cycle_id STRING,
    first_due_date STRING,
    effective_date STRING,
    contracted_amount STRING
  >
) WITH (
  'connector' = 'kafka',
  'topic' = '${kafka_topic}',
  'properties.bootstrap.servers' = '${kafka_bootstrap_servers}',
  'properties.group.id' = '${kafka_group_id}',
${kafka_security_properties}  'scan.startup.mode' = '${scan_startup_mode}',
  'format' = 'json',
  'json.ignore-parse-errors' = 'true',
  'json.fail-on-missing-field' = 'false'
);

CREATE TABLE obs_billing_contracts_raw (
  op STRING,
  ts_ms BIGINT,
  source ROW<db STRING, `schema` STRING, `table` STRING>,
  before ROW<
    id STRING,
    client_id STRING,
    product_id STRING,
    account_id STRING,
    person_id STRING,
    external_id STRING,
    description STRING,
    status STRING,
    overdue_at STRING,
    amount_asset_iso_code STRING,
    created_at STRING,
    updated_at STRING,
    profile_id STRING,
    cycle_id STRING,
    first_due_date STRING,
    effective_date STRING,
    contracted_amount STRING
  >,
  after ROW<
    id STRING,
    client_id STRING,
    product_id STRING,
    account_id STRING,
    person_id STRING,
    external_id STRING,
    description STRING,
    status STRING,
    overdue_at STRING,
    amount_asset_iso_code STRING,
    created_at STRING,
    updated_at STRING,
    profile_id STRING,
    cycle_id STRING,
    first_due_date STRING,
    effective_date STRING,
    contracted_amount STRING
  >
) WITH (
  'connector' = 'filesystem',
  'path' = '${obs_raw_path}',
  'format' = 'json',
  'sink.rolling-policy.file-size' = '8MB',
  'sink.rolling-policy.rollover-interval' = '60 s',
  'sink.rolling-policy.check-interval' = '10 s'
);

INSERT INTO obs_billing_contracts_raw
SELECT op, ts_ms, source, before, after
FROM dms_billing_contracts_cdc;
