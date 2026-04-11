# Dataset Statistics Report

- Source: `C:\Users\villa\dev\rata\datasets\userdata1.parquet`
- Format: `parquet`
- Rows: `1000`
- Columns: `13`
- Column Pairs: `78`
- Nested Fields: `13`

## Structure Overview

- Dataset Types: null:74, number:2932, string:9994

| Column | Observed Types | Structure | Semantic Hints |
| --- | --- | --- | --- |
| birthdate | string:1000 | flat scalar | base64_like |
| cc | string:1000 | flat scalar | hex_like, base64_like |
| comments | null:6, string:994 | flat scalar | hex_like, base64_like |
| country | string:1000 | flat scalar | base64_like |
| email | string:1000 | flat scalar | email_like |
| first_name | string:1000 | flat scalar | base64_like |
| gender | string:1000 | flat scalar | - |
| id | number:1000 | flat scalar | monotonic_increasing |
| ip_address | string:1000 | flat scalar | ip_like |
| last_name | string:1000 | flat scalar | base64_like |
| registration_dttm | number:1000 | flat scalar | - |
| salary | null:68, number:932 | flat scalar | - |
| title | string:1000 | flat scalar | phone_like, base64_like |

## Nested Fields

| Path | Occurrences | Nulls | Observed Types |
| --- | ---: | ---: | --- |
| birthdate | 1000 | 0 | string:1000 |
| cc | 1000 | 0 | string:1000 |
| comments | 1000 | 6 | null:6, string:994 |
| country | 1000 | 0 | string:1000 |
| email | 1000 | 0 | string:1000 |
| first_name | 1000 | 0 | string:1000 |
| gender | 1000 | 0 | string:1000 |
| id | 1000 | 0 | number:1000 |
| ip_address | 1000 | 0 | string:1000 |
| last_name | 1000 | 0 | string:1000 |
| registration_dttm | 1000 | 0 | number:1000 |
| salary | 1000 | 68 | null:68, number:932 |
| title | 1000 | 0 | string:1000 |

| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| birthdate | string | 1000 | 0 | 0 | 788 | min_len=0, max_len=27, avg_len=7.22, empty=197, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| cc | string | 1000 | 0 | 0 | 710 | min_len=0, max_len=19, avg_len=11.41, empty=291, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| comments | string | 994 | 6 | 0 | 84 | min_len=0, max_len=217, avg_len=4.13, empty=811, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| country | string | 1000 | 0 | 0 | 120 | min_len=4, max_len=32, avg_len=7.51, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| email | string | 1000 | 0 | 0 | 985 | min_len=0, max_len=32, avg_len=20.63, empty=16, date_like=0, email_like=984, ip_like=0, url_like=0, json_like=0 |
| first_name | string | 1000 | 0 | 0 | 198 | min_len=0, max_len=11, avg_len=5.64, empty=16, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| gender | string | 1000 | 0 | 0 | 3 | min_len=0, max_len=6, avg_len=4.70, empty=67, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| id | number | 1000 | 0 | 0 | 1000 | min=1, max=1000, mean=500.500, median=500.500, p95=950.050, dup_ratio=0.00, outliers=0, entropy=9.97 |
| ip_address | string | 1000 | 0 | 0 | 1000 | min_len=8, max_len=15, avg_len=13.29, empty=0, date_like=0, email_like=0, ip_like=1000, url_like=0, json_like=0 |
| last_name | string | 1000 | 0 | 0 | 247 | min_len=3, max_len=10, avg_len=6.09, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |
| registration_dttm | number | 1000 | 0 | 0 | 995 | min=1454457660000, max=1454543995000, mean=1454499349191.000, median=1454497677500.000, p95=1454540353500.000, dup_ratio=0.01, outliers=0, entropy=9.96 |
| salary | number | 932 | 68 | 0 | 932 | min=12380.49, max=286592.99, mean=149005.357, median=147274.515, p95=274961.319, dup_ratio=0.00, outliers=0, entropy=9.86 |
| title | string | 1000 | 0 | 0 | 182 | min_len=0, max_len=36, avg_len=14.64, empty=197, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |

## Numeric Column Pairs

| Left | Right | Paired Rows | Pearson | Covariance | Equal Scalars |
| --- | --- | ---: | ---: | ---: | ---: |
| id | registration_dttm | 1000 | -0.0333 | -256724570.5000 | 0 |
| id | salary | 932 | 0.0010 | 24013.1754 | 0 |
| registration_dttm | salary | 932 | -0.0053 | -11279745370.0967 | 0 |

