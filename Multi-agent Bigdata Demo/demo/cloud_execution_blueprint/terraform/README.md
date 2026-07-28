# Terraform Scaffold

This Terraform folder is deliberately resource-free. It models the intended Huawei Cloud bindings and outputs the OBS/DataArts/MRS/DWS handoff values, but it does not create paid resources.

Use it for review:

```powershell
terraform init
terraform plan -var-file terraform.tfvars.example
```

Expected behavior:

- No Huawei Cloud resources are created.
- No credentials are required by this scaffold.
- Outputs show the resource ids, OBS paths, and local release files that must be reviewed before a future real IaC module exists.

To turn this into real infrastructure later, add reviewed resource blocks in a separate change and keep destructive actions in explicit operator steps.
