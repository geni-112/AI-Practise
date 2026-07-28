# SAT Agentic Real Huawei Cloud Big Data Environment

This package is the real execution-layer path for the SAT Agentic POC.
It does not use DuckDB or any local database as the execution layer.

The intent is:

1. A business prompt creates a local agent run package under `generated/<agent_run_id>/`.
2. OBS stores the agent package under `release/<run_id>/agent_generated/`.
3. OBS stores raw, silver, gold, release, and audit data.
4. MRS Spark executes the reviewed cloud smoke PySpark job.
5. The web/API reads the MRS gold evidence from OBS for the minimal customer demo.
6. GaussDB(DWS) can serve reviewed gold data for SQL/BI when explicitly enabled.
7. DataArts Factory can orchestrate reviewed jobs when explicitly enabled.
8. ECS can host the demo web/API entry point.

## Current Resource Inventory

The current workspace has generated local blueprints, release artifacts, and pre-execution checks. It has not created real Huawei Cloud resources yet.

The target real resource list is:

| Resource | Terraform resource | Purpose | Default |
| --- | --- | --- | --- |
| VPC | `huaweicloud_vpc` | Private network boundary | created |
| Subnet | `huaweicloud_vpc_subnet` | Private data subnet | created |
| Security group | `huaweicloud_networking_secgroup` | Restrictive ingress/egress | created |
| OBS bucket | `huaweicloud_obs_bucket` | `raw/`, `silver/`, `gold/`, `release/`, `audit/` | created |
| MRS Spark | `huaweicloud_mapreduce_cluster` | Real PySpark execution | enabled |
| Website evidence API | FastAPI `/api/cloud/e2e-evidence`, `/api/cloud/gold-query` | Customer-visible MRS gold preview and filtered gold query from OBS evidence | enabled |
| DWS | `huaweicloud_dws_cluster` | SQL serving layer | optional with `-EnableDws` |
| DataArts Studio | `huaweicloud_dataarts_studio_instance` | Workflow orchestration | optional because it is prepaid |
| Web ECS + EIP | `huaweicloud_compute_instance`, `huaweicloud_vpc_eip` | Demo web/API host | optional |

## Secrets

Do not put secrets in `.tfvars`, README files, prompts, screenshots, or generated artifacts.
Do not use credentials from skill files, chat messages, browser cookies, saved passwords, logs, or screenshots.

Use environment variables:

```powershell
$env:HUAWEICLOUD_ACCESS_KEY = "<set outside chat>"
$env:HUAWEICLOUD_SECRET_KEY = "<set outside chat>"
$env:HUAWEICLOUD_REGION = "la-south-2"
$env:HUAWEICLOUD_PROJECT_ID = "<project id>"

$env:TF_VAR_mrs_manager_admin_password = "<set outside chat>"
$env:TF_VAR_node_key_pair_name = "<existing Huawei Cloud key pair>"
```

Set `TF_VAR_dws_admin_password` only when running with `-EnableDws`.

The scripts mirror `HUAWEICLOUD_*` to the Terraform provider's `HW_*` variables without printing secret values.
For a customer demo, set `TF_VAR_admin_cidr` to the office/VPN egress CIDR instead of leaving SSH/HTTP ingress open.
The Terraform/apply wrappers block `0.0.0.0/0` or `::/0` SSH/HTTP ingress unless `-AllowOpenIngressForDemo` is explicitly passed for a disposable demo.
Set `TF_VAR_demo_owner` and `TF_VAR_demo_expires_at` before creating paid resources. Terraform applies these as tags to the created resources, and the lifecycle guard blocks apply when cleanup ownership or expiration is missing.

## Commands

Show the planned resource list:

```powershell
.\cloud_real_bigdata\scripts\01_show_resource_inventory.ps1
```

Validate local tooling and credential presence:

```powershell
.\cloud_real_bigdata\scripts\02_validate_env.ps1
```

Check the ingress safety gate before any paid apply:

```powershell
.\cloud_real_bigdata\scripts\14_validate_apply_safety.ps1 `
  -EnableWebEcs `
  -Apply
```

For customer or commercial use, this must pass with a restricted `TF_VAR_admin_cidr`. For a short throwaway demo only, pass `-AllowOpenIngressForDemo`; the generated safety report records that override.

Check the lifecycle guard before any paid apply:

```powershell
.\cloud_real_bigdata\scripts\16_validate_lifecycle_guard.ps1 `
  -Apply
```

This requires `TF_VAR_demo_owner` and a future `TF_VAR_demo_expires_at`. The default maximum demo TTL is 168 hours; pass `-AllowLongLivedDemo` only when a longer-running customer environment has an explicit owner and cleanup commitment.

Export the no-create minimal resource, cost, and quota plan:

```powershell
.\cloud_real_bigdata\scripts\21_export_minimal_cost_quota_plan.ps1 `
  -EnableWebEcs
```

This report creates no resources and calls no cloud API. It lists the exact Terraform resources that would be created, the default MRS/ECS/DWS/DataArts sizing, which services are paid or prepaid, and which quota/price confirmations are still required before a customer or commercial apply.

After credentials and local safety gates are configured, run a read-only Huawei Cloud probe. It creates no resources, uploads no OBS objects, and submits no MRS jobs; it only performs read/list/head style checks:

```powershell
.\cloud_real_bigdata\scripts\17_run_readonly_cloud_probe.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>"
```

The probe report is written under:

```text
.cloud_real_bigdata_work/readonly_probe/readonly_probe_latest.json
.cloud_real_bigdata_work/readonly_probe/readonly_probe.md
```

Run the combined pre-apply readiness gate. It creates no resources, uploads no objects, and submits no MRS jobs. It refreshes the minimal resource/cost/quota plan, then aggregates credentials, ingress safety, lifecycle guard, Terraform validation, environment validation, and optionally the real-cloud Terraform plan:

```powershell
.\cloud_real_bigdata\scripts\15_pre_apply_readiness.ps1 `
  -EnableWebEcs `
  -RunReadonlyCloudProbe `
  -RunTerraformPreflight
```

Recommended operator path for the first real environment: use the bootstrap wrapper. It still creates no resources, uploads no objects, and submits no MRS jobs. With `-ConfigureCredentials`, it prompts locally with masked input, stores values in Windows user environment variables, detects the current public IP as a `/32` admin CIDR, sets short-lived demo owner/expiration guard values, then reruns the readiness gate:

```powershell
.\cloud_real_bigdata\scripts\18_bootstrap_operator_session.ps1 `
  -ConfigureCredentials `
  -PersistUserEnv `
  -SetGuardDefaults `
  -DetectAdminCidr `
  -EnableWebEcs `
  -RunTerraformPreflight
```

For a disposable workstation-local `.env.local` instead of Windows user environment variables, replace `-PersistUserEnv` with `-WriteLocalEnv`. This stores secrets on disk in an ignored file, so use it only on a trusted machine.

After readiness becomes `ready_for_apply`, run the customer demo wrapper to create the minimal resources, upload the prompt-derived package and sample data, submit the MRS Spark job, fetch gold evidence, deploy the optional ECS website, and run strict customer-demo audit. It requires both `-Apply` and `-ConfirmPaidResources`:

```powershell
.\cloud_real_bigdata\scripts\19_run_customer_demo_once.ps1 `
  -EnableWebEcs `
  -SshKeyPath "<path-to-private-key.pem>" `
  -Apply `
  -ConfirmPaidResources
```

Without `-Apply`, the same script runs only bootstrap/readiness and writes a status report; it does not create resources, upload OBS objects, or submit MRS jobs.

When the strict audit passes, the customer demo wrapper exports a handoff package. You can rerun the handoff exporter explicitly without creating resources:

```powershell
.\cloud_real_bigdata\scripts\20_export_customer_handoff.ps1 `
  -BaseUrl "http://<customer-demo-url>" `
  -RequireCloudSuccess `
  -PublishToEvidence
```

The handoff package includes customer URLs, gold preview, privacy checks, cleanup command, and commercial hardening items. Published files are served as `/cloud-evidence/customer_handoff.html`, `/cloud-evidence/customer_handoff.md`, and `/cloud-evidence/customer_handoff.json`.

Validate the customer-demo and commercial-readiness boundary without creating resources:

```powershell
.\cloud_real_bigdata\scripts\22_validate_customer_commercial_readiness.ps1 `
  -BaseUrl "http://<customer-demo-url>"
```

This separates three states: not ready for customer demo, ready for controlled customer demo, and ready for a commercial pilot review. Commercial readiness requires real cloud evidence first, then explicit confirmations for domain/HTTPS, IAM least privilege, monitoring, Terraform state control, backup/retention, incident ownership, and SLA approval. It is intentionally stricter than the minimal POC apply.

The readiness report is written under:

```text
.cloud_real_bigdata_work/pre_apply_readiness/pre_apply_readiness_latest.json
.cloud_real_bigdata_work/pre_apply_readiness/pre_apply_readiness.md
```

Generate a non-secret credential status report:

```powershell
.\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1
```

Safest local setup is to store secrets in Windows user environment variables from the terminal prompt. The script reads secret values with masked input and prints only status:

```powershell
.\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1 -PersistUserEnv
```

If you need a repo-local file for a disposable POC, write an ignored `.env.local`. This stores secrets on disk, so use it only on a trusted workstation:

```powershell
.\cloud_real_bigdata\scripts\12_configure_cloud_credentials.ps1 -WriteLocalEnv
```

You can also keep real values in an ignored local file named `.env.local`. The scripts load only allowlisted Huawei variables and print only whether each value is present:

```powershell
Copy-Item .env.example .env.local
# edit .env.local locally; do not paste secrets into chat or commit the file
.\cloud_real_bigdata\scripts\02_validate_env.ps1
```

Generate the exact minimal one-shot command and a unique OBS bucket name without calling cloud APIs:

```powershell
.\cloud_real_bigdata\scripts\08_prepare_minimal_run.ps1
```

Run a real-cloud preflight plan before any paid apply. This creates a local agent package and runs Terraform init/plan only; it does not apply, upload OBS objects, or submit MRS jobs:

```powershell
.\cloud_real_bigdata\scripts\10_real_cloud_preflight_plan.ps1 `
  -EnableWebEcs
```

If `TF_VAR_admin_cidr` is not restricted, preflight will stop before Terraform plan. Set it first, for example:

```powershell
$env:TF_VAR_admin_cidr = "<office-or-vpn-cidr>/32"
```

Run the final acceptance audit before creating resources. In this mode, missing cloud evidence is reported as a warning. The expected state is `pending_cloud_preflight` until credentials are configured and `10_real_cloud_preflight_plan.ps1` passes; after that it becomes `ready_for_real_apply`:

```powershell
.\cloud_real_bigdata\scripts\09_final_acceptance_audit.ps1 `
  -BaseUrl "http://127.0.0.1:8788"
```

Export a non-secret operator handoff for whoever will run the cloud deployment:

```powershell
.\cloud_real_bigdata\scripts\11_export_operator_handoff.ps1 `
  -BaseUrl "http://127.0.0.1:8788"
```

The handoff is written under `.cloud_real_bigdata_work/operator_handoff/` and includes current status, missing variables, commands, trace paths, and troubleshooting order.

Create or preview real resources:

```powershell
.\cloud_real_bigdata\scripts\03_apply.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -NodeKeyPairName "<existing-key-pair>" `
  -Apply
```

Enable DWS only when SQL serving is required:

```powershell
.\cloud_real_bigdata\scripts\03_apply.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -NodeKeyPairName "<existing-key-pair>" `
  -EnableDws `
  -Apply
```

Enable DataArts only after accepting prepaid monthly billing:

```powershell
.\cloud_real_bigdata\scripts\03_apply.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -NodeKeyPairName "<existing-key-pair>" `
  -EnableDataArts `
  -Apply
```

Upload a tiny SAT sample and the PySpark job to OBS:

```powershell
python .\cloud_real_bigdata\scripts\generate_sample_and_upload.py `
  --bucket "sat-agentic-<globally-unique-suffix>" `
  --run-id "front-demo-real-001" `
  --agent-run-id "<generated-agent-run-id>" `
  --generated-run-dir ".\generated\<generated-agent-run-id>"
```

Submit the MRS Spark smoke job after the upload:

```powershell
.\cloud_real_bigdata\scripts\03_apply.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -NodeKeyPairName "<existing-key-pair>" `
  -SubmitSmokeJob `
  -RunId "front-demo-real-001" `
  -Apply
```

Run the whole real E2E sequence:

```powershell
.\cloud_real_bigdata\scripts\05_run_real_e2e.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -PromptFile .\cloud_real_bigdata\examples\sat_prompt.txt `
  -NodeKeyPairName "<existing-key-pair>" `
  -Apply
```

Use `-UseMaaS` when GLM-5.2 MaaS environment variables are configured and you want the business-contract draft to use MaaS. The same command still falls back safely inside the local agent workflow if MaaS is not selected.

For a customer-facing website on the smallest ECS/EIP path, add `-EnableWebEcs` and pass `-SshKeyPath`. The E2E script will deploy the frontend and run the customer-demo verification automatically.
Use `-SkipWebDeploy` only when you want Terraform to create the ECS/EIP but deploy the website later.

For SQL serving beyond the website evidence view, add `-EnableDws`.

One command for the smallest customer demo path with ECS website deployment:

```powershell
.\cloud_real_bigdata\scripts\05_run_real_e2e.ps1 `
  -ObsBucketName "sat-agentic-<globally-unique-suffix>" `
  -PromptFile .\cloud_real_bigdata\examples\sat_prompt.txt `
  -NodeKeyPairName "<existing-key-pair>" `
  -EnableWebEcs `
  -SshKeyPath "C:\path\to\private_key.pem" `
  -Apply
```

This creates the minimum real big-data execution layer, runs MRS, publishes evidence, deploys the website to ECS, and verifies the customer URL.
Add `-DestroyOnFailure` only when you want the script to call Terraform destroy automatically if a later E2E step fails after real apply has started. The default is safer for troubleshooting because it preserves the failed state for inspection.

This does the following:

1. Converts the business prompt into an agent run package under `generated/<agent_run_id>/`.
2. Validates local tools, dependencies, and credential presence.
3. Creates OBS, VPC/subnet/security group, MRS, and optional DWS/DataArts/ECS.
4. Uploads `taxpayer_registry.csv`, `sat_taxpayer_etl.py`, the agent package, and the release manifest to OBS.
5. Submits the MRS Spark smoke job.
6. Waits for the MRS job to finish.
7. Reads `obs://<bucket>/gold/sat/<run_id>/taxpayer_gold_csv/`.
8. Writes local, frontend-readable, and OBS audit evidence as `e2e_result.json`.
9. Exports a customer-facing report as `customer_demo_report.html`, `customer_demo_report.md`, and `customer_demo_summary.json`.

Every E2E attempt also writes a non-secret operator trace:

```text
.cloud_real_bigdata_work/e2e_traces/latest_e2e_trace.json
.cloud_real_bigdata_work/<run_id>/operator_run_trace.json
```

The trace records step names, run ids, OBS paths, report paths, and failure messages. It must not contain AK/SK, passwords, private keys, cookies, or browser session material.

The frontend reads the latest published evidence from:

```text
cloud_real_bigdata/public_evidence/latest_e2e_result.json
```

and exposes it through:

```text
/api/cloud/e2e-evidence
/api/cloud/gold-query
```

`/api/cloud/gold-query` supports lightweight filters such as `region`, `year`, `regime`, and `resico`. It reads only the published MRS evidence JSON; it does not use DuckDB and does not call live cloud APIs.

The customer-facing report is served from:

```text
/cloud-evidence/customer_demo_report.html
```

Deploy the web front end to the optional ECS:

```powershell
.\cloud_real_bigdata\scripts\06_deploy_frontend_to_ecs.ps1 `
  -WebPublicIp "<terraform-output-web-public-ip>" `
  -SshKeyPath "C:\path\to\private_key.pem"
```

This installs the FastAPI app as a `systemd` service behind Nginx on port 80.
For production, use an ECS agency or cloud secret service for cloud credentials, not files on the server.
The deploy package excludes `.git`, virtualenvs, Terraform state, tfplans, logs, generated local runs, and private key file extensions.
Each successful deployment writes a non-secret manifest under:

```text
.cloud_real_bigdata_work/web_deploy/web_deploy_manifest.json
```

Configure Huawei MaaS GLM-5.2 on the deployed ECS only after the web service is healthy:

```powershell
$env:HUAWEI_MAAS_API_KEY = "<secure-api-key>"
$env:HUAWEI_MAAS_BASE_URL = "https://api-ap-southeast-1.modelarts-maas.com/openai/v1"
$env:HUAWEI_MAAS_MODEL = "glm-5.2"

.\cloud_real_bigdata\scripts\23_configure_maas_on_ecs.ps1 `
  -WebPublicIp "<terraform-output-web-public-ip>" `
  -SshKeyPath "C:\path\to\private_key.pem"
```

The script reads only the three `HUAWEI_MAAS_*` process variables. It uploads a short-lived environment file, installs it as `/etc/sat-agent-vibe/maas.env` with mode `600`, creates a `systemd` drop-in, restarts the service, and calls `/api/maas/test`. Secret values are not written to the repository, deployment manifest, or report. The local temporary file and remote `/tmp` copy are removed after installation.

The ECS deployment already includes the three prompt templates from `app/prompt_templates.py` and the synthetic SAT validation datasets from `app/synthetic_data.py`. A MaaS-assisted run combines the selected template, its variables, and a compact field/security context before generating the business contract. Published MRS Gold evidence remains available separately through `/api/cloud/gold-query`; raw taxpayer identifiers are not sent to MaaS.

Diagnose the optional ECS website after deployment:

```powershell
.\cloud_real_bigdata\scripts\13_diagnose_web_ecs.ps1 `
  -WebPublicIp "<terraform-output-web-public-ip>" `
  -SshKeyPath "C:\path\to\private_key.pem"
```

The diagnostic checks SSH reachability, the remote app directory, `sat-agent-vibe` systemd status, Nginx status/config, local FastAPI health, public `/api/health`, public `/api/cloud/e2e-evidence`, public `/api/cloud/gold-query`, and customer report summary availability. It writes:

```text
.cloud_real_bigdata_work/web_diagnostics/web_diagnostics_latest.json
.cloud_real_bigdata_work/web_diagnostics/web_diagnostics.md
```

Verify the customer demo website:

```powershell
.\cloud_real_bigdata\scripts\07_verify_customer_demo.ps1 `
  -BaseUrl "http://<terraform-output-web-public-ip>"
```

The verifier checks health, real cloud evidence, queryable non-empty gold data, masked RFC, no DuckDB usage, and the customer demo report summary.

After the real E2E run and website deployment, run the final acceptance audit in strict mode. This must pass before treating the environment as customer-demo ready:

```powershell
.\cloud_real_bigdata\scripts\09_final_acceptance_audit.ps1 `
  -BaseUrl "http://<terraform-output-web-public-ip>" `
  -RequireCloudSuccess
```

Before a real cloud run exists, use this only to verify site reachability:

```powershell
.\cloud_real_bigdata\scripts\07_verify_customer_demo.ps1 `
  -BaseUrl "http://127.0.0.1:8788" `
  -AllowNoCloudEvidence
```

Destroy only resources tracked by this Terraform state:

```powershell
.\cloud_real_bigdata\scripts\04_destroy.ps1 -ConfirmDestroy
```

## Data Path

```text
Business prompt
  -> Agent artifacts
  -> OBS release/<run_id>/agent_generated/
  -> OBS raw/sat/<run_id>/taxpayer_registry.csv
  -> MRS Spark sat_taxpayer_etl.py
  -> OBS gold/sat/<run_id>/taxpayer_gold_csv/
  -> Web/API evidence view
  -> optional DWS serving SQL / optional DataArts job
```

## Important Billing Notes

MRS is the minimum paid big-data compute resource for this real E2E path. DWS is disabled by default and is created only with `-EnableDws`. DataArts Studio instance creation is prepaid only in the Terraform provider, so it is optional and disabled unless `-EnableDataArts` is passed.
