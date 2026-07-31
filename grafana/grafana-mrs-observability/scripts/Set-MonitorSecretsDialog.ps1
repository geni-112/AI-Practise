param()

$ErrorActionPreference = "Stop"
$profilePath = Join-Path $env:LOCALAPPDATA "Codex\huawei-mrs-observability\secrets.xml"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Huawei MRS Observability Secrets"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(520, 260)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

function Add-SecretRow([string]$Label, [int]$Y) {
  $labelControl = New-Object System.Windows.Forms.Label
  $labelControl.Text = $Label
  $labelControl.Location = New-Object System.Drawing.Point(24, $Y)
  $labelControl.Size = New-Object System.Drawing.Size(180, 24)
  $box = New-Object System.Windows.Forms.TextBox
  $box.Location = New-Object System.Drawing.Point(210, $Y)
  $box.Size = New-Object System.Drawing.Size(270, 24)
  $box.UseSystemPasswordChar = $true
  $form.Controls.Add($labelControl)
  $form.Controls.Add($box)
  $box
}

$grafanaBox = Add-SecretRow "New Grafana admin password" 30
$mrsDumpBox = Add-SecretRow "MRS SFTP password" 75

$note = New-Object System.Windows.Forms.Label
$note.Text = "Use strong, different passwords. They are DPAPI-encrypted in your Windows profile."
$note.Location = New-Object System.Drawing.Point(24, 118)
$note.Size = New-Object System.Drawing.Size(460, 34)
$form.Controls.Add($note)

$save = New-Object System.Windows.Forms.Button
$save.Text = "Save"
$save.Location = New-Object System.Drawing.Point(310, 166)
$save.Size = New-Object System.Drawing.Size(80, 30)
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = "Cancel"
$cancel.Location = New-Object System.Drawing.Point(400, 166)
$cancel.Size = New-Object System.Drawing.Size(80, 30)
$form.Controls.Add($save)
$form.Controls.Add($cancel)

$save.Add_Click({
  if ($grafanaBox.Text.Length -lt 12 -or $mrsDumpBox.Text.Length -lt 12) {
    [System.Windows.Forms.MessageBox]::Show(
      "Each password must contain at least 12 characters.",
      "Password too short"
    ) | Out-Null
    return
  }
  $dir = Split-Path -Parent $profilePath
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  [pscustomobject]@{
    GrafanaAdminPassword = ConvertTo-SecureString -String $grafanaBox.Text -AsPlainText -Force
    MrsDumpPassword = ConvertTo-SecureString -String $mrsDumpBox.Text -AsPlainText -Force
  } | Export-Clixml -LiteralPath $profilePath
  $form.Tag = "saved"
  $form.Close()
})
$cancel.Add_Click({ $form.Close() })
[void]$form.ShowDialog()
if ($form.Tag -ne "saved") { throw "Secret entry canceled." }
Write-Host "Monitor secrets saved in the local encrypted profile."
