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

function Test-HuaweiCredential(
  [string]$AccountName,
  [string]$IamUser,
  [string]$Password,
  [string]$Region
) {
  $payload = @{
    auth = @{
      identity = @{
        methods = @("password")
        password = @{
          user = @{
            domain = @{ name = $AccountName }
            name = $IamUser
            password = $Password
          }
        }
      }
      scope = @{ project = @{ name = $Region } }
    }
  } | ConvertTo-Json -Depth 20

  try {
    $response = Invoke-WebRequest `
      -Method Post `
      -Uri "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true" `
      -ContentType "application/json;charset=utf8" `
      -Body $payload `
      -TimeoutSec 45
    $body = $response.Content | ConvertFrom-Json
    return [pscustomobject]@{
      Ok = $true
      ProjectId = [string]$body.token.project.id
      Message = "Credential validated."
    }
  }
  catch {
    return [pscustomobject]@{
      Ok = $false
      ProjectId = ""
      Message = "Huawei Cloud IAM rejected the credential. Please check the account, IAM user, password, and region."
    }
  }
}

$existing = Get-SatCredentialProfile
if ($existing) {
  if (-not $Region -and $existing.Region) { $Region = $existing.Region }
  if (-not $ProjectId -and $existing.ProjectId) { $ProjectId = $existing.ProjectId }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "SAT Mexico Huawei Cloud Login"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(500, 300)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$accountBox = New-TextBox ($existing.AccountName) 160 24
$iamBox = New-TextBox ($existing.IamUser) 160 64
$passwordBox = New-TextBox "" 160 104 $true
$regionBox = New-TextBox $Region 160 144
$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Enter the IAM password, then click Save."
$statusLabel.Location = New-Object System.Drawing.Point(24, 184)
$statusLabel.Size = New-Object System.Drawing.Size(430, 34)

$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Text = "Save"
$saveButton.Location = New-Object System.Drawing.Point(280, 224)
$saveButton.Size = New-Object System.Drawing.Size(80, 30)
$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(370, 224)
$cancelButton.Size = New-Object System.Drawing.Size(80, 30)

$form.Controls.Add((New-Label "Main account" 24 27))
$form.Controls.Add($accountBox)
$form.Controls.Add((New-Label "IAM user" 24 67))
$form.Controls.Add($iamBox)
$form.Controls.Add((New-Label "IAM password" 24 107))
$form.Controls.Add($passwordBox)
$form.Controls.Add((New-Label "Region" 24 147))
$form.Controls.Add($regionBox)
$form.Controls.Add($statusLabel)
$form.Controls.Add($saveButton)
$form.Controls.Add($cancelButton)

$cancelButton.Add_Click({
  $form.Tag = "cancel"
  $form.Close()
})

$saveButton.Add_Click({
  $account = $accountBox.Text.Trim()
  $iam = $iamBox.Text.Trim()
  $password = $passwordBox.Text
  $regionValue = $regionBox.Text.Trim()
  if (-not $account -or -not $iam -or -not $password -or -not $regionValue) {
    $statusLabel.Text = "All fields are required."
    return
  }

  $saveButton.Enabled = $false
  $statusLabel.Text = "Validating with Huawei Cloud IAM..."
  $form.Refresh()
  $result = Test-HuaweiCredential -AccountName $account -IamUser $iam -Password $password -Region $regionValue
  if (-not $result.Ok) {
    $statusLabel.Text = $result.Message
    $saveButton.Enabled = $true
    return
  }

  $effectiveProjectId = if ($ProjectId) { $ProjectId } else { $result.ProjectId }
  Save-SatCredentialProfile -AccountName $account -IamUser $iam -Password $password -Region $regionValue -ProjectId $effectiveProjectId | Out-Null
  $form.Tag = "saved"
  $form.Close()
})

[void]$form.ShowDialog()

if ($form.Tag -ne "saved") {
  throw "Credential update canceled."
}

Write-Host "SAT Mexico Huawei Cloud credential profile saved and validated."
