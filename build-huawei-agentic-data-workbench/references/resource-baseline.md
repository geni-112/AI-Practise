# Resource Baseline

Use this reference to plan resources. Verify current Huawei Cloud availability, quotas, prices, API versions, and supported images before deployment; they change over time.

## Minimum Local Environment

| Component | Purpose | Minimum guidance |
|---|---|---|
| FastAPI | Web/API entry point | 1 process for development |
| LangGraph | Explicit agent workflow | In-process graph for POC |
| Local artifact directory | Diffable run outputs | One directory per run ID |
| Synthetic dataset | Contract and transform validation | Small masked CSV/JSON/Parquet samples |
| Huawei MaaS adapter | Optional model generation | OpenAI-compatible client with timeout/retry |
| code-server | Optional engineering escape hatch | Do not expose as the customer entry point |

Recommended local layout:

```text
app/
  api/
  graph/
  agents/
  services/
  static/
templates/
synthetic/
generated/<run-id>/
tests/
```

The local environment must be useful without MaaS. When MaaS is disabled or unavailable, generate a deterministic contract and artifacts suitable for workflow/UI testing, then record the fallback mode explicitly.

## Huawei Cloud POC Baseline

Use the following as a reference shape, not an instruction to create resources automatically.

| Service | Role | POC guidance |
|---|---|---|
| OBS | Landing, raw, refined, Gold, releases, evidence | One bucket with strict prefixes or separate buckets by policy |
| VPC/Subnet | Network isolation | Private subnets for data services; controlled ingress for web tier |
| Security groups | Network policy | Restrict administrative ingress to approved CIDRs |
| ECS | FastAPI workbench host | Small Linux instance; scale only after profiling |
| EIP / ingress | Controlled UI/API access | Use only when required; prefer managed enterprise ingress later |
| MRS | Spark execution | Start from a supported small non-production cluster; verify flavor availability |
| DataArts Studio | Workflow import, scheduling, operations | Add when orchestration APIs and permissions are ready |
| DWS | Serving warehouse | Optional until concurrent BI or warehouse semantics are needed |
| MaaS | Contract/code drafting | Configurable model and endpoint, no hard-coded model assumptions |
| IAM / DEW | Identity and secrets | Separate deploy, probe, release, and execute permissions |
| Cloud Eye / LTS | Metrics and logs | Capture API health, graph runs, job states, and failures |

A previously validated MRS reference used an MRS 3.5 LTS class cluster with Hadoop, Hive, Spark, and JobGateway, two master nodes, and three core nodes. Treat this only as compatibility evidence. Recalculate node count, flavor, disk, availability, and cost for each region and workload.

## Logical OBS Layout

```text
obs://<bucket>/landing/<source>/<ingest-date>/
obs://<bucket>/raw/<domain>/<event-date>/
obs://<bucket>/silver/<domain>/<table>/
obs://<bucket>/gold/<product>/<version>/
obs://<bucket>/releases/<run-id>/
obs://<bucket>/evidence/<run-id>/
```

Apply these rules:

- Make `landing` and `raw` append-oriented.
- Keep refined and Gold schemas versioned.
- Store approved release packages separately from mutable draft artifacts.
- Apply lifecycle expiration to temporary uploads and transient evidence copies.
- Encrypt at rest and restrict prefix access by execution role.

## Minimum Demo Versus Commercial Pilot

### Minimum Demo

- FastAPI and LangGraph on a local machine or one ECS instance.
- Optional MaaS; deterministic fallback enabled.
- Synthetic or sanitized input in local storage/OBS.
- Existing MRS cluster or an explicitly approved temporary POC cluster.
- DataArts package generation without mandatory live import.
- DWS omitted unless the demonstration requires warehouse queries.
- Manual reviewer approval and simple JSON evidence.

### Commercial Pilot

- Enterprise ingress and SSO/federated identity.
- Separate application, artifact, probe, and execution roles.
- Managed secrets and automatic rotation.
- Private service connectivity where available.
- DataArts scheduling with retry, alerting, and ownership.
- MRS autoscaling or workload-aware capacity planning.
- DWS for supported serving patterns.
- Central logs, metrics, cost tags, budgets, and lifecycle policies.
- Release retention and auditable reviewer identity.

## Configuration Contract

Use names like these, but never commit values:

```text
HUAWEI_MAAS_BASE_URL
HUAWEI_MAAS_API_KEY
HUAWEI_MAAS_MODEL
HUAWEI_CLOUD_REGION
HUAWEI_CLOUD_PROJECT_ID
HUAWEI_CLOUD_ACCESS_KEY
HUAWEI_CLOUD_SECRET_KEY
OBS_BUCKET
OBS_RELEASE_PREFIX
MRS_CLUSTER_ID
DATAARTS_WORKSPACE_ID
DWS_ENDPOINT
```

Prefer workload identity, instance agency, CLI profiles, or DEW over long-lived environment keys. Environment variables are acceptable for a controlled POC when the service account and filesystem permissions are restricted.

## Resource Creation Gate

Before creating any resource:

1. Produce a resource manifest with service, region, shape, count, disk, network, tags, and estimated lifetime.
2. Identify existing resources that can be reused safely.
3. Run read-only quota and availability checks.
4. Estimate cost and define the destroy/expiration plan.
5. Obtain explicit user approval for chargeable creation.
6. Persist resource IDs outside the reusable skill and source code.

Do not interpret a cloud API probe as approval to create resources. A probe confirms connectivity, permissions, and object existence only.
