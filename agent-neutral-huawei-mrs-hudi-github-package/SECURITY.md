# Security Rules

This package intentionally contains no Huawei Cloud secrets.

## Do Not Store

Never write any of these into this package, logs, README files, notebooks, screenshots, or chat:

- Huawei Cloud account password.
- IAM password.
- AK/SK.
- Security token.
- Jupyter token.
- ECS admin/root password.
- Database password.

## Accepted Credential Sources

Use one of:

- environment variables populated by a secret manager or operator.
- temporary AK/SK/security token.
- IAM password environment variables for one-time token exchange.
- original Windows host DPAPI fallback with `-UseDpapiFallback`.

## Logging

Scripts may print:

- region id.
- project name.
- bucket name.
- MRS cluster id.
- MRS job id.
- job status.

Scripts must not print:

- secrets.
- request bodies containing passwords.
- Jupyter token query strings.

## Cleanup

Transient/debug MRS clusters are billable while running.

After any run:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Check-MrsCluster.ps1 -ClusterId <id>
```

If the cluster is still running and no job is needed:

```powershell
powershell -ExecutionPolicy Bypass -File .\automation\Remove-MrsCluster.ps1 -ClusterId <id>
```
