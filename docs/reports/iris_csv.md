# Dataset Statistics Report

- Source: `C:\Users\villa\dev\rata\datasets\iris.csv`
- Format: `csv`
- Rows: `150`
- Columns: `5`
- Column Pairs: `10`
- Nested Fields: `5`

## Structure Overview

- Dataset Types: number:600, string:150

| Column | Observed Types | Structure | Semantic Hints |
| --- | --- | --- | --- |
| petal_length | number:150 | flat scalar | - |
| petal_width | number:150 | flat scalar | - |
| sepal_length | number:150 | flat scalar | - |
| sepal_width | number:150 | flat scalar | - |
| species | string:150 | flat scalar | - |

## Nested Fields

| Path | Occurrences | Nulls | Observed Types |
| --- | ---: | ---: | --- |
| petal_length | 150 | 0 | number:150 |
| petal_width | 150 | 0 | number:150 |
| sepal_length | 150 | 0 | number:150 |
| sepal_width | 150 | 0 | number:150 |
| species | 150 | 0 | string:150 |

| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| petal_length | number | 150 | 0 | 0 | 43 | min=1, max=6.9, mean=3.758, median=4.350, p95=6.100, dup_ratio=0.71, outliers=0, entropy=5.03 |
| petal_width | number | 150 | 0 | 0 | 22 | min=0.1, max=2.5, mean=1.199, median=1.300, p95=2.300, dup_ratio=0.85, outliers=0, entropy=4.05 |
| sepal_length | number | 150 | 0 | 0 | 35 | min=4.3, max=7.9, mean=5.843, median=5.800, p95=7.255, dup_ratio=0.77, outliers=0, entropy=4.82 |
| sepal_width | number | 150 | 0 | 0 | 23 | min=2, max=4.4, mean=3.057, median=3.000, p95=3.800, dup_ratio=0.85, outliers=4, entropy=4.02 |
| species | string | 150 | 0 | 0 | 3 | min_len=6, max_len=10, avg_len=8.33, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |

## Numeric Column Pairs

| Left | Right | Paired Rows | Pearson | Covariance | Equal Scalars |
| --- | --- | ---: | ---: | ---: | ---: |
| petal_length | petal_width | 150 | 0.9629 | 1.2870 | 0 |
| petal_length | sepal_length | 150 | 0.8718 | 1.2658 | 0 |
| petal_length | sepal_width | 150 | -0.4284 | -0.3275 | 0 |
| petal_width | sepal_length | 150 | 0.8179 | 0.5128 | 0 |
| petal_width | sepal_width | 150 | -0.3661 | -0.1208 | 0 |
| sepal_length | sepal_width | 150 | -0.1176 | -0.0422 | 0 |

