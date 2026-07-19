param(
    [string]$OutputRoot = "datasets\converted\diffusion-trainer-validation",
    [int]$Rows = 16,
    [int]$Timesteps = 16,
    [int]$ExamplesPerRow = 2,
    [int]$MaxTrainRows = 2000,
    [int]$ReferenceMaxRows = 2000,
    [switch]$IncludePerf
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$datasetsDir = Join-Path $repoRoot "datasets"
$outputRootPath = Join-Path $repoRoot $OutputRoot
$modelsDir = Join-Path $outputRootPath "models"
$generatedDir = Join-Path $outputRootPath "generated"
$reportsDir = Join-Path $outputRootPath "reports"
$summaryPath = Join-Path $outputRootPath "summary.json"
$supportedExtensions = @(".csv", ".json", ".jsonl", ".parquet", ".avro")

New-Item -ItemType Directory -Force -Path $modelsDir, $generatedDir, $reportsDir | Out-Null

function ConvertTo-SafeName {
    param([string]$Value)

    $invalid = [System.IO.Path]::GetInvalidFileNameChars()
    $safe = $Value
    foreach ($char in $invalid) {
        $safe = $safe.Replace($char, "_")
    }
    return $safe.Replace("\", "_").Replace("/", "_").Replace(".", "_")
}

function Invoke-RataJson {
    param(
        [string]$Rata,
        [string[]]$Arguments,
        [string]$ReportPath
    )

    $output = & $Rata @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }

    $text = $output -join [Environment]::NewLine
    Set-Content -Path $ReportPath -Value $text
    return $text | ConvertFrom-Json
}

function Get-DownloadedDatasetFiles {
    $files = @(
        Get-ChildItem -LiteralPath $datasetsDir -File |
            Where-Object { $supportedExtensions -contains $_.Extension.ToLowerInvariant() }
    )

    if ($IncludePerf) {
        $manifestPath = Join-Path $datasetsDir "perf\manifest.json"
        if (Test-Path $manifestPath) {
            $manifest = Get-Content -Path $manifestPath | ConvertFrom-Json
            foreach ($entry in $manifest) {
                $path = Join-Path $repoRoot $entry.relative_path
                if (Test-Path $path) {
                    $files += Get-Item -LiteralPath $path
                }
            }
        }
    }

    return $files | Sort-Object FullName -Unique
}

Push-Location $repoRoot
try {
    cargo build --quiet -p rata-core --bin rata
} finally {
    Pop-Location
}

$rata = Join-Path $repoRoot "target\debug\rata.exe"
$results = @()
$hadFailure = $false

foreach ($dataset in Get-DownloadedDatasetFiles) {
    $relativePath = Resolve-Path -Path $dataset.FullName -Relative
    $safeName = ConvertTo-SafeName $relativePath
    $modelPath = Join-Path $modelsDir "$safeName.model.json"
    $generatedPath = Join-Path $generatedDir "$safeName.synthetic.json"
    $trainReportPath = Join-Path $reportsDir "$safeName.train.report.json"
    $generateReportPath = Join-Path $reportsDir "$safeName.generate.report.json"

    try {
        $train = Invoke-RataJson `
            -Rata $rata `
            -Arguments @(
                "train", "df", $dataset.FullName, $modelPath,
                "--seed", "42",
                "--timesteps", "$Timesteps",
                "--examples-per-row", "$ExamplesPerRow",
                "--max-rows", "$MaxTrainRows"
            ) `
            -ReportPath $trainReportPath

        $generate = Invoke-RataJson `
            -Rata $rata `
            -Arguments @(
                "gen", "df", $modelPath, $dataset.FullName, $generatedPath,
                "--rows", "$Rows",
                "--reference-max-rows", "$ReferenceMaxRows",
                "--seed", "7"
            ) `
            -ReportPath $generateReportPath

        $results += [pscustomobject]@{
            dataset = $relativePath
            status = "passed"
            method = $train.method
            row_count = $train.row_count
            numeric_column_count = @($train.numeric_columns).Count
            passthrough_column_count = @($train.passthrough_columns).Count
            generated_row_count = $generate.generated_row_count
            model_path = Resolve-Path -Path $modelPath -Relative
            synthetic_path = Resolve-Path -Path $generatedPath -Relative
            train_report_path = Resolve-Path -Path $trainReportPath -Relative
            generate_report_path = Resolve-Path -Path $generateReportPath -Relative
        }
    } catch {
        $hadFailure = $true
        $results += [pscustomobject]@{
            dataset = $relativePath
            status = "failed"
            error = $_.Exception.Message
            model_path = Resolve-Path -Path $modelPath -Relative -ErrorAction SilentlyContinue
            synthetic_path = Resolve-Path -Path $generatedPath -Relative -ErrorAction SilentlyContinue
            train_report_path = Resolve-Path -Path $trainReportPath -Relative -ErrorAction SilentlyContinue
            generate_report_path = Resolve-Path -Path $generateReportPath -Relative -ErrorAction SilentlyContinue
        }
    }
}

$summary = [pscustomobject]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    output_root = Resolve-Path -Path $outputRootPath -Relative
    rows_per_dataset = $Rows
    timesteps = $Timesteps
    examples_per_row = $ExamplesPerRow
    max_train_rows = $MaxTrainRows
    reference_max_rows = $ReferenceMaxRows
    include_perf = [bool]$IncludePerf
    dataset_count = @($results).Count
    passed_count = @($results | Where-Object { $_.status -eq "passed" }).Count
    failed_count = @($results | Where-Object { $_.status -eq "failed" }).Count
    results = $results
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath
$summary | ConvertTo-Json -Depth 8

if ($hadFailure) {
    throw "One or more downloaded datasets failed diffusion trainer validation. See $summaryPath."
}
