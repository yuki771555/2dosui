param(
    [switch]$KeepBuildFiles
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot "report\twodosumi_seminar_report.tex"
$buildDir = Join-Path $repoRoot "tmp\pdfs\twodosumi-report"
$outputDir = Join-Path $repoRoot "output\pdf"
$output = Join-Path $outputDir "twodosumi_introduction_seminar_report.pdf"

New-Item -ItemType Directory -Force -Path $buildDir, $outputDir | Out-Null

Push-Location $repoRoot
try {
    for ($pass = 1; $pass -le 2; $pass++) {
        & lualatex -interaction=nonstopmode -halt-on-error `
            -output-directory="$buildDir" "$source"
        if ($LASTEXITCODE -ne 0) {
            throw "LuaLaTeX pass $pass failed with exit code $LASTEXITCODE"
        }
    }

    Copy-Item -LiteralPath (Join-Path $buildDir "twodosumi_seminar_report.pdf") `
        -Destination $output -Force
}
finally {
    Pop-Location
}

if (-not $KeepBuildFiles) {
    Get-ChildItem -LiteralPath $buildDir -File |
        Where-Object { $_.Extension -ne ".pdf" } |
        Remove-Item -Force
}

Write-Output $output
