[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [switch]$SkipEndpointTest
)

$ErrorActionPreference = "Stop"

function Show-ErrorDialog {
    param([string]$Message)
    if ($NonInteractive) {
        Write-Error $Message
        return
    }
    [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "Codex LiteLLM setup",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}

function Normalize-Endpoint {
    param([string]$Endpoint)
    $value = $Endpoint.Trim().TrimEnd("/")
    $value = $value -replace "/chat/completions$", ""
    if ($value -notmatch "^https?://") {
        throw "Endpoint must start with http:// or https://."
    }
    return $value
}

function ConvertTo-Slug {
    param([string]$Value)
    $slug = $Value.ToLowerInvariant() -replace "[^a-z0-9]+", "-"
    $slug = $slug.Trim("-")
    if (-not $slug) {
        throw "The model name cannot be converted to a launcher name."
    }
    if ($slug.Length -gt 40) {
        $slug = $slug.Substring(0, 40).TrimEnd("-")
    }
    return $slug
}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-StablePort {
    param([string]$Value)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $sha.ComputeHash($bytes)
        $number = [BitConverter]::ToUInt16($hash, 0)
        return 4100 + ($number % 700)
    } finally {
        $sha.Dispose()
    }
}

function Get-InputsFromDialog {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Add an OpenAI-compatible model to Codex"
    $form.StartPosition = "CenterScreen"
    $form.Size = New-Object System.Drawing.Size(620, 330)
    $form.MinimumSize = New-Object System.Drawing.Size(620, 330)
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 10)
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $intro = New-Object System.Windows.Forms.Label
    $intro.Location = New-Object System.Drawing.Point(24, 18)
    $intro.Size = New-Object System.Drawing.Size(555, 42)
    $intro.Text = "This creates an isolated Codex launcher and keeps ChatGPT as the default provider."
    $form.Controls.Add($intro)

    $endpointLabel = New-Object System.Windows.Forms.Label
    $endpointLabel.Location = New-Object System.Drawing.Point(24, 72)
    $endpointLabel.Size = New-Object System.Drawing.Size(555, 22)
    $endpointLabel.Text = "OpenAI-compatible endpoint (base URL, usually ending in /v1)"
    $form.Controls.Add($endpointLabel)

    $endpointBox = New-Object System.Windows.Forms.TextBox
    $endpointBox.Location = New-Object System.Drawing.Point(24, 96)
    $endpointBox.Size = New-Object System.Drawing.Size(555, 25)
    $endpointBox.PlaceholderText = "https://example.com/openai/v1"
    $form.Controls.Add($endpointBox)

    $keyLabel = New-Object System.Windows.Forms.Label
    $keyLabel.Location = New-Object System.Drawing.Point(24, 133)
    $keyLabel.Size = New-Object System.Drawing.Size(555, 22)
    $keyLabel.Text = "API key"
    $form.Controls.Add($keyLabel)

    $keyBox = New-Object System.Windows.Forms.TextBox
    $keyBox.Location = New-Object System.Drawing.Point(24, 157)
    $keyBox.Size = New-Object System.Drawing.Size(555, 25)
    $keyBox.UseSystemPasswordChar = $true
    $form.Controls.Add($keyBox)

    $modelLabel = New-Object System.Windows.Forms.Label
    $modelLabel.Location = New-Object System.Drawing.Point(24, 194)
    $modelLabel.Size = New-Object System.Drawing.Size(555, 22)
    $modelLabel.Text = "Exact model ID"
    $form.Controls.Add($modelLabel)

    $modelBox = New-Object System.Windows.Forms.TextBox
    $modelBox.Location = New-Object System.Drawing.Point(24, 218)
    $modelBox.Size = New-Object System.Drawing.Size(555, 25)
    $modelBox.PlaceholderText = "glm-5.1"
    $form.Controls.Add($modelBox)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Location = New-Object System.Drawing.Point(393, 255)
    $cancel.Size = New-Object System.Drawing.Size(88, 30)
    $cancel.Text = "Cancel"
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($cancel)

    $ok = New-Object System.Windows.Forms.Button
    $ok.Location = New-Object System.Drawing.Point(491, 255)
    $ok.Size = New-Object System.Drawing.Size(88, 30)
    $ok.Text = "Configure"
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($ok)

    $form.AcceptButton = $ok
    $form.CancelButton = $cancel

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }

    return @{
        Endpoint = $endpointBox.Text
        ApiKey = $keyBox.Text
        Model = $modelBox.Text
    }
}

function Ensure-LiteLLM {
    $command = Get-Command litellm.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python is required to install LiteLLM but python.exe was not found."
    }

    & $python.Source -m pip install --user "litellm[proxy]"
    if ($LASTEXITCODE -ne 0) {
        throw "LiteLLM installation failed."
    }

    $candidate = Join-Path $env:APPDATA "Python\Python312\Scripts\litellm.exe"
    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }

    $command = Get-Command litellm.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "LiteLLM installed, but litellm.exe could not be located."
    }
    return $command.Source
}

function Find-Codex {
    $candidate = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin\codex.exe"
    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }
    $command = Get-Command codex.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*\WindowsApps\*") {
        return $command.Source
    }
    throw "codex.exe was not found. Install or open the Codex desktop app first."
}

try {
    if ($NonInteractive) {
        $inputs = @{
            Endpoint = $env:CODEX_COMPAT_ENDPOINT
            ApiKey = $env:CODEX_COMPAT_API_KEY
            Model = $env:CODEX_COMPAT_MODEL
        }
    } else {
        $inputs = Get-InputsFromDialog
        if ($null -eq $inputs) {
            Write-Output "Setup cancelled."
            exit 0
        }
    }

    if ([string]::IsNullOrWhiteSpace($inputs.Endpoint) -or
        [string]::IsNullOrWhiteSpace($inputs.ApiKey) -or
        [string]::IsNullOrWhiteSpace($inputs.Model)) {
        throw "Endpoint, API key, and model ID are all required."
    }

    $endpoint = Normalize-Endpoint $inputs.Endpoint
    $model = $inputs.Model.Trim()
    $slug = ConvertTo-Slug $model
    $envName = "CODEX_COMPAT_{0}_API_KEY" -f ($slug.ToUpperInvariant() -replace "-", "_")

    if (-not $SkipEndpointTest) {
        $headers = @{
            Authorization = "Bearer $($inputs.ApiKey)"
            "Content-Type" = "application/json"
        }
        $body = @{
            model = $model
            messages = @(@{ role = "user"; content = "Reply only with OK." })
            max_completion_tokens = 8
            stream = $false
        } | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Method Post -Uri "$endpoint/chat/completions" -Headers $headers -Body $body -TimeoutSec 60 | Out-Null
    }

    $litellmExe = Ensure-LiteLLM
    $codexExe = Find-Codex

    [Environment]::SetEnvironmentVariable($envName, $inputs.ApiKey, "User")
    Set-Item -Path "Env:$envName" -Value $inputs.ApiKey

    $providerRoot = Join-Path $env:USERPROFILE ".codex-providers\$slug"
    $launcherRoot = Join-Path $env:USERPROFILE ".codex\bin"
    New-Item -ItemType Directory -Force -Path $providerRoot, $launcherRoot | Out-Null

    $yamlPath = Join-Path $providerRoot "litellm.yaml"
    $catalogPath = Join-Path $providerRoot "models.json"
    $configPath = Join-Path $providerRoot "config.toml"
    $launcherPath = Join-Path $launcherRoot "codex-$slug.cmd"
    $port = Get-StablePort $slug
    $portsToStop = @($port)
    if (Test-Path -LiteralPath $configPath) {
        $oldConfig = Get-Content -Raw -LiteralPath $configPath
        if ($oldConfig -match "127\.0\.0\.1:(\d+)/v1") {
            $portsToStop += [int]$Matches[1]
        }
    }

    $yaml = @"
model_list:
  - model_name: $model
    litellm_params:
      model: openai/$model
      api_base: $endpoint
      api_key: os.environ/$envName
      use_chat_completions_api: true

litellm_settings:
  drop_params: true
"@

    $catalog = @{
        models = @(
            @{
                slug = $model
                display_name = "$model (compatible)"
                description = "$model through a local LiteLLM compatibility bridge."
                default_reasoning_level = $null
                supported_reasoning_levels = @()
                shell_type = "disabled"
                visibility = "list"
                supported_in_api = $true
                priority = 100
                additional_speed_tiers = @()
                service_tiers = @()
                availability_nux = $null
                upgrade = $null
                base_instructions = "You are a concise coding assistant. Tools are unavailable in this compatibility profile."
                model_messages = $null
                supports_reasoning_summaries = $false
                default_reasoning_summary = "none"
                support_verbosity = $false
                default_verbosity = "low"
                apply_patch_tool_type = $null
                web_search_tool_type = "text"
                truncation_policy = @{ mode = "tokens"; limit = 10000 }
                supports_parallel_tool_calls = $false
                supports_image_detail_original = $false
                supports_search_tool = $false
                experimental_supported_tools = @()
                input_modalities = @("text")
                context_window = 131072
                max_context_window = 131072
                effective_context_window_percent = 90
            }
        )
    } | ConvertTo-Json -Depth 8

    $config = @"
model = "$model"
model_provider = "compatible"
model_catalog_json = '$catalogPath'

[model_providers.compatible]
name = "Compatible model via LiteLLM"
base_url = "http://127.0.0.1:$port/v1"
wire_api = "responses"
request_max_retries = 4
stream_max_retries = 10
stream_idle_timeout_ms = 300000

[windows]
sandbox = "elevated"
"@

    $launcher = @"
@echo off
setlocal
set "CODEX_HOME=$providerRoot"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "`$key = [Environment]::GetEnvironmentVariable('$envName','User');" ^
  "if (-not `$key) { Write-Error '$envName is not configured.'; exit 1 };" ^
  "`$env:$envName = `$key;" ^
  "`$ready = Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue;" ^
  "if (-not `$ready) {" ^
  "  Start-Process -FilePath '$litellmExe' -ArgumentList @('--config','$yamlPath','--host','127.0.0.1','--port','$port') -WindowStyle Hidden;" ^
  "  1..60 | ForEach-Object { if (Test-NetConnection 127.0.0.1 -Port $port -InformationLevel Quiet -WarningAction SilentlyContinue) { exit 0 }; Start-Sleep -Milliseconds 500 };" ^
  "  Write-Error 'LiteLLM proxy did not start on port $port.'; exit 1" ^
  "}; exit 0"

if errorlevel 1 exit /b 1
if /I "%CD%"=="%USERPROFILE%" (
  "$codexExe" --model "$model" --cd "%USERPROFILE%\Documents" %*
) else (
  "$codexExe" --model "$model" %*
)
"@

    Write-Utf8NoBom -Path $yamlPath -Content $yaml
    Write-Utf8NoBom -Path $catalogPath -Content $catalog
    Write-Utf8NoBom -Path $configPath -Content $config
    Set-Content -LiteralPath $launcherPath -Value $launcher -Encoding ascii

    $portsToStop | Select-Object -Unique | ForEach-Object {
        Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
    }

    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathParts = @($userPath -split ";" | Where-Object { $_.Trim() })
    if (-not ($pathParts | Where-Object { $_.TrimEnd("\") -ieq $launcherRoot.TrimEnd("\") })) {
        [Environment]::SetEnvironmentVariable("Path", (($pathParts + $launcherRoot) -join ";"), "User")
    }

    $result = "codex-$slug"
    if ($NonInteractive) {
        Write-Output "CONFIGURED=true"
        Write-Output "LAUNCHER=$result"
        Write-Output "MODEL=$model"
        Write-Output "ENDPOINT=$endpoint"
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "Configuration complete.`n`nOpen a new PowerShell window and run:`n$result`n`nYour default ChatGPT configuration was not changed.",
            "Codex LiteLLM setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    }
} catch {
    Show-ErrorDialog $_.Exception.Message
    exit 1
}
