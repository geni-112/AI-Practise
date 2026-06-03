$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Huawei Cloud IAM fallback credentials"
$form.Size = New-Object System.Drawing.Size(460, 300)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$form.Font = $font

function Add-Label([string]$Text, [int]$Y) {
  $label = New-Object System.Windows.Forms.Label
  $label.Text = $Text
  $label.Location = New-Object System.Drawing.Point(24, $Y)
  $label.Size = New-Object System.Drawing.Size(130, 24)
  $form.Controls.Add($label)
}

function Add-TextBox([int]$Y, [bool]$Password = $false, [string]$Default = "") {
  $box = New-Object System.Windows.Forms.TextBox
  $box.Location = New-Object System.Drawing.Point(160, $Y)
  $box.Size = New-Object System.Drawing.Size(280, 24)
  $box.Text = $Default
  if ($Password) {
    $box.UseSystemPasswordChar = $true
  }
  $form.Controls.Add($box)
  return $box
}

Add-Label "Domain account" 24
$domainBox = Add-TextBox 24

Add-Label "IAM user" 68
$userBox = Add-TextBox 68

Add-Label "IAM password" 112
$passwordBox = Add-TextBox 112 $true

Add-Label "Region" 156
$regionBox = Add-TextBox 156 $false "la-south-2"

$hint = New-Object System.Windows.Forms.Label
$hint.Text = "Credentials will be encrypted locally with Windows DPAPI. Secrets are not printed."
$hint.Location = New-Object System.Drawing.Point(24, 198)
$hint.Size = New-Object System.Drawing.Size(416, 24)
$form.Controls.Add($hint)

$ok = New-Object System.Windows.Forms.Button
$ok.Text = "Save"
$ok.Location = New-Object System.Drawing.Point(258, 230)
$ok.Size = New-Object System.Drawing.Size(82, 30)
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $ok
$form.Controls.Add($ok)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = "Cancel"
$cancel.Location = New-Object System.Drawing.Point(350, 230)
$cancel.Size = New-Object System.Drawing.Size(82, 30)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancel
$form.Controls.Add($cancel)

$result = $form.ShowDialog()
if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
  Write-Host "Canceled. No fallback credentials were saved."
  exit 1
}

if (-not $domainBox.Text.Trim() -or -not $userBox.Text.Trim() -or -not $passwordBox.Text -or -not $regionBox.Text.Trim()) {
  throw "All fields are required."
}

$dir = Join-Path $env:LOCALAPPDATA "Codex\huawei-cloud-bigdata"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$path = Join-Path $dir "iam-fallback-credentials.xml"

$record = [pscustomobject]@{
  DomainName = $domainBox.Text.Trim()
  IamUserName = $userBox.Text.Trim()
  IamPassword = ConvertTo-SecureString $passwordBox.Text -AsPlainText -Force
  Region = $regionBox.Text.Trim()
  CreatedAt = (Get-Date).ToString("s")
}

$record | Export-Clixml -Path $path
Write-Host "Saved IAM fallback credentials to $path"
Write-Host "Secret values were DPAPI-encrypted and were not printed."
