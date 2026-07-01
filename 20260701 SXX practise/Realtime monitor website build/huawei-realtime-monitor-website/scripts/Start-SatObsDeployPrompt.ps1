param()

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
. (Join-Path $PSScriptRoot "SatCredentialStore.ps1")

$repoRoot = Split-Path -Parent $PSScriptRoot
$defaultAccount = ""
$defaultIamUser = ""
$defaultPassword = ""
$savedProfile = Get-SatCredentialProfile
if ($savedProfile) {
  $defaultAccount = $savedProfile.AccountName
  $defaultIamUser = $savedProfile.IamUser
  $defaultPassword = $savedProfile.Password
}
$statusPath = Join-Path $repoRoot "monitor\data\status.json"
if ((-not $defaultAccount -or -not $defaultIamUser) -and (Test-Path -LiteralPath $statusPath)) {
  try {
    $status = Get-Content -LiteralPath $statusPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $defaultAccount = [string]$status.account.domain_name
    $defaultIamUser = [string]$status.account.iam_user
  }
  catch {
    $defaultAccount = ""
    $defaultIamUser = ""
  }
}

function New-Label([string]$Text, [int]$X, [int]$Y) {
  $label = New-Object System.Windows.Forms.Label
  $label.Text = $Text
  $label.Location = New-Object System.Drawing.Point($X, $Y)
  $label.Size = New-Object System.Drawing.Size(160, 22)
  $label
}

function New-TextBox([int]$X, [int]$Y, [bool]$Password = $false) {
  $box = New-Object System.Windows.Forms.TextBox
  $box.Location = New-Object System.Drawing.Point($X, $Y)
  $box.Size = New-Object System.Drawing.Size(330, 24)
  if ($Password) { $box.UseSystemPasswordChar = $true }
  $box
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Deploy SAT Monitor to Mexico City2 OBS"
$form.Size = New-Object System.Drawing.Size(590, 455)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$title = New-Object System.Windows.Forms.Label
$title.Text = "Deploy static monitor files to la-north-2. This can create/use an OBS bucket."
$title.Location = New-Object System.Drawing.Point(24, 18)
$title.Size = New-Object System.Drawing.Size(525, 22)
$title.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($title)

$form.Controls.Add((New-Label "Main account name" 24 58))
$accountBox = New-TextBox 195 56
$accountBox.Text = $defaultAccount
$form.Controls.Add($accountBox)

$form.Controls.Add((New-Label "IAM user name" 24 96))
$iamBox = New-TextBox 195 94
$iamBox.Text = $defaultIamUser
$form.Controls.Add($iamBox)

$form.Controls.Add((New-Label "IAM password" 24 134))
$passwordBox = New-TextBox 195 132 $true
$passwordBox.Text = $defaultPassword
$form.Controls.Add($passwordBox)

$form.Controls.Add((New-Label "OBS bucket (optional)" 24 172))
$bucketBox = New-TextBox 195 170
$form.Controls.Add($bucketBox)

$createBox = New-Object System.Windows.Forms.CheckBox
$createBox.Text = "Create the OBS bucket if missing (pay-per-use storage and request traffic may be charged)."
$createBox.Location = New-Object System.Drawing.Point(24, 212)
$createBox.Size = New-Object System.Drawing.Size(530, 24)
$createBox.Checked = $true
$form.Controls.Add($createBox)

$note = New-Object System.Windows.Forms.Label
$note.Text = "Default OBS website domains in Mexico may require a custom domain for browser preview. The files are still deployed in Mexico City2."
$note.Location = New-Object System.Drawing.Point(24, 252)
$note.Size = New-Object System.Drawing.Size(530, 44)
$note.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($note)

$saveProfileBox = New-Object System.Windows.Forms.CheckBox
$saveProfileBox.Text = "Save/update encrypted local credential profile for next time."
$saveProfileBox.Location = New-Object System.Drawing.Point(24, 302)
$saveProfileBox.Size = New-Object System.Drawing.Size(530, 24)
$saveProfileBox.Checked = $true
$form.Controls.Add($saveProfileBox)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Deploy"
$runButton.Location = New-Object System.Drawing.Point(344, 354)
$runButton.Size = New-Object System.Drawing.Size(92, 30)
$runButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $runButton
$form.Controls.Add($runButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(446, 354)
$cancelButton.Size = New-Object System.Drawing.Size(86, 30)
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancelButton
$form.Controls.Add($cancelButton)

if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
  Write-Host "SAT OBS deployment cancelled."
  exit 1
}

if (-not $accountBox.Text.Trim() -or -not $iamBox.Text.Trim() -or -not $passwordBox.Text) {
  [System.Windows.Forms.MessageBox]::Show("Main account name, IAM user name, and password are required.", "Missing input", "OK", "Warning") | Out-Null
  exit 1
}

$env:HUAWEICLOUD_ACCOUNT_NAME = $accountBox.Text.Trim()
$env:HUAWEICLOUD_IAM_USER = $iamBox.Text.Trim()
$env:HUAWEICLOUD_IAM_PASSWORD = $passwordBox.Text
$env:HUAWEICLOUD_REGION = "la-north-2"
if ($bucketBox.Text.Trim()) {
  $env:SAT_MONITOR_OBS_BUCKET = $bucketBox.Text.Trim()
}

if ($saveProfileBox.Checked) {
  $savedPath = Save-SatCredentialProfile `
    -AccountName $env:HUAWEICLOUD_ACCOUNT_NAME `
    -IamUser $env:HUAWEICLOUD_IAM_USER `
    -Password $env:HUAWEICLOUD_IAM_PASSWORD `
    -Region $env:HUAWEICLOUD_REGION
  Write-Host "Encrypted SAT Mexico credential profile saved locally: $savedPath"
}

python (Join-Path $PSScriptRoot "build_static_site.py") --zip
if ($LASTEXITCODE -ne 0) {
  throw "Static site build failed."
}

$args = @((Join-Path $PSScriptRoot "deploy_obs_static_site.py"), "--region", "la-north-2")
if ($createBox.Checked) {
  $args += "--create-bucket"
}
python @args
if ($LASTEXITCODE -ne 0) {
  throw "OBS static website deployment failed."
}

$resultPath = Join-Path $repoRoot "exports\sat_obs_website_la-north-2.json"
if (Test-Path -LiteralPath $resultPath) {
  $result = Get-Content -LiteralPath $resultPath -Encoding UTF8 -Raw | ConvertFrom-Json
  [System.Windows.Forms.MessageBox]::Show("Website files deployed to Mexico City2.`n`nURL: $($result.website_url)", "SAT monitor deployed", "OK", "Information") | Out-Null
}
