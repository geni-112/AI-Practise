# Open-source Components

- Apache Hudi: table format replacing Delta merge/upsert/delete behavior.
- JupyterHub: open-source Notebook workbench on CCE.
- sparkmagic / Livy: optional path for Notebook-to-MRS Spark sessions.
- Superset: optional open-source BI on ECS or CCE, querying DWS.
- PySpark: DLI Spark job implementation language.

The main production data path uses DLI serverless Spark; MRS is optional and should only be provisioned when Livy or MRS-specific Hudi compatibility is required.
