# Huawei Cloud deployment guide

The package contains reusable source and Mexico City2 deployment scripts, with **no existing deployment state or account material**. Running the local demo is independent of these steps. Deploy only when the current user has authorized the requested billable resources; honor authorization already given in that session and do not create duplicate resources.

## Read-only preflight

Configure the deployment operator's credentials securely: `HUAWEICLOUD_SDK_AK`, `HUAWEICLOUD_SDK_SK`, `HUAWEICLOUD_PROJECT_ID`, optional `HUAWEICLOUD_SDK_SECURITY_TOKEN`, and `HUAWEICLOUD_REGION=la-north-2`.

```bash
.venv/bin/python scripts/huawei_resources.py
```

This command queries sellable DWS capacity and saves a local plan. It does not create cloud resources; without credentials it exits blocked. The prepared scripts target Mexico City2 (`la-north-2`) only and reject automatic region substitution. They choose the smallest available stable CPU/RAM/storage candidate for a dedicated three-node cluster, **not a verified cheapest total cost quotation**. Check actual availability, quota and prices in the intended account before application.

## Authorized DWS creation

After the operator has reviewed the plan within the user's authorized scope:

```bash
.venv/bin/python scripts/huawei_resources.py --apply
```

Creates a dedicated VPC `10.63.0.0/16`, subnet `10.63.1.0/24`, security group and DWS, with no DWS public IP. The subnet uses the region's private DNS `100.125.1.250`. It refuses untracked same-name resources and records generated resource identities privately under `.runtime/huawei-state.json`. Generated passwords are separate owner-readable files. Preserve this state for reconciliation and cleanup; do not copy it into a public skill or another account.

Poll the actual cluster API until available. A successful create response is not a healthy database or complete application deployment. Export its current details to the private `.runtime/huawei-dws-details.json` expected by the host script, using the operator's SDK/console. Never fabricate resource IDs to bypass missing state.

## Application host reference

`scripts/huawei_host.py` and `infra/cloud_bootstrap.py` are a prepared single-host demo deployment path. They are **not a generic one-command cloud installer**. Before using them in a new account, obtain and validate these local prerequisites:

- `.runtime/huawei-state.json` from this account's successful DWS provisioning, with cluster/VPC/subnet IDs.
- `.runtime/huawei-dws-details.json` containing the current cluster detail, private `endpoints[].connect_info` or `private_ip`.
- `.runtime/huawei-host-inventory.json` with a `flavors` array of current ECS flavor details. The sample selects `s6.large.4` and checks `os_extra_specs.condoperationaz` for `la-north-2a(normal)`.
- `.runtime/huawei-images.json`, a current public image array containing the selected Ubuntu 24.04 server image `id`/`name`. Resolve it from this region, not another account's example.
- `.runtime/dws-certs/ca-1.pem` containing the official trusted DWS v2 CA, obtained from Huawei's documented certificate bundle. Verify trust and chain; do not generate a self-signed substitute.
- Valid private model configuration, freshly generated data, frontend production build and any requested source/data downloads.

The host scripts assume Ubuntu, systemd, Docker installation, private DWS routing and access to dependency registries. Confirm live flavor/image names and quotas; adjust selection code when the region's inventory differs. They prepare one 2-vCPU/8-GB app host, 40-GB system disk and 5-Mbps traffic-billed EIP, plus a private OBS artifact bucket. Availability and price must be checked again in each account.

The operational sequence is `huawei_host.py network` → `upload` → `create` → `status`. These actions are **mutating or paid**, except status. Read the code and reconcile state before execution. `upload` creates an encrypted release with short-lived private OBS delivery URLs. The application receives model and reader credentials, not the cloud operator's resource-management AK/SK. Keep generated control files, one-time invitation and signing material private. `finalize` closes the temporary bootstrap update channel after successful verification.

Build before uploading:

```bash
python scripts/package_downloads.py
npm ci
npm run build
```

The packaged host uploader includes `src/messages.json`, needed by backend localization as well as the built frontend. The source-only public skill never includes the encrypted deployment release or its configuration.

## Verify and operate

Database access remains private. Only the app HTTPS endpoint is public; internal APIs, OpenMetadata, Temporal, search and PostgreSQL stay bound to localhost. The sample login gate uses a separate owner invitation/password and Secure/HttpOnly cookies. Role switching inside the demo remains a demonstration and must not be sold as production IAM.

`scripts/cloud_verify.py` runs on the dedicated app host. It exercises actual model planning → openJiuwen → scoped MCP → DWS, compares results with generated CSVs, checks region/domain/export/tenant restrictions, submits a Temporal task and verifies OpenMetadata lineage. It consumes model calls and creates synthetic task outputs. Do not run it against an unrelated existing service. Inspect actual verification reports before reporting readiness; health configuration flags alone do not prove model or warehouse execution.

`infra/update_ui.py` assumes `/opt/nexo-app` and the sample systemd setup. Review paths and release contents before using it elsewhere. There is no automated generic resource destroyer. Locate all billable resources from the private state and account inventory; cleanup requires the current user's scope and must preserve resources outside it. Stopping the chat or closing the demo does not stop cloud billing.
