# Synthetic Generator Evaluation

This document compares the Rust diffusion path and SMOTE on the local test datasets.

Priority order used in this evaluation:

- privacy first
- correlation preservation second
- simple distribution summaries third

Metrics used:

- DCR median and DCR p5: nearest-neighbor distance from synthetic rows to original rows over common numeric columns
- exact replay ratio: exact full-row matches against the original dataset
- exact numeric replay ratio: exact matches on numeric columns only
- mean abs Pearson delta: average absolute Pearson correlation drift over numeric column pairs
- max abs Pearson delta: largest Pearson correlation drift over numeric column pairs

| Dataset | Rows | Target | Diffusion Privacy | Diffusion Corr | SMOTE Privacy | SMOTE Corr | Notes |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| iris.csv | 150 | species | DCR median 0.5887, replay 0.0000, numeric replay 0.0000 | mean 0.1199, max 0.2111 | DCR median 0.8070, replay 0.4733, numeric replay 0.4733 | mean 0.0329, max 0.0716 |  |
| cars.json | 406 | Origin | DCR median 1.0824, replay 0.0000, numeric replay 0.0000 | mean 0.4717, max 0.9503 | DCR median 0.6290, replay 0.4754, numeric replay 0.4754 | mean 0.0751, max 0.1672 |  |
| news_headlines.jsonl | 200 |  | n/a | n/a | n/a | n/a | Diffusion not evaluated: dataset has no fully numeric columns. SMOTE not evaluated: no suitable low-cardinality label column. |
| userdata1.avro | 1000 | gender | DCR median 0.0599, replay 0.0000, numeric replay 0.0000 | mean 0.0646, max 0.0983 | DCR median 0.0616, replay 0.5010, numeric replay 0.5010 | mean 0.0233, max 0.0351 |  |
| userdata1.parquet | 1000 | gender | DCR median 0.2006, replay 0.0000, numeric replay 0.0000 | mean 0.0188, max 0.0394 | DCR median 0.1514, replay 0.5010, numeric replay 0.5010 | mean 0.0336, max 0.0643 |  |

## iris.csv

- Source: `datasets/iris.csv`
- Original rows: `150`
- Target column: `species`
- Numeric columns: `petal_length, petal_width, sepal_length, sepal_width`

### Diffusion

- Training MSE: `0.6093`
- DCR median: `0.5887`
- DCR p5: `0.2299`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Mean absolute Pearson delta: `0.1199`
- Max absolute Pearson delta: `0.2111`
- Top drift pairs:
  - `petal_width/sepal_width` delta `0.2111`
  - `sepal_length/sepal_width` delta `0.1942`
  - `petal_length/sepal_width` delta `0.1735`

### SMOTE

- Minority label: `setosa`
- DCR median: `0.8070`
- DCR p5: `0.2408`
- Exact replay ratio: `0.4733`
- Exact numeric replay ratio: `0.4733`
- Mean absolute Pearson delta: `0.0329`
- Max absolute Pearson delta: `0.0716`
- Top drift pairs:
  - `petal_width/sepal_width` delta `0.0716`
  - `petal_length/sepal_width` delta `0.0578`
  - `sepal_length/sepal_width` delta `0.0344`

## cars.json

- Source: `datasets/cars.json`
- Original rows: `406`
- Target column: `Origin`
- Numeric columns: `Acceleration, Cylinders, Displacement, Horsepower, Miles_per_Gallon, Weight_in_lbs`

### Diffusion

- Training MSE: `0.5859`
- DCR median: `1.0824`
- DCR p5: `0.4627`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Mean absolute Pearson delta: `0.4717`
- Max absolute Pearson delta: `0.9503`
- Top drift pairs:
  - `Displacement/Horsepower` delta `0.9503`
  - `Horsepower/Weight_in_lbs` delta `0.9471`
  - `Cylinders/Horsepower` delta `0.9069`

### SMOTE

- Minority label: `Europe`
- DCR median: `0.6290`
- DCR p5: `0.3897`
- Exact replay ratio: `0.4754`
- Exact numeric replay ratio: `0.4754`
- Mean absolute Pearson delta: `0.0751`
- Max absolute Pearson delta: `0.1672`
- Top drift pairs:
  - `Acceleration/Weight_in_lbs` delta `0.1672`
  - `Displacement/Miles_per_Gallon` delta `0.1127`
  - `Cylinders/Miles_per_Gallon` delta `0.1106`

## news_headlines.jsonl

- Source: `datasets/news_headlines.jsonl`
- Original rows: `200`
- Target column: ``
- Numeric columns: ``
- Note: Diffusion not evaluated: dataset has no fully numeric columns.
- Note: SMOTE not evaluated: no suitable low-cardinality label column.

## userdata1.avro

- Source: `datasets/userdata1.avro`
- Original rows: `1000`
- Target column: `gender`
- Numeric columns: `cc, id, salary`

### Diffusion

- Training MSE: `0.7935`
- DCR median: `0.0599`
- DCR p5: `0.0178`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Mean absolute Pearson delta: `0.0646`
- Max absolute Pearson delta: `0.0983`
- Top drift pairs:
  - `id/salary` delta `0.0983`
  - `cc/salary` delta `0.0706`
  - `cc/id` delta `0.0247`

### SMOTE

- Minority label: `Male`
- DCR median: `0.0616`
- DCR p5: `0.0169`
- Exact replay ratio: `0.5010`
- Exact numeric replay ratio: `0.5010`
- Mean absolute Pearson delta: `0.0233`
- Max absolute Pearson delta: `0.0351`
- Top drift pairs:
  - `cc/id` delta `0.0351`
  - `id/salary` delta `0.0329`
  - `cc/salary` delta `0.0020`

## userdata1.parquet

- Source: `datasets/userdata1.parquet`
- Original rows: `1000`
- Target column: `gender`
- Numeric columns: `id, registration_dttm, salary`

### Diffusion

- Training MSE: `0.7852`
- DCR median: `0.2006`
- DCR p5: `0.0866`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Mean absolute Pearson delta: `0.0188`
- Max absolute Pearson delta: `0.0394`
- Top drift pairs:
  - `id/salary` delta `0.0394`
  - `registration_dttm/salary` delta `0.0091`
  - `id/registration_dttm` delta `0.0078`

### SMOTE

- Minority label: `Male`
- DCR median: `0.1514`
- DCR p5: `0.0738`
- Exact replay ratio: `0.5010`
- Exact numeric replay ratio: `0.5010`
- Mean absolute Pearson delta: `0.0336`
- Max absolute Pearson delta: `0.0643`
- Top drift pairs:
  - `id/registration_dttm` delta `0.0643`
  - `registration_dttm/salary` delta `0.0274`
  - `id/salary` delta `0.0090`
