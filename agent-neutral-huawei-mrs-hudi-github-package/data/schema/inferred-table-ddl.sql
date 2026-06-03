CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_payment_outbox (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  payment_id STRING NOT NULL,
  account_id STRING NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  method STRING NOT NULL,
  provider STRING NOT NULL,
  external_reference STRING,
  event_type STRING,
  payload STRING,
  outbox_topic STRING,
  published_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_payment_payments (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  payment_id STRING NOT NULL,
  account_id STRING NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  method STRING NOT NULL,
  provider STRING NOT NULL,
  external_reference STRING,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_payment_events (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  payment_id STRING NOT NULL,
  account_id STRING NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  method STRING NOT NULL,
  provider STRING NOT NULL,
  external_reference STRING,
  event_type STRING,
  payload STRING,
  event_version INT
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_account_configurations (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_parameters (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_inbound_operation_step_status_configurations (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_outbound_operation_step_configurations (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_generated_event_logs (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING,
  event_version INT
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_connector_restriction_logs (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  connector_id STRING NOT NULL,
  account_id STRING NOT NULL,
  operation_id STRING,
  operation_type STRING,
  step_name STRING,
  status STRING NOT NULL,
  parameter_name STRING,
  parameter_value STRING,
  restriction_reason STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_profiles (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_cycles (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_contracts (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_operations (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_statements (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_installments (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_statement_components (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_events (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING,
  event_version INT
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_installment_events (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING,
  event_version INT
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_installment_components (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_contracts_additional_data (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING,
  additional_data_json STRING
);

CREATE TABLE IF NOT EXISTS dockone_silver.dockone_exampleapp_billing_outbox (
  id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  update_date TIMESTAMP NOT NULL,
  tenant_id STRING NOT NULL,
  source_system STRING NOT NULL,
  profile_id STRING,
  contract_id STRING,
  cycle_id STRING,
  statement_id STRING,
  installment_id STRING,
  component_id STRING,
  amount DECIMAL(18,2) NOT NULL,
  currency STRING NOT NULL,
  status STRING NOT NULL,
  due_date DATE,
  event_type STRING,
  payload STRING,
  outbox_topic STRING,
  published_at TIMESTAMP
);
