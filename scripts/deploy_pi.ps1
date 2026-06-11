param(
    [string]$HostName = "192.168.137.105",
    [string]$User = "yuki",
    [string]$RemoteDir = "/home/yuki/2dosumi"
)

$ErrorActionPreference = "Stop"
$Target = "$User@$HostName"

ssh $Target "mkdir -p '$RemoteDir/config' '$RemoteDir/twodosumi' '$RemoteDir/scripts'"
scp -r twodosumi config requirements-pi.txt README.md "${Target}:$RemoteDir/"
Write-Host "Deployed to ${Target}:$RemoteDir"

