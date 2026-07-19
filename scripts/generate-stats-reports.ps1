$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$datasetsDir = Join-Path $repoRoot "datasets"
$reportsDir = Join-Path $repoRoot "docs\reports"

if (-not (Test-Path $datasetsDir)) {
    throw "Datasets directory not found: $datasetsDir"
}

New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$datasets = Get-ChildItem -Path $datasetsDir -File | Where-Object { $_.Name -ne ".gitkeep" }

foreach ($dataset in $datasets) {
    $reportStem = $dataset.Name -replace "\.", "_"
    $markdownPath = Join-Path $reportsDir "$reportStem.md"
    $jsonPath = Join-Path $reportsDir "$reportStem.json"
    $datasetPath = Resolve-Path -Relative $dataset.FullName

    Write-Host "Generating reports for $($dataset.Name)"

    $markdown = cargo run -p rata-core --bin rata -- stats $datasetPath
    $markdown | Set-Content -Path $markdownPath -Encoding utf8

    $json = cargo run -p rata-core --bin rata -- stats $datasetPath --output json
    $json | Set-Content -Path $jsonPath -Encoding utf8
}

Write-Host ""
Write-Host "Reports written to $reportsDir"
