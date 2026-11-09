# MCP and DWS integration

The route is FastAPI identity → openJiuwen Workflow → scoped openJiuwen MCP client → packaged stdio MCP server → psycopg2 → DWS. It uses the MCP protocol as the tool interface and the PostgreSQL-compatible driver for actual database traffic. The package does not register or assume a Huawei-hosted MCP service.

## Connect an existing DWS

1. Obtain the authorized private endpoint, database name, reader account and CA trust. The API/MCP host must have a route to the DWS VPC. Do not add a DWS public endpoint merely for convenience.
2. Configure the backend's private `.env` or secure environment. Keep empty values out of public docs:

   ```dotenv
   DATA_BACKEND=dws
   DWS_HOST=
   DWS_PORT=8000
   DWS_DATABASE=gaussdb
   DWS_USER=
   DWS_PASSWORD=
   DWS_SSLMODE=verify-full
   DWS_SSLROOTCERT=
   ```

3. Use `verify-full` when the server certificate matches the endpoint. Huawei's documented CA setup can use `verify-ca` with the official trusted CA. Never use `sslmode=disable`, `require` alone as a substitute for verification, or disable HTTP TLS checks. Certificate files are operator-provided local artifacts, not bundled secrets.
4. The current query compiler maps internal datasets to `internal.*`, external feed datasets to `external.*`; `tenants` is control data under `governance`. Reconcile mappings before connecting a different schema. Arbitrary enterprise schemas are not automatically semantic models.
5. Validate a limited read with a reader account, then a scoped ChatBI query and CSV reconciliation. Check domain denial, regional restrictions, tenant boundaries and export denial separately.

MCP server sessions bind the server-resolved tenant/persona. The query path uses read-only DWS sessions, a statement timeout and parameter binding. Scope checks remain necessary even if the connection itself succeeds. API health `dws_connected=true` means a connection check passed, not that all dataset mappings or permissions are correct.

## Import only the synthetic demo

Use a dedicated empty demonstration database/schema and an explicitly authorized loading account. `scripts/load_dws.py` reads credentials from the **process environment**, not `.env` by itself:

```bash
.venv/bin/python -m scripts.load_dws
```

Supply the environment using a secure runtime or an operator-approved configuration loader. Do not place plaintext secrets in shell arguments or logs. The loader creates `internal`, `external`, `governance` schemas, copies the 12 CSVs and verifies expected counts. It refuses to truncate unexpected nonempty tables. Matching row counts cause a skip and do not prove content identity; use a fresh demo namespace, not an existing business database.

The cloud bootstrap uses `scripts.initialize_dws.py` with a temporary administrator file to load data, grant a separate reader, verify access and delete that admin file. This bootstrap path assumes a fresh authorized cloud demo and is not the generic instruction for an existing production cluster.

## Publish and extend

Workflow publication currently writes to separate local `.runtime/outputs.db`; DWS remains read-only for query execution. No DWS write-back is claimed. Snowflake/Redshift are future adapters behind the same scoped MCP contracts and unified metadata catalog. Add explicit dialect, authentication, type and isolation tests for each platform.

Official context: [Huawei DWS MCP practice](https://support.huaweicloud.com/intl/zh-cn/bestpractice-dws/dws_05_0152.html). Follow the actual account/region documentation and endpoint inventory when configuring a new environment.
