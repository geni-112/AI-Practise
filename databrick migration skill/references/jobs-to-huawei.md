# Databricks Jobs to Huawei DataArts/MRS Reference

## Scope

Use this reference for Databricks Jobs JSON, notebooks, `%run` dependencies, task graphs, cluster configs, widgets, dbutils calls, libraries, schedules, and workflow orchestration.

## Target Pattern

- DataArts Factory owns orchestration, dependency graph, schedules, retries, and manual triggers.
- MRS Spark owns notebook/script computation.
- OBS stores source scripts, raw data, curated outputs, logs, and handoff files.
- DWS owns warehouse serving tables and BI-facing SQL.

## Job Mapping

| Databricks concept | Huawei demo replacement |
| --- | --- |
| Job | DataArts Factory job or script-trigger wrapper |
| Task | DataArts node, MRS Spark step, DWS SQL step, or shell/API step |
| Job cluster | MRS cluster or MRS Serverless/Spark resource profile |
| Notebook task | PySpark script submitted to MRS; optionally preserved as `.ipynb` for explanation |
| Wheel/JAR task | OBS-hosted dependency plus MRS Spark submit parameter |
| `dbutils.widgets` | DataArts parameters, environment variables, or CLI arguments |
| `%run` | Python module import or explicit script dependency |
| Job schedule | DataArts schedule or manual trigger for demo |
| Secrets | Environment variables, cloud secret service, or DataArts connection; never hard-code |

## Rewrite Steps

1. Extract a task graph from job JSON/YAML or notebooks.
2. Convert notebooks into executable `.py` scripts. Keep markdown narrative only in docs.
3. Replace `dbutils.fs` paths with OBS paths or local temp paths.
4. Replace widgets with `argparse` parameters.
5. Move cluster/library setup into MRS submit configuration.
6. Represent orchestration as `dataarts/job-plan.md` plus any API scripts the repository already uses.
7. Add a smoke path: generate sample input, run one MRS transform, load/query DWS, and verify expected counts.

## Common Code Rewrites

Databricks widget:

```python
date = dbutils.widgets.get("biz_date")
```

Portable rewrite:

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--biz-date", required=True)
args = parser.parse_args()
date = args.biz_date
```

Databricks path:

```python
input_path = "dbfs:/mnt/raw/orders"
```

OBS rewrite:

```python
input_path = f"obs://{bucket}/raw/orders"
```

Notebook call:

```python
dbutils.notebook.run("./00_PADRON_BASE/00_Padron_Base_", 0, params)
```

Portable module rewrite:

```python
from padron_base.main import run_padron_base

run_padron_base(**params)
```

Notebook metadata and exit handling:

```python
context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
dbutils.notebook.exit("OK")
```

Portable rewrite:

```python
import logging
import sys

metadata = {"job_name": args.job_name, "biz_date": args.biz_date}
logging.info("job metadata: %s", metadata)
sys.exit(0)
```

For failures, prefer raising a custom exception or `sys.exit(1)` so MRS/Yarn status reflects the failure.

## MRS PySpark Packaging Notes

- Convert notebook chains into Python packages and a launcher script.
- Replace Databricks-only dependency imports with local modules bundled through `--py-files` or packaged wheels.
- Keep helper functions such as source-table parsing and output-path updates in shared utility modules.
- For jobs needing custom Python packages, use `--archives hdfs:///tmp/python.zip#<alias>` and set `spark.pyspark.python`.
- See `references/mrs-pyspark-iceberg-runbook.md` for complete spark-sql and spark-submit command patterns.

## DataArts Job Plan Template

Create a concise `dataarts/job-plan.md` when no executable DataArts API integration exists:

```markdown
# DataArts Job Plan

Parameters:
- `biz_date`: `YYYY-MM-DD`
- `obs_bucket`: target OBS bucket

Nodes:
1. `generate_raw_orders`: optional local/upload step
2. `mrs_orders_bronze`: submit MRS Spark script `obs://.../orders_bronze.py`
3. `mrs_orders_curated`: submit MRS Spark script `obs://.../orders_curated.py`
4. `dws_load_orders`: run DWS SQL `dws/load_orders.sql`
5. `validate_orders`: run DWS validation SQL

Dependencies:
- 1 -> 2 -> 3 -> 4 -> 5
```

## Demo Safety

- Prefer manual trigger plus clear parameters for first demo runs.
- Include retry/idempotency notes for every node that writes to OBS, Iceberg, or DWS.
- For delete/recreate demo resources, isolate names with a demo prefix and date suffix.
- Keep credentials outside generated code.
