CREATE SCHEMA IF NOT EXISTS sat_agentic;

CREATE TABLE IF NOT EXISTS sat_agentic.taxpayer_gold (
    year integer,
    region varchar(64),
    regime varchar(64),
    resico_flag boolean,
    taxpayer_count bigint,
    annual_income_total numeric(18,2),
    annual_income_avg numeric(18,2)
);

-- Load strategy:
-- 1. MRS writes reviewed aggregate CSV to obs://<bucket>/gold/sat/<run_id>/taxpayer_gold_csv/.
-- 2. DWS imports the CSV through an OBS foreign table or a DataArts DWS node.
-- 3. Do not place AK/SK in this SQL file. Prefer a DWS OBS agency/data source.
-- 4. After import, query:
--
-- SELECT year, region, regime, resico_flag, taxpayer_count, annual_income_total
-- FROM sat_agentic.taxpayer_gold
-- ORDER BY year, region, regime, resico_flag;
