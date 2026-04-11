param(
    [double]$BudgetGB = 5.0
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$datasetsDir = Join-Path $repoRoot "datasets"
$perfDir = Join-Path $datasetsDir "perf"
$manifestPath = Join-Path $perfDir "manifest.json"
$targetBytes = [int64]($BudgetGB * 1GB)

New-Item -ItemType Directory -Force -Path $perfDir | Out-Null

function Get-DirectorySizeBytes {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return [int64]0
    }

    return [int64](Get-ChildItem -LiteralPath $Path -Recurse -File | Measure-Object -Property Length -Sum).Sum
}

function Get-DownloadManifest {
    if (Test-Path $manifestPath) {
        return Get-Content $manifestPath | ConvertFrom-Json
    }

    return @()
}

function Save-DownloadManifest {
    param([object[]]$Manifest)

    $Manifest | ConvertTo-Json -Depth 8 | Set-Content -Path $manifestPath
}

function Add-ManifestEntry {
    param(
        [object[]]$Manifest,
        [hashtable]$Entry
    )

    $existing = $Manifest | Where-Object { $_.relative_path -eq $Entry.relative_path } | Select-Object -First 1
    if ($null -ne $existing) {
        $existing.source = $Entry.source
        $existing.url = $Entry.url
        $existing.format = $Entry.format
        $existing.size_bytes = $Entry.size_bytes
        return $Manifest
    }

    return @($Manifest + [pscustomobject]$Entry)
}

function Build-ManifestFromExistingFiles {
    param(
        [object[]]$Downloads,
        [string]$DatasetsDir
    )

    $rebuilt = @()
    foreach ($download in $Downloads) {
        $targetPath = Join-Path $DatasetsDir $download.RelativePath
        if (-not (Test-Path $targetPath)) {
            continue
        }

        $sizeBytes = (Get-Item -LiteralPath $targetPath).Length
        $rebuilt = Add-ManifestEntry -Manifest $rebuilt -Entry @{
            relative_path = Resolve-Path -Relative $targetPath
            source = $download.Source
            url = $download.Url
            format = $download.Format
            size_bytes = $sizeBytes
        }
    }

    return $rebuilt
}

function Download-IfNeeded {
    param(
        [string]$Url,
        [string]$TargetPath,
        [string]$Format,
        [string]$Source,
        [object[]]$Manifest
    )

    if (Test-Path $TargetPath) {
        $sizeBytes = (Get-Item -LiteralPath $TargetPath).Length
        Write-Host "Reusing $TargetPath ($([math]::Round($sizeBytes / 1MB, 2)) MiB)"
    } else {
        $tmpPath = "$TargetPath.partial"
        if (Test-Path $tmpPath) {
            Remove-Item -LiteralPath $tmpPath -Force
        }

        Write-Host "Downloading $TargetPath [$Format] from $Source"
        try {
            Invoke-WebRequest -Uri $Url -OutFile $tmpPath
            Move-Item -LiteralPath $tmpPath -Destination $TargetPath
            $sizeBytes = (Get-Item -LiteralPath $TargetPath).Length
        } catch {
            if (Test-Path $tmpPath) {
                Remove-Item -LiteralPath $tmpPath -Force
            }

            Write-Warning ("Skipping {0}: {1}" -f $Url, $_.Exception.Message)
            return $Manifest
        }
    }

    return Add-ManifestEntry -Manifest $Manifest -Entry @{
        relative_path = Resolve-Path -Relative $TargetPath
        source = $Source
        url = $Url
        format = $Format
        size_bytes = $sizeBytes
    }
}

$downloads = @()

$quickDrawCategories = @(
    "cat", "dog", "tree", "car", "airplane", "apple", "bicycle", "bird", "book", "bus",
    "butterfly", "camera", "chair", "cloud", "computer", "cup", "face", "fish", "flower",
    "guitar", "hammer", "horse", "house", "key", "moon", "rabbit", "star", "sun", "train",
    "truck", "whale", "bear", "boat", "candle", "castle", "circle", "cookie", "couch",
    "crab", "duck", "elephant"
)

foreach ($category in $quickDrawCategories) {
    $downloads += @{
        RelativePath = "perf\\quickdraw-$category.jsonl"
        Url = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/$category.ndjson"
        Format = "jsonl"
        Source = "googlecreativelab/quickdraw-dataset"
    }
}

foreach ($year in 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015) {
    foreach ($month in 1..12) {
        $monthToken = "{0:D4}-{1:D2}" -f $year, $month
        $downloads += @{
            RelativePath = "perf\\yellow_tripdata_$monthToken.parquet"
            Url = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_$monthToken.parquet"
            Format = "parquet"
            Source = "NYC TLC Trip Record Data"
        }
    }
}

$manifest = Get-DownloadManifest

foreach ($download in $downloads) {
    $currentSize = Get-DirectorySizeBytes -Path $perfDir
    if ($currentSize -ge $targetBytes) {
        break
    }

    $targetPath = Join-Path $datasetsDir $download.RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null

    $manifest = Download-IfNeeded `
        -Url $download.Url `
        -TargetPath $targetPath `
        -Format $download.Format `
        -Source $download.Source `
        -Manifest $manifest

    Save-DownloadManifest -Manifest $manifest

    $newSize = Get-DirectorySizeBytes -Path $perfDir
    $progress = [math]::Min(100, [math]::Round(($newSize / $targetBytes) * 100, 2))
    Write-Host ("Current perf corpus size: {0:N2} GiB / {1:N2} GiB ({2}%)" -f ($newSize / 1GB), ($targetBytes / 1GB), $progress)
}

$manifest = Build-ManifestFromExistingFiles -Downloads $downloads -DatasetsDir $datasetsDir
Save-DownloadManifest -Manifest $manifest

$finalSize = Get-DirectorySizeBytes -Path $perfDir
Write-Host ""
Write-Host ("Prepared performance datasets in {0}" -f $perfDir)
Write-Host ("Final size: {0:N2} GiB" -f ($finalSize / 1GB))
