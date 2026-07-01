param(
  [string]$Region = "la-north-2",
  [string]$ProjectId = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "SatCredentialStore.ps1")

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function New-Label([string]$Text, [int]$X, [int]$Y) {
  $label = New-Object System.Windows.Forms.Label
  $label.Text = $Text
  $label.Location = New-Object System.Drawing.Point($X, $Y)
  $label.Size = New-Object System.Drawing.Size(130, 24)
  return $label
}

function New-TextBox([string]$Value, [int]$X, [int]$Y, [bool]$Password = $false) {
  $box = New-Object System.Windows.Forms.TextBox
  $box.Text = $Value
  $box.Location = New-Object System.Drawing.Point($X, $Y)
  $box.Size = New-Object System.Drawing.Size(300, 24)
  $box.UseSystemPasswordChar = $Password
  return $box
}

$existing = Get-SatCredentialProfile
if ($existing) {
  if ($existing.Region) { $Region = $existing.Region }
  if ($existing.ProjectId) { $ProjectId = $existing.ProjectId }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "SAT Mexico Huawei Cloud AK/SK"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(510, 315)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$akBox = New-TextBox ($existing.AccessKey) 170 24
$skBox = New-TextBox "" 170 64 $true
$regionBox = New-TextBox $Region 170 104
$projectBox = New-TextBox $ProjectId 170 144
$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Enter AK/SK, then click Save."
$statusLabel.Location = New-Object System.Drawing.Point(24, 184)
$statusLabel.Size = New-Object System.Drawing.Size(440, 44)

$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Text = "Save"
$saveButton.Location = New-Object System.Drawing.Point(290, 238)
$saveButton.Size = New-Object System.Drawing.Size(80, 30)
$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(380, 238)
$cancelButton.Size = New-Object System.Drawing.Size(80, 30)

$form.Controls.Add((New-Label "Access Key ID" 24 27))
$form.Controls.Add($akBox)
$form.Controls.Add((New-Label "Secret Access Key" 24 67))
$form.Controls.Add($skBox)
$form.Controls.Add((New-Label "Region" 24 107))
$form.Controls.Add($regionBox)
$form.Controls.Add((New-Label "Project ID" 24 147))
$form.Controls.Add($projectBox)
$form.Controls.Add($statusLabel)
$form.Controls.Add($saveButton)
$form.Controls.Add($cancelButton)

$cancelButton.Add_Click({
  $form.Tag = "cancel"
  $form.Close()
})

$saveButton.Add_Click({
  $ak = $akBox.Text.Trim()
  $sk = $skBox.Text
  $regionValue = $regionBox.Text.Trim()
  $projectValue = $projectBox.Text.Trim()
  if (-not $ak -or -not $sk -or -not $regionValue -or -not $projectValue) {
    $statusLabel.Text = "All fields are required."
    return
  }

  $saveButton.Enabled = $false
  $statusLabel.Text = "Validating AK/SK with Huawei Cloud ECS..."
  $form.Refresh()

  $oldAk = $env:HUAWEICLOUD_ACCESS_KEY
  $oldSk = $env:HUAWEICLOUD_SECRET_KEY
  $oldRegion = $env:HUAWEICLOUD_REGION
  $oldProject = $env:HUAWEICLOUD_PROJECT_ID
  $env:HUAWEICLOUD_ACCESS_KEY = $ak
  $env:HUAWEICLOUD_SECRET_KEY = $sk
  $env:HUAWEICLOUD_REGION = $regionValue
  $env:HUAWEICLOUD_PROJECT_ID = $projectValue
  try {
    $output = & python (Join-Path $PSScriptRoot "validate_huawei_aksk.py") 2>&1
    if ($LASTEXITCODE -ne 0) {
      $statusLabel.Text = (($output | Out-String).Trim())
      $saveButton.Enabled = $true
      return
    }
    Save-SatAkSkProfile -AccessKey $ak -SecretKey $sk -Region $regionValue -ProjectId $projectValue | Out-Null
    $form.Tag = "saved"
    $form.Close()
  }
  finally {
    $env:HUAWEICLOUD_ACCESS_KEY = $oldAk
    $env:HUAWEICLOUD_SECRET_KEY = $oldSk
    $env:HUAWEICLOUD_REGION = $oldRegion
    $env:HUAWEICLOUD_PROJECT_ID = $oldProject
  }
})

[void]$form.ShowDialog()

if ($form.Tag -ne "saved") {
  throw "AK/SK update canceled."
}

Write-Host "SAT Mexico Huawei Cloud AK/SK profile saved and validated."
