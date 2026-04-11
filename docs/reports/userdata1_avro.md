# Dataset Statistics Report

- Source: `C:\Users\villa\dev\rata\datasets\userdata1.avro`
- Format: `avro`
- Rows: `1000`
- Columns: `13`
- Column Pairs: `78`
- Nested Fields: `13`

## Structure Overview

- Dataset Types: null:358, number:2642, string:10000

| Column | Observed Types | Structure | Semantic Hints |
| --- | --- | --- | --- |
| birthdate | string:1000 | flat scalar | base64_like |
| cc | null:291, number:709 | flat scalar | - |
| comments | string:1000 | flat scalar | hex_like, base64_like |
| country | string:1000 | flat scalar | base64_like |
| email | string:1000 | flat scalar | email_like |
| first_name | string:1000 | flat scalar | base64_like |
| gender | string:1000 | flat scalar | - |
| id | number:1000 | flat scalar | monotonic_increasing |
| ip_address | string:1000 | flat scalar | ip_like |
| last_name | string:1000 | flat scalar | base64_like |
| registration_dttm | string:1000 | flat scalar | temporal |
| salary | null:67, number:933 | flat scalar | - |
| title | string:1000 | flat scalar | base64_like |

## Nested Fields

| Path | Occurrences | Nulls | Observed Types |
| --- | ---: | ---: | --- |
| birthdate | 1000 | 0 | string:1000 |
| cc | 1000 | 291 | null:291, number:709 |
| comments | 1000 | 0 | string:1000 |
| country | 1000 | 0 | string:1000 |
| email | 1000 | 0 | string:1000 |
| first_name | 1000 | 0 | string:1000 |
| gender | 1000 | 0 | string:1000 |
| id | 1000 | 0 | number:1000 |
| ip_address | 1000 | 0 | string:1000 |
| last_name | 1000 | 0 | string:1000 |
| registration_dttm | 1000 | 0 | string:1000 |
| salary | 1000 | 67 | null:67, number:933 |
| title | 1000 | 0 | string:1000 |

| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| birthdate | string | 1000 | 0 | 0 | 787 | min_len=0, max_len=10, avg_len=7.20, empty=198, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| cc | number | 709 | 291 | 0 | 709 | min=4017951658384, max=6771600305307320000, mean=410311243193780096.000, median=3580839316768053.000, p95=4936365156928857088.000, dup_ratio=0.00, outliers=221, entropy=9.47 |
| comments | string | 1000 | 0 | 0 | 88 | min_len=0, max_len=217, avg_len=4.98, empty=807, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| country | string | 1000 | 0 | 0 | 120 | min_len=4, max_len=34, avg_len=7.53, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| email | string | 1000 | 0 | 0 | 985 | min_len=0, max_len=32, avg_len=20.63, empty=16, date_like=0, email_like=984, ip_like=0, url_like=0, json_like=0 |
| first_name | string | 1000 | 0 | 0 | 198 | min_len=0, max_len=11, avg_len=5.64, empty=16, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| gender | string | 1000 | 0 | 0 | 3 | min_len=0, max_len=6, avg_len=4.70, empty=67, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| id | number | 1000 | 0 | 0 | 1000 | min=1, max=1000, mean=500.500, median=500.500, p95=950.050, dup_ratio=0.00, outliers=0, entropy=9.97 |
| ip_address | string | 1000 | 0 | 0 | 1000 | min_len=8, max_len=15, avg_len=13.29, empty=0, date_like=0, email_like=0, ip_like=1000, url_like=0, json_like=0 |
| last_name | string | 1000 | 0 | 0 | 247 | min_len=3, max_len=10, avg_len=6.09, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| registration_dttm | string | 1000 | 0 | 0 | 997 | min_len=20, max_len=20, avg_len=20.00, empty=0, date_like=1000, email_like=0, ip_like=0, url_like=0, json_like=0 |
| salary | number | 933 | 67 | 0 | 933 | min=12380.49, max=286592.99, mean=148911.965, median=146980.490, p95=274957.588, dup_ratio=0.00, outliers=0, entropy=9.87 |
| title | string | 1000 | 0 | 0 | 181 | min_len=0, max_len=36, avg_len=14.63, empty=198, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |

## Numeric Column Pairs

| Left | Right | Paired Rows | Pearson | Covariance | Equal Scalars |
| --- | --- | ---: | ---: | ---: | ---: |
| cc | id | 709 | 0.0301 | 12806315926179418112.0000 | 0 |
| cc | salary | 658 | 0.0088 | 1012593049829577719808.0000 | 0 |
| id | salary | 933 | 0.0007 | 15367.5204 | 0 |

