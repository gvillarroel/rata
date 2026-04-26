# Synthetic Generator Evaluation

This document compares the Rust diffusion path, SMOTE, and DP noise on the local test datasets.

Priority order used in this evaluation:

- privacy first
- correlation preservation second
- simple distribution summaries third

Metrics used:

- DCR median and DCR p5: nearest-neighbor distance from synthetic rows to original rows over common numeric columns
- exact replay ratio: exact full-row matches against the original dataset
- exact numeric replay ratio: exact matches on numeric columns only
- exact non-numeric replay ratio: exact matches on common non-numeric scalar signatures
- mean abs Pearson delta: average absolute Pearson correlation drift over numeric column pairs
- max abs Pearson delta: largest Pearson correlation drift over numeric column pairs

| Dataset | Rows | Target | Diffusion Privacy | Diffusion Corr | SMOTE Privacy | SMOTE Corr | DP Noise Privacy | DP Noise Corr | Notes |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| iris.csv | 150 | species | DCR median 0.4928, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.1199, max 0.2111 | DCR median 0.0044, replay 0.4733, numeric replay 0.4733, non-numeric replay 1.0000 | mean 0.0329, max 0.0717 | DCR median 1.9383, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.5205, max 0.9287 |  |
| cars.json | 406 | Origin | DCR median 0.4334, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.4717, max 0.9503 | DCR median 0.0112, replay 0.4754, numeric replay 0.4754, non-numeric replay 1.0000 | mean 0.0751, max 0.1672 | DCR median 2.1378, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.6105, max 0.9234 |  |
| news_headlines.jsonl | 200 |  | n/a | n/a | n/a | n/a | n/a | n/a | Diffusion not evaluated: dataset has no fully numeric columns. DP noise not evaluated: dataset has no fully numeric columns. SMOTE not evaluated: no suitable low-cardinality label column. |
| userdata1.avro | 1000 | gender | DCR median 0.0009, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.0646, max 0.0983 | DCR median 0.0000, replay 0.5010, numeric replay 0.5010, non-numeric replay 1.0000 | mean 0.0233, max 0.0351 | DCR median 0.0000, replay 0.0020, numeric replay 0.0020, non-numeric replay 1.0000 | mean 0.0143, max 0.0325 |  |
| userdata1.parquet | 1000 | gender | DCR median 0.0494, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.0188, max 0.0394 | DCR median 0.0000, replay 0.5010, numeric replay 0.5010, non-numeric replay 1.0000 | mean 0.0336, max 0.0643 | DCR median 0.0578, replay 0.0000, numeric replay 0.0000, non-numeric replay 1.0000 | mean 0.0328, max 0.0662 |  |

## iris.csv

- Source: `datasets/iris.csv`
- Original rows: `150`
- Target column: `species`
- Numeric columns: `petal_length, petal_width, sepal_length, sepal_width`

### Diffusion

- Training MSE: `0.6093`
- DCR median: `0.4928`
- DCR p5: `0.2069`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `0`
- Rare numeric value columns: `4`
- Mean absolute Pearson delta: `0.1199`
- Max absolute Pearson delta: `0.2111`
- Top drift pairs:
  - `petal_width/sepal_width` delta `0.2111`
  - `sepal_length/sepal_width` delta `0.1942`
  - `petal_length/sepal_width` delta `0.1735`

### SMOTE

- Minority label: `setosa`
- DCR median: `0.0044`
- DCR p5: `0.0000`
- Exact replay ratio: `0.4733`
- Exact numeric replay ratio: `0.4733`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `0`
- Rare numeric value columns: `4`
- Mean absolute Pearson delta: `0.0329`
- Max absolute Pearson delta: `0.0717`
- Top drift pairs:
  - `petal_width/sepal_width` delta `0.0717`
  - `petal_length/sepal_width` delta `0.0577`
  - `sepal_length/sepal_width` delta `0.0344`

### DP Noise

- Epsilon: `1.0000`
- DCR median: `1.9383`
- DCR p5: `0.6857`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `0`
- Rare numeric value columns: `4`
- Mean absolute Pearson delta: `0.5205`
- Max absolute Pearson delta: `0.9287`
- Top drift pairs:
  - `petal_length/sepal_length` delta `0.9287`
  - `petal_length/petal_width` delta `0.7970`
  - `petal_width/sepal_length` delta `0.6640`

## cars.json

- Source: `datasets/cars.json`
- Original rows: `406`
- Target column: `Origin`
- Numeric columns: `Acceleration, Cylinders, Displacement, Horsepower, Miles_per_Gallon, Weight_in_lbs`

### Diffusion

- Training MSE: `0.5859`
- DCR median: `0.4334`
- DCR p5: `0.1773`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `1`
- Rare numeric value columns: `6`
- Mean absolute Pearson delta: `0.4717`
- Max absolute Pearson delta: `0.9503`
- Top drift pairs:
  - `Displacement/Horsepower` delta `0.9503`
  - `Horsepower/Weight_in_lbs` delta `0.9471`
  - `Cylinders/Horsepower` delta `0.9069`

### SMOTE

- Minority label: `Europe`
- DCR median: `0.0112`
- DCR p5: `0.0000`
- Exact replay ratio: `0.4754`
- Exact numeric replay ratio: `0.4754`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `1`
- Rare numeric value columns: `6`
- Mean absolute Pearson delta: `0.0751`
- Max absolute Pearson delta: `0.1672`
- Top drift pairs:
  - `Acceleration/Weight_in_lbs` delta `0.1672`
  - `Displacement/Miles_per_Gallon` delta `0.1127`
  - `Cylinders/Miles_per_Gallon` delta `0.1106`

### DP Noise

- Epsilon: `1.0000`
- DCR median: `2.1378`
- DCR p5: `0.6649`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `1`
- Rare numeric value columns: `5`
- Mean absolute Pearson delta: `0.6105`
- Max absolute Pearson delta: `0.9234`
- Top drift pairs:
  - `Cylinders/Weight_in_lbs` delta `0.9234`
  - `Cylinders/Displacement` delta `0.9040`
  - `Displacement/Weight_in_lbs` delta `0.8922`

## news_headlines.jsonl

- Source: `datasets/news_headlines.jsonl`
- Original rows: `200`
- Target column: ``
- Numeric columns: ``
- Note: Diffusion not evaluated: dataset has no fully numeric columns.
- Note: DP noise not evaluated: dataset has no fully numeric columns.
- Note: SMOTE not evaluated: no suitable low-cardinality label column.

## userdata1.avro

- Source: `datasets/userdata1.avro`
- Original rows: `1000`
- Target column: `gender`
- Numeric columns: `cc, id, salary`

### Diffusion

- Training MSE: `0.7935`
- DCR median: `0.0009`
- DCR p5: `0.0001`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0646`
- Max absolute Pearson delta: `0.0983`
- Top drift pairs:
  - `id/salary` delta `0.0983`
  - `cc/salary` delta `0.0706`
  - `cc/id` delta `0.0247`

### SMOTE

- Minority label: `Male`
- DCR median: `0.0000`
- DCR p5: `0.0000`
- Exact replay ratio: `0.5010`
- Exact numeric replay ratio: `0.5010`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0233`
- Max absolute Pearson delta: `0.0351`
- Top drift pairs:
  - `cc/id` delta `0.0351`
  - `id/salary` delta `0.0329`
  - `cc/salary` delta `0.0020`

### DP Noise

- Epsilon: `1.0000`
- DCR median: `0.0000`
- DCR p5: `0.0000`
- Exact replay ratio: `0.0020`
- Exact numeric replay ratio: `0.0020`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0143`
- Max absolute Pearson delta: `0.0325`
- Top drift pairs:
  - `id/salary` delta `0.0325`
  - `cc/id` delta `0.0103`
  - `cc/salary` delta `0.0000`

## userdata1.parquet

- Source: `datasets/userdata1.parquet`
- Original rows: `1000`
- Target column: `gender`
- Numeric columns: `id, registration_dttm, salary`

### Diffusion

- Training MSE: `0.7852`
- DCR median: `0.0494`
- DCR p5: `0.0143`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0188`
- Max absolute Pearson delta: `0.0394`
- Top drift pairs:
  - `id/salary` delta `0.0394`
  - `registration_dttm/salary` delta `0.0091`
  - `id/registration_dttm` delta `0.0078`

### SMOTE

- Minority label: `Male`
- DCR median: `0.0000`
- DCR p5: `0.0000`
- Exact replay ratio: `0.5010`
- Exact numeric replay ratio: `0.5010`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0336`
- Max absolute Pearson delta: `0.0643`
- Top drift pairs:
  - `id/registration_dttm` delta `0.0643`
  - `registration_dttm/salary` delta `0.0274`
  - `id/salary` delta `0.0090`

### DP Noise

- Epsilon: `1.0000`
- DCR median: `0.0578`
- DCR p5: `0.0235`
- Exact replay ratio: `0.0000`
- Exact numeric replay ratio: `0.0000`
- Exact non-numeric replay ratio: `1.0000`
- Rare non-numeric value columns: `9`
- Rare numeric value columns: `3`
- Mean absolute Pearson delta: `0.0328`
- Max absolute Pearson delta: `0.0662`
- Top drift pairs:
  - `id/registration_dttm` delta `0.0662`
  - `registration_dttm/salary` delta `0.0200`
  - `id/salary` delta `0.0122`
