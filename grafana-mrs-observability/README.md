# Huawei Cloud MRS Observability

Grafana OSS monitoring and searchable logging for Huawei Cloud big-data
infrastructure, MRS, FusionInsight Manager, DataArts Factory, and OBS. The
dashboards use a white, Databricks-inspired information hierarchy while
remaining editable Grafana dashboards.

No cloud credentials, Manager passwords, deployment IPs, project IDs, cluster
IDs, private keys, downloaded logs, or deployment outputs are stored in this
repository.

## What is included

- Grafana OSS with provisioned Prometheus and Loki data sources.
- Prometheus, Loki, Caddy, and Node Exporter.
- Huawei API exporter for Cloud Eye, MRS clusters, nodes, jobs, and DataArts
  job metadata.
- DataArts collector that discovers OBS log roots, downloads `.job` and `.log`
  objects, masks secrets, and pushes searchable content to Loki.
- FusionInsight performance-dump exporter for Manager SFTP uploads.
- Dashboards for compute/services, MRS job traceability, and unified logs.
- Parameterized deployment to a new pay-per-use ECS or an approved existing ECS.

## Data paths

```text
Cloud Eye / MRS / DataArts APIs -> Huawei exporter -> Prometheus -> Grafana
DataArts -> OBS logs -> DataArts collector -> Loki -> Grafana
FusionInsight Manager -> SFTP dump -> dump exporter -> Prometheus -> Grafana
MRS tracking URL -> tokenized no-referrer launcher -> Manager/YARN/Spark UI
```

Grafana does not need manually created data sources. They are provisioned from
`grafana/provisioning/datasources/prometheus.yml` every time the stack starts.

## Prerequisites

- Windows PowerShell for the provided wrappers, or Python 3.11+ directly.
- A Huawei Cloud IAM user or agency with the least privileges needed for ECS,
  VPC, Cloud Eye, MRS, DataArts, and OBS reads. ECS/VPC write permissions are
  needed only when the deployment script creates or changes infrastructure.
- An existing VPC and subnet shared with or routable to MRS.
- A region-specific ECS image ID, availability zone, and valid flavor.
- Quota and pay-per-use cost confirmation before creating a new ECS.

Install the local deployment dependencies:

```powershell
.\scripts\Install-Dependencies.ps1
```

Save the Grafana and SFTP passwords in the current Windows user's DPAPI-encrypted
profile:

```powershell
.\scripts\Set-MonitorSecretsDialog.ps1
```

Load Huawei credentials from a trusted local profile, CLI, workload identity,
or secret service. At minimum the deployment process expects:

```powershell
$env:HUAWEICLOUD_ACCESS_KEY = '<runtime value>'
$env:HUAWEICLOUD_SECRET_KEY = '<runtime value>'
$env:HUAWEICLOUD_REGION = '<region id>'
$env:HUAWEICLOUD_PROJECT_ID = '<project id>'
```

Do not save those values in this checkout.

## Deploy a new monitoring ECS

Set the non-secret resource selection explicitly:

```powershell
$env:MONITOR_VPC_ID = '<vpc id>'
$env:MONITOR_SUBNET_ID = '<subnet id>'
$env:MONITOR_IMAGE_ID = '<regional ECS image id>'
$env:MONITOR_AVAILABILITY_ZONES = '<az-1,az-2>'
$env:MONITOR_FLAVORS = '<flavor-1,flavor-2>'
$env:MONITOR_VOLUME_TYPES = 'GPSSD,SSD,SAS'
$env:MONITOR_WEB_CIDR = '<approved client or proxy CIDR>'
$env:MRS_CLUSTER_ID = '<MRS cluster id>'
$env:MRS_CLUSTER_NAME = '<MRS cluster name>'
```

Creation is blocked unless the explicit paid-resource confirmation flag is
present:

```powershell
.\scripts\Deploy-Monitor.ps1 --confirm-create
```

The script checks quota, creates a restrictive security group, creates the ECS,
uploads the stack, writes remote environment files with mode `0600`, and starts
the containers.

## Deploy to an approved existing ECS

Set the exact host identity and MRS target:

```powershell
$env:MONITOR_SERVER_ID = '<ECS server id>'
$env:MONITOR_SERVER_NAME = '<exact ECS name>'
$env:MONITOR_PUBLIC_IP = '<approved EIP>'
$env:MONITOR_VPC_ID = '<expected VPC id>'
$env:MONITOR_PUBLIC_DOMAIN = '<optional DNS name>'
$env:MRS_CLUSTER_ID = '<MRS cluster id>'
$env:MRS_CLUSTER_NAME = '<MRS cluster name>'

.\scripts\Deploy-ExistingMonitor.ps1
```

The existing-host workflow validates the ECS ID, name, EIP, and VPC before
uploading. If SSH key authentication fails it stops without resetting the
password. `--allow-password-reset` is an explicit, disruptive recovery option
that resets the ECS password and reboots the host; use it only after approval.

## Automatic collection

- Prometheus scrapes internal targets every 30 seconds.
- Huawei API and DataArts collector metrics are scraped every 60 seconds.
- DataArts OBS logs synchronize every 10 minutes by default and retain object
  signatures so unchanged objects are not re-ingested.
- Set `DATAARTS_LOG_TIMEZONE_OFFSET_HOURS` to the fixed offset used in the
  regional DataArts OBS execution-directory names; the portable default is UTC.
- Sensitive-looking passwords, tokens, secrets, AKs, and SKs are masked before
  Prometheus or Loki emission.
- MRS job history is paginated and bounded by `MAX_MRS_JOBS`.
- Log links are tokenized. The launcher sends `Referrer-Policy: no-referrer` so
  FusionInsight/YARN does not reject Grafana-originated navigation.

## FusionInsight Manager one-time setup

The receiver directories and exporter are automated, but Manager must be
configured once to upload performance data over SFTP. Use a dedicated SFTP
account, allow TCP 22 only from verified Manager/MRS hosts, and upload beneath
`/srv/mrs-dump`. Component and audit log export also requires Manager-side
configuration and a user with the corresponding component permissions.

Verify and trust the expected Manager certificate. Do not disable TLS
verification and do not embed Manager credentials in URLs or configuration.

## Validation

After deployment, verify:

- all eight containers are running;
- every Prometheus target is up;
- Loki `/ready`, Grafana `/api/health`, and exporter `/health` succeed;
- the three provisioned dashboards load without query errors;
- MRS links use `/mrs-log/<token>` rather than raw Manager URLs;
- repository, Prometheus, and Loki contain no runtime credentials.

Generated `exports/`, local `logs/`, encrypted profiles, `.env` files, SSH keys,
and Python caches are ignored by Git.
