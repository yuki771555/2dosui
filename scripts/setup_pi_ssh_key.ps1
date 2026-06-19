param(
    [string]$HostName = "192.168.137.105",
    [string]$User = "yuki",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519"
)

$ErrorActionPreference = "Stop"
$Target = "$User@$HostName"
$PubKeyPath = "$KeyPath.pub"

if (-not (Test-Path $KeyPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $KeyPath) | Out-Null
    $KeygenCommand = 'ssh-keygen -t ed25519 -f "{0}" -N "" -C "codex-deploy"' -f $KeyPath
    cmd.exe /d /c $KeygenCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create SSH key: $KeyPath"
    }
}

if (-not (Test-Path $PubKeyPath)) {
    ssh-keygen -y -f $KeyPath | Set-Content -NoNewline -Path $PubKeyPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create public key: $PubKeyPath"
    }
}

Write-Host "Registering SSH key on $Target"
Write-Host "Enter the Raspberry Pi password when prompted. This is needed only once."

Get-Content $PubKeyPath | ssh $Target "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

Write-Host "Testing key login..."
ssh -o BatchMode=yes $Target "echo SSH key login OK"

Write-Host "Done. Future deploys can use: .\scripts\deploy_pi.ps1 -AllowDirty"
