# Dataset Statistics Report

- Source: `C:\Users\villa\dev\rata\datasets\news_headlines.jsonl`
- Format: `jsonl`
- Rows: `200`
- Columns: `2`
- Column Pairs: `1`
- Nested Fields: `3`

## Structure Overview

- Dataset Types: object:200, string:200

| Column | Observed Types | Structure | Semantic Hints |
| --- | --- | --- | --- |
| meta | object:200 | object rows=200, keys 1..1, avg_keys=1.00 | - |
| text | string:200 | flat scalar | - |

## Nested Fields

| Path | Occurrences | Nulls | Observed Types |
| --- | ---: | ---: | --- |
| meta | 200 | 0 | object:200 |
| meta.source | 200 | 0 | string:200 |
| text | 200 | 0 | string:200 |

| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| meta | object | 200 | 0 | 0 | 1 | object:200 |
| text | string | 200 | 0 | 0 | 178 | min_len=10, max_len=92, avg_len=47.92, empty=0, date_like=0, email_like=0, ip_like=0, url_like=0, json_like=0 |

