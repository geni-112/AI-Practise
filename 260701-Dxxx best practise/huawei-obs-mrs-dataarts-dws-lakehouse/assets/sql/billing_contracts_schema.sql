CREATE SCHEMA IF NOT EXISTS billing;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- PostgreSQL versions before native uuidv7 support need a compatibility
-- function so the table default can be created. The data generator inserts
-- UUIDv7 values explicitly; this fallback exists only for the DEFAULT clause.
CREATE OR REPLACE FUNCTION public.uuidv7()
RETURNS uuid
LANGUAGE sql
VOLATILE
AS $$
  SELECT gen_random_uuid();
$$;

CREATE TABLE IF NOT EXISTS billing.contracts (
  id uuid DEFAULT uuidv7() NOT NULL,
  client_id uuid DEFAULT current_setting('app.client_id'::text)::uuid NOT NULL,
  product_id uuid NOT NULL,
  account_id uuid NULL,
  person_id uuid NOT NULL,
  external_id varchar(255) DEFAULT NULL::character varying NULL,
  description varchar(255) DEFAULT NULL::character varying NULL,
  status varchar(100) NOT NULL,
  overdue_at timestamptz NULL,
  amount_asset_iso_code varchar(3) NOT NULL,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz NULL,
  profile_id uuid NOT NULL,
  cycle_id uuid NOT NULL,
  first_due_date date NOT NULL,
  effective_date timestamptz NOT NULL,
  contracted_amount numeric(21, 8) NOT NULL,
  CONSTRAINT contracts_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS contracts_updated_at_idx
ON billing.contracts (updated_at);

CREATE INDEX IF NOT EXISTS contracts_client_id_idx
ON billing.contracts (client_id);
