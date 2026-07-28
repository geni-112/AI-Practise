param(
    [switch]$ConfirmDestroy,

    [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmDestroy) {
    throw "Destroy requested without -ConfirmDestroy."
}

function Mirror-HuaweiEnv {
    if ($env:HUAWEICLOUD_ACCESS_KEY -and -not $env:HW_ACCESS_KEY) { $env:HW_ACCESS_KEY = $env:HUAWEICLOUD_ACCESS_KEY }
    if ($env:HUAWEICLOUD_SECRET_KEY -and -not $env:HW_SECRET_KEY) { $env:HW_SECRET_KEY = $env:HUAWEICLOUD_SECRET_KEY }
    if ($env:HUAWEICLOUD_REGION -and -not $env:HW_REGION_NAME) { $env:HW_REGION_NAME = $env:HUAWEICLOUD_REGION }
    if ($env:HUAWEICLOUD_PROJECT_ID -and -not $env:HW_PROJECT_ID) { $env:HW_PROJECT_ID = $env:HUAWEICLOUD_PROJECT_ID }
}

Mirror-HuaweiEnv

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$tfDir = Resolve-Path (Join-Path $scriptDir "..\terraform")

& (Join-Path $scriptDir "00_load_local_env.ps1") -Quiet
Mirror-HuaweiEnv

Push-Location $tfDir
try {
    if (-not (Test-Path "terraform.tfstate")) {
        throw "terraform.tfstate not found in $tfDir. Refusing to destroy unmanaged resources."
    }

    $stateText = Get-Content -Raw "terraform.tfstate"
    if ($stateText -notmatch "sat-agentic") {
        throw "Terraform state does not contain sat-agentic marker. Inspect manually."
    }

    terraform state list
    if ($AutoApprove) {
        terraform destroy -input=false -auto-approve
    }
    else {
        terraform destroy
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Terraform destroy failed with exit code $LASTEXITCODE."
    }

    $remaining = @(terraform state list)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to verify Terraform state after destroy."
    }
    if ($remaining.Count -gt 0) {
        throw "Destroy completed but Terraform state still contains $($remaining.Count) managed resources."
    }
}
finally {
    Pop-Location
}
