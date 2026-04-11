# Dataset Statistics Report

- Source: `C:\Users\villa\dev\rata\datasets\cars.json`
- Format: `json`
- Rows: `406`
- Columns: `9`
- Column Pairs: `36`
- Nested Fields: `9`

## Structure Overview

- Dataset Types: null:14, number:2422, string:1218

| Column | Observed Types | Structure | Semantic Hints |
| --- | --- | --- | --- |
| Acceleration | number:406 | flat scalar | - |
| Cylinders | number:406 | flat scalar | - |
| Displacement | number:406 | flat scalar | - |
| Horsepower | null:6, number:400 | flat scalar | - |
| Miles_per_Gallon | null:8, number:398 | flat scalar | - |
| Name | string:406 | flat scalar | - |
| Origin | string:406 | flat scalar | - |
| Weight_in_lbs | number:406 | flat scalar | - |
| Year | string:406 | flat scalar | temporal |

## Nested Fields

| Path | Occurrences | Nulls | Observed Types |
| --- | ---: | ---: | --- |
| Acceleration | 406 | 0 | number:406 |
| Cylinders | 406 | 0 | number:406 |
| Displacement | 406 | 0 | number:406 |
| Horsepower | 406 | 6 | null:6, number:400 |
| Miles_per_Gallon | 406 | 8 | null:8, number:398 |
| Name | 406 | 0 | string:406 |
| Origin | 406 | 0 | string:406 |
| Weight_in_lbs | 406 | 0 | number:406 |
| Year | 406 | 0 | string:406 |

| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Acceleration | number | 406 | 0 | 0 | 96 | min=8, max=24.8, mean=15.520, median=15.500, p95=20.325, dup_ratio=0.76, outliers=6, entropy=5.96 |
| Cylinders | number | 406 | 0 | 0 | 5 | min=3, max=8, mean=5.475, median=4.000, p95=8.000, dup_ratio=0.99, outliers=0, entropy=1.59 |
| Displacement | number | 406 | 0 | 0 | 83 | min=68, max=455, mean=194.780, median=151.000, p95=400.000, dup_ratio=0.80, outliers=0, entropy=5.74 |
| Horsepower | number | 400 | 6 | 0 | 93 | min=46, max=230, mean=105.082, median=95.000, p95=180.000, dup_ratio=0.77, outliers=8, entropy=5.86 |
| Miles_per_Gallon | number | 398 | 8 | 0 | 129 | min=9, max=46.6, mean=23.515, median=23.000, p95=37.030, dup_ratio=0.68, outliers=1, entropy=6.22 |
| Name | string | 406 | 0 | 0 | 311 | min_len=6, max_len=36, avg_len=16.27, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| Origin | string | 406 | 0 | 0 | 3 | min_len=3, max_len=6, avg_len=3.93, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| Weight_in_lbs | number | 406 | 0 | 0 | 356 | min=1613, max=5140, mean=2979.414, median=2822.500, p95=4462.250, dup_ratio=0.12, outliers=0, entropy=8.40 |
| Year | string | 406 | 0 | 0 | 12 | min_len=10, max_len=10, avg_len=10.00, empty=0, date_like=406, email_like=0, ip_like=0, url_like=0, json_like=0 |

## Numeric Column Pairs

| Left | Right | Paired Rows | Pearson | Covariance | Equal Scalars |
| --- | --- | ---: | ---: | ---: | ---: |
| Acceleration | Cylinders | 406 | -0.5225 | -2.5015 | 2 |
| Acceleration | Displacement | 406 | -0.5580 | -163.7184 | 0 |
| Acceleration | Horsepower | 400 | -0.6971 | -75.6124 | 0 |
| Acceleration | Miles_per_Gallon | 398 | 0.4203 | 9.0362 | 8 |
| Acceleration | Weight_in_lbs | 406 | -0.4301 | -1018.7050 | 0 |
| Cylinders | Displacement | 406 | 0.9518 | 170.5617 | 0 |
| Cylinders | Horsepower | 400 | 0.8442 | 56.0444 | 0 |
| Cylinders | Miles_per_Gallon | 398 | -0.7754 | -10.2830 | 0 |
| Cylinders | Weight_in_lbs | 406 | 0.8952 | 1295.0570 | 0 |
| Displacement | Horsepower | 400 | 0.8983 | 3657.5580 | 0 |
| Displacement | Miles_per_Gallon | 398 | -0.8042 | -653.7556 | 0 |
| Displacement | Weight_in_lbs | 406 | 0.9325 | 82664.7033 | 0 |
| Horsepower | Miles_per_Gallon | 392 | -0.7784 | -233.2613 | 0 |
| Horsepower | Weight_in_lbs | 400 | 0.8666 | 28466.8609 | 0 |
| Miles_per_Gallon | Weight_in_lbs | 398 | -0.8317 | -5491.3796 | 0 |

