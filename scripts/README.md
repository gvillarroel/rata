# Test Dataset Downloads

Run the PowerShell script below to download the current test datasets into `datasets/`:

```powershell
./scripts/download-test-datasets.ps1
```

The downloaded files are stored in `datasets/` and ignored by git.

## Large Performance Corpus

Run the PowerShell script below to download a larger local corpus into `datasets/perf/`.
The script stops after the downloaded files consume roughly the requested budget on disk.

```powershell
./scripts/download-large-test-datasets.ps1 -BudgetGB 5
```

The current corpus strategy uses:
- Quick, Draw simplified newline-delimited JSON files saved locally as `.jsonl`
- NYC TLC yellow taxi Parquet files from the official public trip-data distribution

The script writes a manifest to `datasets/perf/manifest.json`.

## Included Datasets

- `iris.csv`
  - Format: CSV
  - Source: `https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv`
- `cars.json`
  - Format: JSON
  - Source: `https://raw.githubusercontent.com/vega/vega-datasets/main/data/cars.json`
- `news_headlines.jsonl`
  - Format: JSONL
  - Source: `https://raw.githubusercontent.com/explosion/prodigy-recipes/master/example-datasets/news_headlines.jsonl`
- `userdata1.parquet`
  - Format: Parquet
  - Source: `https://raw.githubusercontent.com/Teradata/kylo/master/samples/sample-data/parquet/userdata1.parquet`
- `userdata1.avro`
  - Format: Avro
  - Source: `https://raw.githubusercontent.com/Teradata/kylo/master/samples/sample-data/avro/userdata1.avro`

## Notes

- These URLs were selected from Brave search results for small public sample datasets.
- The current set gives one sample per required format.
