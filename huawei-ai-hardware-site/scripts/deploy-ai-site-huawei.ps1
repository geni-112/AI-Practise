$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$tfDir = Join-Path $repoRoot "terraform\ai-hardware-config-site"
$localDir = Join-Path $repoRoot ".local"
$tfvarsPath = Join-Path $localDir "ai-site-deploy.tfvars"
$planPath = Join-Path $localDir "ai-site-deploy.tfplan"
$statusPath = Join-Path $localDir "ai-site-deploy-status.txt"

New-Item -ItemType Directory -Force -Path $localDir | Out-Null

function ConvertTo-TfString {
  param([string]$Value)
  return '"' + ($Value -replace '\\', '\\' -replace '"', '\"') + '"'
}

function Show-DeployDialog {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing

  $form = New-Object System.Windows.Forms.Form
  $form.Text = "Huawei Cloud LA-Santiago Deploy"
  $form.Size = New-Object System.Drawing.Size(620, 500)
  $form.StartPosition = "CenterScreen"
  $form.FormBorderStyle = "FixedDialog"
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false

  $layout = New-Object System.Windows.Forms.TableLayoutPanel
  $layout.Dock = "Fill"
  $layout.Padding = New-Object System.Windows.Forms.Padding(16)
  $layout.RowCount = 9
  $layout.ColumnCount = 2
  $layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 160))) | Out-Null
  $layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
  $form.Controls.Add($layout)

  function Add-Field {
    param(
      [string]$Label,
      [string]$Name,
      [string]$Default = "",
      [bool]$Password = $false
    )
    $row = $layout.RowCount - 9 + $script:fieldIndex
    $labelControl = New-Object System.Windows.Forms.Label
    $labelControl.Text = $Label
    $labelControl.Dock = "Fill"
    $labelControl.TextAlign = "MiddleLeft"
    $textBox = New-Object System.Windows.Forms.TextBox
    $textBox.Name = $Name
    $textBox.Text = $Default
    $textBox.Dock = "Fill"
    if ($Password) {
      $textBox.UseSystemPasswordChar = $true
    }
    $layout.Controls.Add($labelControl, 0, $script:fieldIndex)
    $layout.Controls.Add($textBox, 1, $script:fieldIndex)
    $script:fields[$Name] = $textBox
    $script:fieldIndex += 1
  }

  $script:fields = @{}
  $script:fieldIndex = 0
  Add-Field "Access Key" "access_key" "" $false
  Add-Field "Secret Key" "secret_key" "" $true
  Add-Field "IAM Domain Name" "domain_name" "" $false
  Add-Field "ECS Admin Password" "admin_password" "" $true
  Add-Field "SSH Admin CIDR" "admin_cidr" "0.0.0.0/0" $false
  Add-Field "Project Name" "project_name" "ai-hw-config" $false

  $note = New-Object System.Windows.Forms.Label
  $note.Text = "The script tries the smallest on-demand ECS in la-south-2 first: 1 vCPU / 2 GB, then falls back. Credentials are written only to ignored .local tfvars."
  $note.Dock = "Fill"
  $note.Height = 52
  $layout.SetColumnSpan($note, 2)
  $layout.Controls.Add($note, 0, $script:fieldIndex)
  $script:fieldIndex += 1

  $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
  $buttons.Dock = "Fill"
  $buttons.FlowDirection = "RightToLeft"
  $deployButton = New-Object System.Windows.Forms.Button
  $deployButton.Text = "Deploy"
  $deployButton.Width = 110
  $deployButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $cancelButton = New-Object System.Windows.Forms.Button
  $cancelButton.Text = "Cancel"
  $cancelButton.Width = 90
  $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $buttons.Controls.Add($deployButton) | Out-Null
  $buttons.Controls.Add($cancelButton) | Out-Null
  $layout.SetColumnSpan($buttons, 2)
  $layout.Controls.Add($buttons, 0, $script:fieldIndex)

  $form.AcceptButton = $deployButton
  $form.CancelButton = $cancelButton

  $result = $form.ShowDialog()
  if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
    throw "Deployment cancelled."
  }

  $values = @{}
  foreach ($key in $script:fields.Keys) {
    $values[$key] = $script:fields[$key].Text.Trim()
  }

  foreach ($required in @("access_key", "secret_key", "domain_name", "admin_password")) {
    if ([string]::IsNullOrWhiteSpace($values[$required])) {
      throw "Missing required field: $required"
    }
  }

  return $values
}

function Write-TfVars {
  param(
    [hashtable]$Values,
    [hashtable]$FlavorCandidate
  )

  New-Item -ItemType Directory -Force -Path $localDir | Out-Null

  $lines = @(
    "access_key = $(ConvertTo-TfString $Values.access_key)",
    "secret_key = $(ConvertTo-TfString $Values.secret_key)",
    "domain_name = $(ConvertTo-TfString $Values.domain_name)",
    "admin_password = $(ConvertTo-TfString $Values.admin_password)",
    "admin_cidr = $(ConvertTo-TfString $Values.admin_cidr)",
    "project_name = $(ConvertTo-TfString $Values.project_name)",
    "create_rds = false",
    "region = `"la-south-2`"",
    "image_id = $(ConvertTo-TfString $FlavorCandidate.ImageId)",
    "ecs_flavor_id = $(ConvertTo-TfString $FlavorCandidate.FlavorId)",
    "ecs_performance_type = $(ConvertTo-TfString $FlavorCandidate.PerformanceType)",
    "ecs_cpu_core_count = $($FlavorCandidate.Cpu)",
    "ecs_memory_size = $($FlavorCandidate.Memory)"
  )

  Set-Content -Path $tfvarsPath -Value $lines -Encoding UTF8
}

function Invoke-Terraform {
  param([string[]]$Arguments)
  & terraform @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "terraform $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

Set-Content -Path $statusPath -Value "Preparing package..." -Encoding UTF8
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "package-ai-site.ps1")
if ($LASTEXITCODE -ne 0) {
  throw "Site package failed."
}

$values = Show-DeployDialog

$candidates = @(
  @{ Name = "1 vCPU / 2 GB by availability query"; Cpu = 1; Memory = 2; PerformanceType = "normal"; FlavorId = ""; ImageId = "" },
  @{ Name = "2 vCPU / 4 GB by availability query"; Cpu = 2; Memory = 4; PerformanceType = "normal"; FlavorId = ""; ImageId = "" },
  @{ Name = "2 vCPU / 4 GB explicit fallback c6.large.2"; Cpu = 2; Memory = 4; PerformanceType = "normal"; FlavorId = "c6.large.2"; ImageId = "a4605ecc-7558-4d2c-95f7-3a595ec3f876" }
)

Push-Location $tfDir
try {
  Set-Content -Path $statusPath -Value "Running terraform init..." -Encoding UTF8
  Invoke-Terraform -Arguments @("init", "-input=false")

  $selected = $null
  foreach ($candidate in $candidates) {
    Set-Content -Path $statusPath -Value "Planning with $($candidate.Name)..." -Encoding UTF8
    Write-TfVars -Values $values -FlavorCandidate $candidate
    & terraform plan -input=false -var-file="$tfvarsPath" -out="$planPath"
    if ($LASTEXITCODE -eq 0) {
      $selected = $candidate
      break
    }
  }

  if ($null -eq $selected) {
    throw "Terraform plan failed for all minimum flavor candidates. Confirm ECS flavor and Ubuntu image availability in la-south-2."
  }

  Set-Content -Path $statusPath -Value "Applying with $($selected.Name)..." -Encoding UTF8
  Invoke-Terraform -Arguments @("apply", "-input=false", "$planPath")

  $siteUrl = (& terraform output -raw site_url).Trim()
  $flavor = (& terraform output -raw selected_ecs_flavor).Trim()
  $az = (& terraform output -raw selected_availability_zone).Trim()
  $message = "Deployment completed. URL=$siteUrl; AZ=$az; ECS Flavor=$flavor"
  Set-Content -Path $statusPath -Value $message -Encoding UTF8
  Write-Host $message

  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.MessageBox]::Show($message, "Huawei Cloud Deployment Completed") | Out-Null
}
finally {
  Pop-Location
}
