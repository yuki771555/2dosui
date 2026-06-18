param(
    [string]$HostName = "192.168.137.105",
    [string]$User = "yuki",
    [string]$RemoteDir = "/home/yuki/2dosumi",
    [int]$Port = 8080,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$Target = "$User@$HostName"

$Dirty = git status --porcelain
if ($Dirty -and -not $AllowDirty) {
    throw "Working tree has uncommitted changes. Commit/stash them, or pass -AllowDirty for a test deployment."
}

ssh $Target "mkdir -p '$RemoteDir/config' '$RemoteDir/twodosumi' '$RemoteDir/scripts' '$RemoteDir/docs'"

scp -r twodosumi scripts docs requirements-pi.txt README.md "${Target}:$RemoteDir/"

$RemoteConfig = "$RemoteDir/config/pi.aggregate.json"
$ConfigExists = ssh $Target "test -f '$RemoteConfig' && echo exists || true"
if ($ConfigExists.Trim() -ne "exists") {
    scp config/pi.aggregate.json "${Target}:$RemoteDir/config/pi.aggregate.json"
    Write-Host "Created initial Pi config at $RemoteConfig"
} else {
    Write-Host "Keeping existing Pi config at $RemoteConfig"
}

$RemoteScript = @'
set -euo pipefail

APP_DIR="$1"
APP_USER="$2"
PORT="$3"

cd "$APP_DIR"

if ! python3 -m venv .venv; then
  echo "Failed to create .venv. On Raspberry Pi OS, install venv support with:" >&2
  echo "  sudo apt-get update && sudo apt-get install -y python3-venv" >&2
  exit 1
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-pi.txt

chmod +x scripts/install_twodosumi_web_service.sh
APP_DIR="$APP_DIR" APP_USER="$APP_USER" PORT="$PORT" ./scripts/install_twodosumi_web_service.sh

curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null
echo "Health check passed: http://127.0.0.1:${PORT}/healthz"
'@

$RemoteScript | ssh $Target "bash -s -- '$RemoteDir' '$User' '$Port'"

Write-Host "Deployed to ${Target}:$RemoteDir"
Write-Host "If Tailscale Serve is not configured yet, run on the Pi: tailscale serve --bg $Port"
