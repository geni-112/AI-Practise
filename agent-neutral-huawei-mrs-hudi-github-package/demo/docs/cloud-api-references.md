# Cloud API References

- DLI is a serverless service compatible with Spark, Flink, and HetuEngine.
- Spark batch submission endpoint: `POST /v2.0/{project_id}/batches`.
- Spark batch state endpoint: `GET /v2.0/{project_id}/batches/{batch_id}/state`.
- DLI Spark jobs can use OBS package paths such as `obs://bucket/job.py`.
- CDM supports incremental migration patterns, but it is not a full Auto Loader equivalent.

Confirm exact endpoint hostnames and regional availability in the Huawei Cloud console before executing paid-resource scripts.
