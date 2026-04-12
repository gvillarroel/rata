use anyhow::{Result, anyhow, bail};
use nalgebra::DMatrix;
use rand::{Rng, rngs::StdRng};
use serde_json::{Number as JsonNumber, Value as JsonValue};

use crate::Record;

pub enum FeatureSelection<'a> {
    ExplicitOrAuto(&'a [String]),
    Exact(&'a [String]),
}

pub struct NumericDatasetView {
    pub numeric: NumericMatrix,
    pub passthrough_columns: Vec<String>,
}

pub struct NumericMatrix {
    pub columns: Vec<String>,
    pub matrix: DMatrix<f64>,
    pub means: Vec<f64>,
    pub stddevs: Vec<f64>,
    pub mins: Vec<f64>,
    pub maxs: Vec<f64>,
}

pub fn prepare_numeric_dataset(
    records: &[Record],
    selection: &FeatureSelection<'_>,
) -> Result<NumericDatasetView> {
    if records.is_empty() {
        bail!("dataset is empty");
    }

    let numeric_columns = match selection {
        FeatureSelection::ExplicitOrAuto(columns) if !columns.is_empty() => {
            validate_numeric_columns(records, columns)?
        }
        FeatureSelection::ExplicitOrAuto(_) => autodetect_numeric_columns(records),
        FeatureSelection::Exact(columns) => validate_numeric_columns(records, columns)?,
    };

    let numeric_set = numeric_columns
        .iter()
        .cloned()
        .collect::<std::collections::BTreeSet<_>>();
    let passthrough_columns = collect_column_names(records)
        .into_iter()
        .filter(|name| !numeric_set.contains(name))
        .collect::<Vec<_>>();

    let row_count = records.len();
    let col_count = numeric_columns.len();
    let mut raw = DMatrix::zeros(row_count, col_count);
    let mut mins = vec![f64::INFINITY; col_count];
    let mut maxs = vec![f64::NEG_INFINITY; col_count];
    let mut means = vec![0.0; col_count];

    for row_index in 0..row_count {
        let record = &records[row_index];
        for col_index in 0..col_count {
            let name = &numeric_columns[col_index];
            let value = value_as_f64(
                record
                    .get(name)
                    .ok_or_else(|| anyhow!("column `{name}` not found in every row"))?,
            )
            .ok_or_else(|| anyhow!("column `{name}` must be numeric"))?;
            raw[(row_index, col_index)] = value;
            mins[col_index] = mins[col_index].min(value);
            maxs[col_index] = maxs[col_index].max(value);
            means[col_index] += value;
        }
    }

    for mean in &mut means {
        *mean /= row_count as f64;
    }

    let mut stddevs = vec![0.0; col_count];
    for row_index in 0..row_count {
        for col_index in 0..col_count {
            let delta = raw[(row_index, col_index)] - means[col_index];
            stddevs[col_index] += delta * delta;
        }
    }
    for stddev in &mut stddevs {
        *stddev = (*stddev / row_count as f64).sqrt();
        if *stddev == 0.0 {
            *stddev = 1.0;
        }
    }

    let standardized = DMatrix::from_fn(row_count, col_count, |row, col| {
        (raw[(row, col)] - means[col]) / stddevs[col]
    });

    Ok(NumericDatasetView {
        numeric: NumericMatrix {
            columns: numeric_columns,
            matrix: standardized,
            means,
            stddevs,
            mins,
            maxs,
        },
        passthrough_columns,
    })
}

pub fn build_output_records(
    reference_records: &[Record],
    reference_view: &NumericDatasetView,
    generated_numeric: &DMatrix<f64>,
    passthrough_columns: &[String],
    rng: &mut StdRng,
) -> Result<Vec<Record>> {
    let mut output = Vec::with_capacity(generated_numeric.nrows());
    for row_index in 0..generated_numeric.nrows() {
        let base = &reference_records[rng.random_range(0..reference_records.len())];
        let mut record = Record::new();

        for passthrough in passthrough_columns {
            if let Some(value) = base.get(passthrough) {
                record.insert(passthrough.clone(), value.clone());
            }
        }

        for col_index in 0..reference_view.numeric.columns.len() {
            let name = &reference_view.numeric.columns[col_index];
            let value = generated_numeric[(row_index, col_index)];
            record.insert(
                name.clone(),
                JsonValue::Number(
                    JsonNumber::from_f64(value)
                        .ok_or_else(|| anyhow!("failed to encode generated value for `{name}`"))?,
                ),
            );
        }

        output.push(record);
    }

    Ok(output)
}

fn autodetect_numeric_columns(records: &[Record]) -> Vec<String> {
    collect_column_names(records)
        .into_iter()
        .filter(|column| {
            records
                .iter()
                .all(|record| record.get(column).and_then(value_as_f64).is_some())
        })
        .collect()
}

fn validate_numeric_columns(records: &[Record], columns: &[String]) -> Result<Vec<String>> {
    for column in columns {
        for record in records {
            let value = record
                .get(column)
                .ok_or_else(|| anyhow!("column `{column}` not found in every row"))?;
            if value_as_f64(value).is_none() {
                bail!("column `{column}` must be fully numeric for diffusion training");
            }
        }
    }
    Ok(columns.to_vec())
}

fn collect_column_names(records: &[Record]) -> Vec<String> {
    let mut names = std::collections::BTreeSet::new();
    for record in records {
        for key in record.keys() {
            names.insert(key.clone());
        }
    }
    names.into_iter().collect()
}

fn value_as_f64(value: &JsonValue) -> Option<f64> {
    match value {
        JsonValue::Number(number) => number.as_f64(),
        _ => None,
    }
}
