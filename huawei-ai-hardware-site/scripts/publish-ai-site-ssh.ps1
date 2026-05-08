$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$archive = Join-Path $repoRoot "deploy\ai-hardware-config-site.tar.gz"
$targetHost = "119.8.152.171"
$targetUser = "root"

function Show-PasswordDialog {
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing

  $form = New-Object System.Windows.Forms.Form
  $form.Text = "Publish AI Site over SSH"
  $form.Size = New-Object System.Drawing.Size(520, 180)
  $form.StartPosition = "CenterScreen"
  $form.FormBorderStyle = "FixedDialog"
  $form.MaximizeBox = $false
  $form.MinimizeBox = $false

  $label = New-Object System.Windows.Forms.Label
  $label.Text = "ECS root/admin password for $targetHost"
  $label.SetBounds(16, 18, 460, 24)
  $form.Controls.Add($label)

  $password = New-Object System.Windows.Forms.TextBox
  $password.UseSystemPasswordChar = $true
  $password.SetBounds(16, 48, 470, 26)
  $form.Controls.Add($password)

  $publishButton = New-Object System.Windows.Forms.Button
  $publishButton.Text = "Publish"
  $publishButton.SetBounds(286, 88, 96, 32)
  $publishButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
  $form.Controls.Add($publishButton)

  $cancelButton = New-Object System.Windows.Forms.Button
  $cancelButton.Text = "Cancel"
  $cancelButton.SetBounds(390, 88, 96, 32)
  $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
  $form.Controls.Add($cancelButton)

  $form.AcceptButton = $publishButton
  $form.CancelButton = $cancelButton

  if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
    throw "Publish cancelled."
  }

  if ([string]::IsNullOrWhiteSpace($password.Text)) {
    throw "Password is required."
  }

  return $password.Text
}

if (-not (Test-Path -LiteralPath $archive)) {
  throw "Missing site archive: $archive. Run npm run package:ai-site first."
}

$passwordValue = Show-PasswordDialog
$env:AI_SITE_SSH_PASSWORD = $passwordValue
$env:AI_SITE_ARCHIVE = $archive
$env:AI_SITE_HOST = $targetHost
$env:AI_SITE_USER = $targetUser

$python = @'
import os
import posixpath
import sys
import time
import paramiko

host = os.environ["AI_SITE_HOST"]
user = os.environ["AI_SITE_USER"]
password = os.environ["AI_SITE_SSH_PASSWORD"]
archive = os.environ["AI_SITE_ARCHIVE"]
remote_archive = "/tmp/ai-hardware-config-site.tar.gz"
target = "/var/www/ai-hardware-config-site"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, username=user, password=password, timeout=30, look_for_keys=False, allow_agent=False)

try:
    sftp = client.open_sftp()
    try:
        sftp.put(archive, remote_archive)
    finally:
        sftp.close()

    commands = [
        f"mkdir -p {target}",
        f"tar -xzf {remote_archive} -C {target}",
        "nginx -t",
        "systemctl restart nginx"
    ]
    for command in commands:
        stdin, stdout, stderr = client.exec_command(command)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        if code != 0:
            sys.stderr.write(out + err)
            raise SystemExit(code)
finally:
    client.close()

print(f"Published {archive} to http://{host}/")
'@

try {
  $python | python -
  if ($LASTEXITCODE -ne 0) {
    throw "SSH publish failed with exit code $LASTEXITCODE"
  }
}
finally {
  Remove-Item Env:\AI_SITE_SSH_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:\AI_SITE_ARCHIVE -ErrorAction SilentlyContinue
  Remove-Item Env:\AI_SITE_HOST -ErrorAction SilentlyContinue
  Remove-Item Env:\AI_SITE_USER -ErrorAction SilentlyContinue
}
