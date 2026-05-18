@echo off
chcp 65001 >nul
setlocal

REM ── ChatBI Huawei Cloud Deploy Script (Windows) ───────────────────────
REM Usage: deploy.bat [plan|apply|destroy|output|ssh|status]

set TERRAFORM_DIR=%~dp0..\terraform
set CREDS_FILE=%USERPROFILE%\.claude\huawei-chatbi\credentials.env
set ACTION=%1

if "%ACTION%"=="" (
    echo Usage: deploy.bat [plan^|apply^|destroy^|output^|ssh^|status]
    exit /b 1
)

REM ── Load credentials ──────────────────────────────────────────────────
if not exist "%CREDS_FILE%" (
    echo ERROR: Credentials not found at %CREDS_FILE%
    echo Run /huawei-chatbi configure first
    exit /b 1
)

for /f "tokens=1,2 delims==" %%a in (%CREDS_FILE%) do (
    if "%%a"=="HW_ACCESS_KEY"  set HW_ACCESS_KEY=%%b
    if "%%a"=="HW_SECRET_KEY"  set HW_SECRET_KEY=%%b
    if "%%a"=="HW_REGION"      set HW_REGION=%%b
    if "%%a"=="MAAS_API_KEY"   set MAAS_API_KEY=%%b
    if "%%a"=="MAAS_BASE_URL"  set MAAS_BASE_URL=%%b
    if "%%a"=="MAAS_MODEL"     set MAAS_MODEL=%%b
    if "%%a"=="ECS_FLAVOR"     set ECS_FLAVOR=%%b
    if "%%a"=="DWS_FLAVOR"     set DWS_FLAVOR=%%b
    if "%%a"=="EIP_BANDWIDTH"  set EIP_BANDWIDTH=%%b
)

REM ── Write terraform.tfvars ────────────────────────────────────────────
(
echo access_key    = "%HW_ACCESS_KEY%"
echo secret_key    = "%HW_SECRET_KEY%"
echo region        = "%HW_REGION%"
echo maas_api_key  = "%MAAS_API_KEY%"
echo maas_base_url = "%MAAS_BASE_URL%"
echo maas_model    = "%MAAS_MODEL%"
echo ecs_flavor    = "%ECS_FLAVOR%"
echo dws_flavor    = "%DWS_FLAVOR%"
echo eip_bandwidth = %EIP_BANDWIDTH%
echo project_name  = "chatbi"
) > "%TERRAFORM_DIR%\terraform.tfvars"

set CHECKPOINT_DISABLE=1

if "%ACTION%"=="plan" (
    echo === Terraform Init ===
    terraform -chdir="%TERRAFORM_DIR%" init -upgrade
    echo === Terraform Plan ===
    terraform -chdir="%TERRAFORM_DIR%" plan -out=tfplan
    goto :end
)

if "%ACTION%"=="apply" (
    if not exist "%TERRAFORM_DIR%\tfplan" (
        echo No tfplan found. Running plan first...
        terraform -chdir="%TERRAFORM_DIR%" init -upgrade
        terraform -chdir="%TERRAFORM_DIR%" plan -out=tfplan
    )
    echo === Terraform Apply ===
    terraform -chdir="%TERRAFORM_DIR%" apply tfplan
    echo === Outputs ===
    terraform -chdir="%TERRAFORM_DIR%" output
    goto :end
)

if "%ACTION%"=="output" (
    terraform -chdir="%TERRAFORM_DIR%" output
    goto :end
)

if "%ACTION%"=="status" (
    terraform -chdir="%TERRAFORM_DIR%" state list
    terraform -chdir="%TERRAFORM_DIR%" output
    goto :end
)

if "%ACTION%"=="destroy" (
    echo.
    echo WARNING: This will permanently destroy ALL resources including DWS data!
    set /p CONFIRM=Type 'yes' to confirm:
    if not "%CONFIRM%"=="yes" (
        echo Aborted.
        exit /b 1
    )
    terraform -chdir="%TERRAFORM_DIR%" destroy -auto-approve
    goto :end
)

if "%ACTION%"=="ssh" (
    for /f "tokens=2 delims==" %%a in ('terraform -chdir="%TERRAFORM_DIR%" output -raw ecs_public_ip 2^>nul') do set ECS_IP=%%a
    set ECS_IP=
    for /f %%a in ('terraform -chdir="%TERRAFORM_DIR%" output -raw ecs_public_ip') do set ECS_IP=%%a
    echo Connecting to %ECS_IP%...
    ssh -i "%~dp0..\chatbi-keypair.pem" ubuntu@%ECS_IP%
    goto :end
)

echo Unknown action: %ACTION%
exit /b 1

:end
endlocal
