$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item -Force (Join-Path $root "jobs\dli\bronze_hudi_job.py") (Join-Path $dist "bronze_hudi_job.py")
Copy-Item -Force (Join-Path $root "jobs\dli\silver_hudi_job.py") (Join-Path $dist "silver_hudi_job.py")
Copy-Item -Force (Join-Path $root "jobs\dli\load_silver_to_dws_job.py") (Join-Path $dist "load_silver_to_dws_job.py")
Compress-Archive -Path (Join-Path $dist "*.py") -DestinationPath (Join-Path $dist "dli-hudi-jobs.zip") -Force
Write-Host "Packaged DLI jobs in $dist"
