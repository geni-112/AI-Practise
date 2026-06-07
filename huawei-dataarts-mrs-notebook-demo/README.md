# Huawei DataArts + MRS Notebook Demo

This folder contains a VS Code Notebook based development entrypoint for a Huawei Cloud big data workflow.

## What It Demonstrates

- Develop a PySpark job in VS Code Notebook.
- Commit the notebook and exported script to Git.
- Import the script into DataArts Factory.
- Submit the job to MRS Spark.
- Read raw data from OBS and write clean, reject, and curated outputs back to OBS.
- Publish curated metrics to Hive and emit a monitor event dataset.

## Folder Layout

```text
notebooks/dataarts_mrs_bigdata_etl.ipynb
spark/jobs/bigdata_lakehouse_etl.py
dataarts/bigdata_lakehouse_dag.json
config/demo.env.example
```

## VS Code Notebook

Open the notebook with VS Code and select this kernel:

```text
Python 3.12 - Huawei DataArts Demo
```

The first notebook cell is a local smoke test. The PySpark cells are intended for MRS Spark or a Spark-enabled local environment.

## DataArts Runtime Parameters

```text
demo.raw_path=obs://<bucket>/raw/orders/${biz_date}/
demo.clean_path=obs://<bucket>/clean/orders/${biz_date}/
demo.reject_path=obs://<bucket>/clean/rejects/orders/${biz_date}/
demo.curated_path=obs://<bucket>/curated/daily_channel_metrics/${biz_date}/
demo.event_path=obs://<bucket>/curated/daily_channel_metrics/${biz_date}/_events
demo.input_format=csv
demo.biz_date=${biz_date}
demo.shuffle_partitions=200
```

## MRS Submit Example

```bash
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --conf demo.raw_path=obs://<bucket>/raw/orders/${biz_date}/ \
  --conf demo.clean_path=obs://<bucket>/clean/orders/${biz_date}/ \
  --conf demo.reject_path=obs://<bucket>/clean/rejects/orders/${biz_date}/ \
  --conf demo.curated_path=obs://<bucket>/curated/daily_channel_metrics/${biz_date}/ \
  --conf demo.event_path=obs://<bucket>/curated/daily_channel_metrics/${biz_date}/_events \
  --conf demo.input_format=csv \
  --conf demo.biz_date=${biz_date} \
  --conf demo.shuffle_partitions=200 \
  spark/jobs/bigdata_lakehouse_etl.py
```

## Security Notes

- Do not commit AK/SK, project IDs, database passwords, or private keys.
- Use IAM agency, environment variables, or a secret manager.
- Keep raw data immutable and expose only curated data to BI/API consumers.

