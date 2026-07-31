# Grafana, MRS, DataArts, and FusionInsight Observability

Use this reference to build or extend a Grafana OSS monitoring plane for Huawei Cloud big-data resources. Keep resource identifiers, host addresses, credentials, certificates, and deployment evidence outside the skill.

## Contents

- [Source hierarchy](#source-hierarchy)
- [Reference deployment](#reference-deployment)
- [Job traceability contract](#job-traceability-contract)
- [DataArts OBS log ingestion](#dataarts-obs-log-ingestion)
- [FusionInsight Manager ingestion](#fusioninsight-manager-ingestion)
- [Databricks-style white dashboard](#databricks-style-white-dashboard)
- [Validation gates](#validation-gates)

## Source hierarchy

Use the narrowest authoritative source for each signal:

| Signal | Preferred source | Notes |
| --- | --- | --- |
| ECS CPU, disk, network, service metrics | Cloud Eye metric discovery and batch query | Discover available namespaces and dimensions before writing PromQL. |
| ECS memory | Cloud Eye Agent metrics such as `AGT.ECS`, or Node Exporter | Basic `SYS.ECS` metrics may not include memory. Show `unavailable` when no agent-backed series exists. |
| MRS cluster and node state | MRS cluster and node APIs | Preserve cluster ID, node group, role, IP, and state as dimensions where cardinality is bounded. |
| MRS job history | Paginated MRS job APIs | Do not stop at the first page; cap the retained history explicitly. |
| MRS/YARN/Spark execution logs | Job tracking URL, YARN ResourceManager, or Spark History Server | A regional `log-detail` API may be unpublished or return 404. Treat the tracking URL as the durable fallback. |
| FusionInsight component metrics | Manager performance-data SFTP dump | Parse metric ID, service, host, unit, cluster, timestamp, and value into Prometheus samples. |
| FusionInsight audit/component logs | Manager download or SFTP workflows | Require verified Manager TLS and Manager-side configuration. |
| DataArts job definitions and instances | DataArts APIs | Capture name, owner, parameters, schedule, instance ID, status, and timestamps when returned. |
| DataArts node log content | OBS log roots returned by DataArts | Read `.job` and `.log` objects, mask secrets, then push to Loki. |
| Monitoring ECS health | Node Exporter and container health endpoints | Keep this separate from MRS worker metrics. |

Check current regional service availability and API schemas before implementation. Do not assume an endpoint available in one Huawei Cloud region exists in another.

## Reference deployment

Deploy the monitoring plane on an ECS in the MRS VPC:

1. Run Grafana OSS, Prometheus, Loki, a Huawei API exporter, a DataArts OBS-log collector, a FusionInsight dump exporter, Node Exporter, and an HTTPS reverse proxy.
2. Keep MRS, DataArts, OBS, DWS, and Manager traffic private. Expose Grafana only when requested.
3. Provision Prometheus and Loki data sources and version-controlled Grafana dashboards.
4. Use persistent volumes for Prometheus, Loki, Grafana, and the OBS object-signature state.
5. Pin container versions and record retention, scrape interval, job-history limit, and log-backfill limits as configuration.

Prefer instance metadata or short-lived IAM credentials on ECS. If static AK/SK must be used, inject them at runtime from a protected profile or secret service and restrict environment files to the service account.

## Job traceability contract

Represent one execution per row and retain:

- platform, cluster ID, job ID, job name, job type, execution state, result, start time, end time, and duration;
- submitting user or returned executor, queue, runtime parameters, application IDs, and tracking/log URL;
- ApplicationMaster or driver host, executor hosts, and the source used to establish that linkage;
- historical execution or instance ID and the original resource link.

Use these semantics:

- `assigned_node` means a verified YARN ApplicationMaster or Spark driver host.
- `executor_nodes` is separate because a distributed job can use many nodes.
- Never infer an assigned node from the MRS cluster node list. If the public job API lacks the host, export `unavailable_pending_yarn_or_fusioninsight`.
- Prefer the API's executed-by field. If only the job owner or creator is available, label it as owner and do not present it as a verified executor.
- Link success and failure rows to their tracking/log target whenever Huawei returns one.
- Preserve unavailable, unmatched, and unknown states in the dashboard instead of dropping the row.

Enrich node linkage from YARN ResourceManager, Spark History, or trusted FusionInsight data only after matching stable application and job identifiers.

## DataArts OBS log ingestion

Implement historical ingestion as an idempotent collector:

1. Enumerate DataArts job definitions and configured OBS log roots.
2. Page through job instances for the selected history window.
3. List only relevant `.job` and `.log` objects under those roots.
4. Bound object count, object size, history days, request rate, and download concurrency.
5. Store object key, ETag or signature, size, and last-modified state so unchanged objects are skipped.
6. Decode text defensively, normalize timestamps to UTC using a configurable source offset, and mask secrets before any log or metric emission.
7. Match a log object to the nearest instance of the same job inside a configurable time window. Record this as heuristic matching and retain unmatched objects.
8. Push content to Loki and expose collector health, files, bytes, lines, skipped objects, failures, and last successful synchronization to Prometheus.
9. Version the ingestion logic or labels during a corrected backfill so dashboards can select the canonical generation.

Keep Loki labels low-cardinality. Good filter labels include source, ingestion version, job, status, and node when bounded. Keep paths, parameters, long IDs, and raw content in log fields or structured metadata when possible.

Apply masking to key/value and free-text forms of:

- passwords and passphrases;
- tokens, bearer values, cookies, and authorization headers;
- secret keys, access keys, connection strings, and embedded credentials;
- runtime parameters whose key suggests sensitive content.

Test masking with synthetic sentinels and with exact runtime credentials without printing those credentials in test output.

## FusionInsight Manager ingestion

For performance-data upload:

1. Create a dedicated non-login or constrained SFTP receiver account on the monitoring ECS.
2. Create separate directories for performance data, audit logs, and component logs with restrictive ownership and mode.
3. Permit TCP 22 only from the MRS subnet or verified Manager hosts. Do not broaden public SSH access.
4. Configure Manager to upload at an appropriate supported interval.
5. Parse Manager dump files incrementally and expose the original metric ID, display name, service, host, unit, cluster, and timestamp.

Do not automate Manager login through an untrusted self-signed certificate. Verify the endpoint and certificate fingerprint, establish trust, then authenticate through a secret channel. Never commit Manager credentials or downloaded audit logs.

## Databricks-style white dashboard

Use Grafana's light theme at server, organization, and user preference levels. Build a white, low-chrome information hierarchy:

1. overview and freshness;
2. compute CPU, memory, network, and disk;
3. FusionInsight service and component metrics;
4. MRS and DataArts job executions;
5. job parameters, user or owner, history, application IDs, assigned-node evidence, and log links;
6. searchable raw logs and collector health.

Use table links for logs and tracking pages, status colors for success/running/failure/unknown, consistent time ranges, and dashboard variables for cluster, service, job, status, and node. Clearly annotate missing series and heuristic correlations.

## Validation gates

Before handoff, verify:

- every container is running or healthy;
- Loki readiness, Grafana health, exporter health, and HTTPS access;
- all expected Prometheus targets are up;
- Grafana data sources resolve and provisioned dashboards load without query errors;
- CPU, memory, disk, network, component, job, and log panels either contain data or show an accurate unavailable reason;
- MRS pagination reaches the expected history count;
- DataArts object catalog totals reconcile with OBS listing limits and the canonical ingestion generation;
- job links open the correct execution target and node fields state their evidence source;
- Manager SFTP directories and security-group rules are restricted;
- repository and active Prometheus/Loki data contain no runtime credentials or synthetic secret sentinels.

Report any remaining Manager-side setup, certificate trust, regional endpoint gap, agent installation, or credential requirement explicitly.
