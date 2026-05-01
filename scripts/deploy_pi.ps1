param(
    [string]$Target = "yuki@192.168.137.111",
    [string]$RemoteDir = "~/2dosumi"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== 2dosumi deploy =="
Write-Host "Target: $Target"
Write-Host "Remote: $RemoteDir"
Write-Host ""

Write-Host "1/4 Creating remote directory..."
ssh $Target "mkdir -p $RemoteDir"

Write-Host "2/4 Copying project files..."
scp -r `
    pyproject.toml `
    README.md `
    config.toml.example `
    .env.example `
    src `
    tests `
    systemd `
    $Target`:$RemoteDir/

Write-Host "3/4 Setting up Python environment and default config..."
ssh $Target "cd $RemoteDir && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip setuptools && python -m pip install -e . && cp -n config.toml.example config.toml && cp -n .env.example .env"

Write-Host "4/4 Running tests and simulator smoke test on Raspberry Pi..."
ssh $Target "cd $RemoteDir && . .venv/bin/activate && python -m unittest discover -s tests -v && 2dosumi run --source sim --speed 240 --max-samples 360 --no-discord --no-buzzer | grep -E '\[state\]|SECOND_SLEEP' | tail -n 12"

Write-Host ""
Write-Host "Deploy complete."
Write-Host "Next commands on Pi:"
Write-Host "  cd ~/2dosumi"
Write-Host "  nano .env          # set DISCORD_WEBHOOK_URL later"
Write-Host "  2dosumi run --source sim --speed 30"
