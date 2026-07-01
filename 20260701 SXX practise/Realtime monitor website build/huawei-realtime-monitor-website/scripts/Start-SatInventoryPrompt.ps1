param(
  [switch]$SkipInventory
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot "SatCredentialStore.ps1")

$savedProfile = Get-SatCredentialProfile

function New-Label([string]$Text, [int]$X, [int]$Y) {
  $label = New-Object System.Windows.Forms.Label
  $label.Text = $Text
  $label.Location = New-Object System.Drawing.Point($X, $Y)
  $label.Size = New-Object System.Drawing.Size(145, 22)
  $label
}

function New-TextBox([int]$X, [int]$Y, [bool]$Password = $false) {
  $box = New-Object System.Windows.Forms.TextBox
  $box.Location = New-Object System.Drawing.Point($X, $Y)
  $box.Size = New-Object System.Drawing.Size(320, 24)
  if ($Password) {
    $box.UseSystemPasswordChar = $true
  }
  $box
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "SAT Mexico Huawei Cloud Resource Inventory"
$form.Size = New-Object System.Drawing.Size(560, 450)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$title = New-Object System.Windows.Forms.Label
$title.Text = "Huawei Cloud resource inventory for the selected customer account."
$title.Location = New-Object System.Drawing.Point(24, 18)
$title.Size = New-Object System.Drawing.Size(500, 22)
$title.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($title)

$form.Controls.Add((New-Label "Main account name" 24 58))
$accountBox = New-TextBox 180 56
if ($savedProfile) { $accountBox.Text = $savedProfile.AccountName }
$form.Controls.Add($accountBox)

$form.Controls.Add((New-Label "IAM user name" 24 96))
$iamBox = New-TextBox 180 94
if ($savedProfile) { $iamBox.Text = $savedProfile.IamUser }
$form.Controls.Add($iamBox)

$form.Controls.Add((New-Label "IAM password" 24 134))
$passwordBox = New-TextBox 180 132 $true
if ($savedProfile) { $passwordBox.Text = $savedProfile.Password }
$form.Controls.Add($passwordBox)

$form.Controls.Add((New-Label "Mexico region" 24 172))
$regionBox = New-Object System.Windows.Forms.ComboBox
$regionBox.Location = New-Object System.Drawing.Point(180, 170)
$regionBox.Size = New-Object System.Drawing.Size(320, 24)
$regionBox.DropDownStyle = "DropDownList"
[void]$regionBox.Items.Add("na-mexico-1 | LA-Mexico City1")
[void]$regionBox.Items.Add("la-north-2 | LA-Mexico City2")
$regionBox.SelectedIndex = 1
if ($savedProfile -and $savedProfile.Region -eq "na-mexico-1") { $regionBox.SelectedIndex = 0 }
$form.Controls.Add($regionBox)

$form.Controls.Add((New-Label "Project ID (optional)" 24 210))
$projectBox = New-TextBox 180 208
if ($savedProfile) { $projectBox.Text = $savedProfile.ProjectId }
$form.Controls.Add($projectBox)

$form.Controls.Add((New-Label "DataArts workspace ID" 24 248))
$workspaceBox = New-TextBox 180 246
$form.Controls.Add($workspaceBox)

$note = New-Object System.Windows.Forms.Label
$note.Text = "Credentials stay in this local PowerShell process and are not written to repository files."
$note.Location = New-Object System.Drawing.Point(24, 286)
$note.Size = New-Object System.Drawing.Size(500, 22)
$note.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($note)

$saveProfileBox = New-Object System.Windows.Forms.CheckBox
$saveProfileBox.Text = "Save/update encrypted local credential profile for next time."
$saveProfileBox.Location = New-Object System.Drawing.Point(24, 314)
$saveProfileBox.Size = New-Object System.Drawing.Size(470, 24)
$saveProfileBox.Checked = $true
$form.Controls.Add($saveProfileBox)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Run inventory"
$runButton.Location = New-Object System.Drawing.Point(294, 356)
$runButton.Size = New-Object System.Drawing.Size(110, 30)
$runButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $runButton
$form.Controls.Add($runButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(414, 356)
$cancelButton.Size = New-Object System.Drawing.Size(86, 30)
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancelButton
$form.Controls.Add($cancelButton)

$result = $form.ShowDialog()
if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
  Write-Host "SAT Mexico inventory prompt cancelled."
  exit 1
}

if (-not $accountBox.Text.Trim() -or -not $iamBox.Text.Trim() -or -not $passwordBox.Text) {
  [System.Windows.Forms.MessageBox]::Show("Main account name, IAM user name, and password are required.", "Missing input", "OK", "Warning") | Out-Null
  exit 1
}

$selectedRegion = ($regionBox.SelectedItem -split "\|")[0].Trim()
$env:HUAWEICLOUD_ACCOUNT_NAME = $accountBox.Text.Trim()
$env:HUAWEICLOUD_IAM_USER = $iamBox.Text.Trim()
$env:HUAWEICLOUD_IAM_PASSWORD = $passwordBox.Text
$env:HUAWEICLOUD_REGION = $selectedRegion
if ($projectBox.Text.Trim()) {
  $env:HUAWEICLOUD_PROJECT_ID = $projectBox.Text.Trim()
}
else {
  Remove-Item Env:\HUAWEICLOUD_PROJECT_ID -ErrorAction SilentlyContinue
}
if ($workspaceBox.Text.Trim()) {
  $env:DATAARTS_WORKSPACE_ID = $workspaceBox.Text.Trim()
}
else {
  Remove-Item Env:\DATAARTS_WORKSPACE_ID -ErrorAction SilentlyContinue
}

if ($saveProfileBox.Checked) {
  $savedPath = Save-SatCredentialProfile `
    -AccountName $env:HUAWEICLOUD_ACCOUNT_NAME `
    -IamUser $env:HUAWEICLOUD_IAM_USER `
    -Password $env:HUAWEICLOUD_IAM_PASSWORD `
    -Region $env:HUAWEICLOUD_REGION `
    -ProjectId ($env:HUAWEICLOUD_PROJECT_ID)
  Write-Host "Encrypted SAT Mexico credential profile saved locally: $savedPath"
}

Write-Host "SAT Mexico credential variables are set for this process. Region: $selectedRegion"
if ($SkipInventory) {
  exit 0
}

$repoRoot = Split-Path -Parent $PSScriptRoot
python (Join-Path $PSScriptRoot "huawei_inventory.py")
python (Join-Path $PSScriptRoot "analyze_bigdata_assets.py")

$statusPath = Join-Path $repoRoot "monitor\data\status.json"
if (Test-Path -LiteralPath $statusPath) {
  $status = Get-Content -LiteralPath $statusPath -Encoding UTF8 -Raw | ConvertFrom-Json
  $message = "Resources: {0}`nCatalog objects: {1}`nJobs: {2}`nRisks: {3}" -f `
    $status.summary.resource_count, $status.summary.catalog_count, $status.summary.job_count, $status.summary.risk_count
  [System.Windows.Forms.MessageBox]::Show($message, "SAT Mexico inventory finished", "OK", "Information") | Out-Null
}
