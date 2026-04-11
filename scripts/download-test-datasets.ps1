$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$datasetsDir = Join-Path $repoRoot "datasets"

New-Item -ItemType Directory -Force -Path $datasetsDir | Out-Null

$downloads = @(
    @{
        FileName = "iris.csv"
        Url = "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv"
        Format = "csv"
        Source = "mwaskom/seaborn-data"
    },
    @{
        FileName = "cars.json"
        Url = "https://raw.githubusercontent.com/vega/vega-datasets/main/data/cars.json"
        Format = "json"
        Source = "vega/vega-datasets"
    },
    @{
        FileName = "news_headlines.jsonl"
        Url = "https://raw.githubusercontent.com/explosion/prodigy-recipes/master/example-datasets/news_headlines.jsonl"
        Format = "jsonl"
        Source = "explosion/prodigy-recipes"
    },
    @{
        FileName = "userdata1.parquet"
        Url = "https://raw.githubusercontent.com/Teradata/kylo/master/samples/sample-data/parquet/userdata1.parquet"
        Format = "parquet"
        Source = "Teradata/kylo"
    },
    @{
        FileName = "userdata1.avro"
        Url = "https://raw.githubusercontent.com/Teradata/kylo/master/samples/sample-data/avro/userdata1.avro"
        Format = "avro"
        Source = "Teradata/kylo"
    }
)

foreach ($download in $downloads) {
    $targetPath = Join-Path $datasetsDir $download.FileName
    Write-Host "Downloading $($download.FileName) [$($download.Format)] from $($download.Source)"
    Invoke-WebRequest -Uri $download.Url -OutFile $targetPath
}

Write-Host ""
Write-Host "Downloaded test datasets into $datasetsDir"
