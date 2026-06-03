# Notebook Execution Success Strategy

Databricks notebooks usually combine development, job submission, dependency packaging, and result inspection. The replacement here is JupyterHub on CCE with explicit success gates.

## Success gates

- Local notebook cells must execute with 100% success before cloud submission.
- Cloud-facing cells are dry-run by default and validate endpoint/payload construction.
- Actual DLI submission is performed by scripts, not hidden notebook state.
- Notebook users call DLI through API/SDK and access DWS through JDBC/SQLAlchemy.

## Why this improves reliability

- Scripts become the source of truth for production jobs.
- Notebooks remain exploratory and auditable.
- Notebook failure rate is measured by `notebooks/validate_notebook_execution.py`.
