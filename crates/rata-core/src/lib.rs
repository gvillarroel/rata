use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::fmt::Write as _;
use std::fs::File;
use std::io::{BufRead, BufReader, BufWriter, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;

mod diffusion;

use anyhow::{Context, Result, anyhow, bail};
use apache_avro::{
    Codec as AvroCodec, Reader as AvroReader, Schema as AvroSchema, Writer as AvroWriter,
    types::Value as AvroValue,
};
use arrow_array::{ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray};
use arrow_schema::{DataType as ArrowDataType, Field as ArrowField, Schema as ArrowSchema};
use chrono::{DateTime, NaiveDate, Utc};
use parquet::arrow::ArrowWriter;
use parquet::file::reader::{FileReader, SerializedFileReader};
use parquet::record::{Field as ParquetField, Row as ParquetRow};
use rand::{Rng, SeedableRng, rngs::StdRng};
use serde::Serialize;
use serde_json::{Map as JsonMap, Number as JsonNumber, Value as JsonValue};

pub use diffusion::{
    DiffusionGenerateOptions, DiffusionGenerateReport, DiffusionTrainOptions, DiffusionTrainReport,
    generate_from_diffusion_model, train_diffusion_model,
};

pub type Record = JsonMap<String, JsonValue>;

const DEFAULT_RARE_VALUE_ALERT_THRESHOLD: usize = 5;
const MAX_RARE_VALUE_ALERTS: usize = 10;
const MAX_RARE_VALUE_EXAMPLES: usize = 5;

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DatasetFormat {
    Csv,
    Json,
    Jsonl,
    Parquet,
    Avro,
}

impl DatasetFormat {
    pub fn detect(path: &Path) -> Result<Self> {
        let extension = path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.to_ascii_lowercase())
            .ok_or_else(|| anyhow!("cannot detect dataset format for {}", path.display()))?;

        match extension.as_str() {
            "csv" => Ok(Self::Csv),
            "json" => Ok(Self::Json),
            "jsonl" | "ndjson" => Ok(Self::Jsonl),
            "parquet" => Ok(Self::Parquet),
            "avro" => Ok(Self::Avro),
            _ => bail!("unsupported dataset format: {}", extension),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DatasetStats {
    pub source_path: PathBuf,
    pub format: DatasetFormat,
    pub row_count: usize,
    pub column_count: usize,
    pub structure: StructureReport,
    pub columns: Vec<ColumnStats>,
    pub column_pairs: Vec<ColumnPairStats>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TransformReport {
    pub source_path: PathBuf,
    pub source_format: DatasetFormat,
    pub output_path: PathBuf,
    pub output_format: DatasetFormat,
    pub row_count: usize,
    pub column_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct DatasetPreview {
    pub source_path: PathBuf,
    pub format: DatasetFormat,
    pub total_row_count: usize,
    pub returned_row_count: usize,
    pub column_count: usize,
    pub columns: Vec<String>,
    pub rows: Vec<Record>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SmoteReport {
    pub source_path: PathBuf,
    pub source_format: DatasetFormat,
    pub output_path: PathBuf,
    pub output_format: DatasetFormat,
    pub target_column: String,
    pub minority_label: String,
    pub feature_columns: Vec<String>,
    pub original_row_count: usize,
    pub synthetic_row_count: usize,
    pub output_row_count: usize,
    pub k: usize,
    pub seed: Option<u64>,
    pub stats_diff: StatsDiffReport,
    pub evaluation: GenerationEvaluationReport,
}

#[derive(Debug, Clone, Serialize)]
pub struct DpNoiseReport {
    pub source_path: PathBuf,
    pub source_format: DatasetFormat,
    pub output_path: PathBuf,
    pub output_format: DatasetFormat,
    pub epsilon: f64,
    pub row_count: usize,
    pub noisy_columns: Vec<String>,
    pub seed: Option<u64>,
    pub stats_diff: StatsDiffReport,
    pub evaluation: GenerationEvaluationReport,
}

#[derive(Debug, Clone, Serialize)]
pub struct GenerationEvaluationReport {
    pub reference_population: String,
    pub reference_row_count: usize,
    pub synthetic_row_count: usize,
    pub feature_columns: Vec<String>,
    pub quality: SyntheticDataQualityReport,
    pub privacy: SyntheticDataPrivacyReport,
    pub references: Vec<EvaluationReference>,
    pub caveats: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SyntheticDataQualityReport {
    pub propensity_mse: f64,
    pub propensity_classifier_accuracy: f64,
    pub propensity_classifier_balanced_accuracy: f64,
    pub propensity_classifier_auc: f64,
    pub mean_univariate_ks_distance: f64,
    pub max_univariate_ks_distance: f64,
    pub feature_correlation_drift: CorrelationDriftSummary,
}

#[derive(Debug, Clone, Serialize)]
pub struct CorrelationDriftSummary {
    pub pair_count: usize,
    pub mean_absolute_pearson_delta: f64,
    pub max_absolute_pearson_delta: f64,
    pub mean_absolute_spearman_delta: f64,
    pub max_absolute_spearman_delta: f64,
    pub top_drift_pairs: Vec<CorrelationDriftPair>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CorrelationDriftPair {
    pub left: String,
    pub right: String,
    pub pearson_delta: f64,
    pub spearman_delta: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct SyntheticDataPrivacyReport {
    pub exact_row_match_count: usize,
    pub exact_row_match_ratio: f64,
    pub exact_feature_match_count: usize,
    pub exact_feature_match_ratio: f64,
    pub distance_to_closest_record: DistanceSummary,
    pub nearest_neighbor_distance_ratio: DistanceSummary,
    pub real_to_real_distance_baseline: DistanceSummary,
    pub synthetic_below_real_dcr_p5_count: usize,
    pub synthetic_below_real_dcr_median_count: usize,
    pub rare_value_alerts: RareValueAlertSummary,
}

#[derive(Debug, Clone, Serialize)]
pub struct DistanceSummary {
    pub count: usize,
    pub min: f64,
    pub p5: f64,
    pub median: f64,
    pub mean: f64,
    pub p95: f64,
    pub max: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct RareValueAlertSummary {
    pub threshold: usize,
    pub reviewed_columns: usize,
    pub columns_with_alerts: usize,
    pub alerts: Vec<RareValueAlert>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RareValueAlert {
    pub column: String,
    pub reference_distinct_value_count: usize,
    pub synthetic_distinct_value_count: usize,
    pub reference_unique_value_count: usize,
    pub synthetic_unique_value_count: usize,
    pub reference_rare_value_count: usize,
    pub synthetic_rare_value_count: usize,
    pub overlapping_unique_value_count: usize,
    pub overlapping_rare_value_count: usize,
    pub overlapping_unique_examples: Vec<String>,
    pub overlapping_rare_examples: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct EvaluationReference {
    pub metric: String,
    pub citation: String,
    pub url: String,
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct StatsDiffReport {
    pub original_row_count: usize,
    pub generated_row_count: usize,
    pub row_count_delta: isize,
    pub original_column_count: usize,
    pub generated_column_count: usize,
    pub column_count_delta: isize,
    pub columns: Vec<ColumnStatsDiff>,
    pub column_pairs: Vec<ColumnPairStatsDiff>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnStatsDiff {
    pub name: String,
    pub dominant_type_before: String,
    pub dominant_type_after: String,
    pub non_null_delta: isize,
    pub null_delta: isize,
    pub missing_delta: isize,
    pub distinct_delta: isize,
    pub mode_count_delta: isize,
    pub top_values_before: Vec<ValueFrequency>,
    pub top_values_after: Vec<ValueFrequency>,
    pub numeric_summary: Option<NumericSummaryDiff>,
    pub string_summary: Option<StringSummaryDiff>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NumericSummaryDiff {
    pub min_delta: f64,
    pub max_delta: f64,
    pub mean_delta: f64,
    pub median_delta: f64,
    pub stddev_delta: f64,
    pub sum_delta: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StringSummaryDiff {
    pub average_length_delta: f64,
    pub median_length_delta: f64,
    pub empty_count_delta: isize,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnPairStatsDiff {
    pub left: String,
    pub right: String,
    pub paired_non_null_delta: isize,
    pub overlap_ratio_delta: f64,
    pub equal_scalar_ratio_delta: f64,
    pub numeric_relationship: Option<NumericPairSummaryDiff>,
    pub categorical_relationship: Option<CategoricalPairSummaryDiff>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NumericPairSummaryDiff {
    pub covariance_delta: f64,
    pub pearson_correlation_delta: f64,
    pub spearman_correlation_delta: f64,
    pub slope_delta: f64,
    pub intercept_delta: f64,
    pub r_squared_delta: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct CategoricalPairSummaryDiff {
    pub mutual_information_delta: f64,
    pub normalized_mutual_information_delta: f64,
    pub chi_square_delta: f64,
    pub cramers_v_delta: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct InferredSchema {
    pub name: String,
    pub format: DatasetFormat,
    pub root: SchemaNode,
}

#[derive(Debug, Clone, Serialize)]
pub struct SchemaNode {
    pub kinds: BTreeMap<String, usize>,
    pub nullable: bool,
    pub semantic_hints: Vec<String>,
    pub object: Option<ObjectSchema>,
    pub array: Option<ArraySchema>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ObjectSchema {
    pub fields: Vec<SchemaField>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SchemaField {
    pub name: String,
    pub required: bool,
    pub schema: SchemaNode,
}

#[derive(Debug, Clone, Serialize)]
pub struct ArraySchema {
    pub item: Box<SchemaNode>,
}

#[derive(Debug, Clone, Serialize)]
pub struct StructureReport {
    pub dataset_type_counts: BTreeMap<String, usize>,
    pub nested_field_count: usize,
    pub nested_fields: Vec<NestedFieldStats>,
    pub columns: Vec<ColumnStructure>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnStructure {
    pub name: String,
    pub observed_types: BTreeMap<String, usize>,
    pub array_summary: Option<ArrayStructureSummary>,
    pub object_summary: Option<ObjectStructureSummary>,
    pub semantic_hints: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ArrayStructureSummary {
    pub row_count_with_arrays: usize,
    pub min_length: usize,
    pub max_length: usize,
    pub average_length: f64,
    pub element_type_counts: BTreeMap<String, usize>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ObjectStructureSummary {
    pub row_count_with_objects: usize,
    pub key_count_min: usize,
    pub key_count_max: usize,
    pub average_key_count: f64,
    pub top_keys: Vec<ValueFrequency>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NestedFieldStats {
    pub path: String,
    pub occurrence_count: usize,
    pub null_count: usize,
    pub observed_types: BTreeMap<String, usize>,
}

#[derive(Debug, Default)]
struct NestedAccumulator {
    occurrence_count: usize,
    null_count: usize,
    observed_types: BTreeMap<ValueType, usize>,
}

#[derive(Debug, Default, Clone)]
struct SchemaState {
    kinds: BTreeMap<ValueType, usize>,
    null_count: usize,
    object: Option<ObjectSchemaState>,
    array: Option<Box<SchemaState>>,
    string_semantics: BTreeSet<String>,
}

#[derive(Debug, Default, Clone)]
struct ObjectSchemaState {
    field_occurrences: HashMap<String, usize>,
    fields: BTreeMap<String, SchemaState>,
    sample_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnStats {
    pub name: String,
    pub dominant_type: ValueType,
    pub non_null_count: usize,
    pub null_count: usize,
    pub missing_count: usize,
    pub completeness_ratio: f64,
    pub null_ratio: f64,
    pub distinct_count: usize,
    pub distinct_ratio: f64,
    pub uniqueness_ratio: f64,
    pub mode_count: usize,
    pub mode_ratio: f64,
    pub entropy: f64,
    pub value_type_counts: BTreeMap<String, usize>,
    pub top_values: Vec<ValueFrequency>,
    pub numeric_summary: Option<NumericSummary>,
    pub string_summary: Option<StringSummary>,
    pub boolean_summary: Option<BooleanSummary>,
    pub temporal_summary: Option<TemporalSummary>,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum ValueType {
    Null,
    Boolean,
    Number,
    String,
    Array,
    Object,
}

impl ValueType {
    fn label(self) -> &'static str {
        match self {
            Self::Null => "null",
            Self::Boolean => "boolean",
            Self::Number => "number",
            Self::String => "string",
            Self::Array => "array",
            Self::Object => "object",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ValueFrequency {
    pub value: String,
    pub count: usize,
    pub ratio: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct NumericSummary {
    pub count: usize,
    pub min: f64,
    pub max: f64,
    pub sum: f64,
    pub mean: f64,
    pub median: f64,
    pub variance: f64,
    pub stddev: f64,
    pub p25: f64,
    pub p50: f64,
    pub p75: f64,
    pub p95: f64,
    pub range: f64,
    pub iqr: f64,
    pub mad: f64,
    pub coefficient_of_variation: f64,
    pub zero_count: usize,
    pub positive_count: usize,
    pub negative_count: usize,
    pub integer_like_count: usize,
    pub duplicate_count: usize,
    pub duplicate_ratio: f64,
    pub outlier_count_tukey: usize,
    pub monotonic_increasing: bool,
    pub monotonic_decreasing: bool,
    pub is_constant: bool,
    pub skewness: f64,
    pub kurtosis_excess: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StringSummary {
    pub count: usize,
    pub min_length: usize,
    pub max_length: usize,
    pub average_length: f64,
    pub median_length: f64,
    pub empty_count: usize,
    pub whitespace_only_count: usize,
    pub average_word_count: f64,
    pub max_word_count: usize,
    pub date_like_count: usize,
    pub email_like_count: usize,
    pub ip_like_count: usize,
    pub uuid_like_count: usize,
    pub url_like_count: usize,
    pub phone_like_count: usize,
    pub json_like_count: usize,
    pub numeric_like_count: usize,
    pub boolean_like_count: usize,
    pub ascii_only_count: usize,
    pub hex_like_count: usize,
    pub base64_like_count: usize,
    pub mac_address_like_count: usize,
    pub zip_code_like_count: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct BooleanSummary {
    pub true_count: usize,
    pub false_count: usize,
    pub true_ratio: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct TemporalSummary {
    pub count: usize,
    pub min: String,
    pub max: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ColumnPairStats {
    pub left: String,
    pub right: String,
    pub paired_non_null_count: usize,
    pub overlap_ratio: f64,
    pub both_null_or_missing_count: usize,
    pub equal_scalar_count: usize,
    pub equal_scalar_ratio: f64,
    pub shared_distinct_scalar_count: usize,
    pub scalar_jaccard_index: f64,
    pub numeric_relationship: Option<NumericPairSummary>,
    pub categorical_relationship: Option<CategoricalPairSummary>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NumericPairSummary {
    pub covariance: f64,
    pub pearson_correlation: f64,
    pub spearman_correlation: f64,
    pub slope: f64,
    pub intercept: f64,
    pub r_squared: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct CategoricalPairSummary {
    pub distinct_pair_count: usize,
    pub top_combinations: Vec<ValueFrequency>,
    pub mutual_information: f64,
    pub normalized_mutual_information: f64,
    pub chi_square: f64,
    pub cramers_v: f64,
}

pub fn analyze_dataset(path: impl AsRef<Path>) -> Result<DatasetStats> {
    let path = path.as_ref();
    let format = DatasetFormat::detect(path)?;
    let records = load_records(path, format)?;
    Ok(compute_stats(path, format, &records))
}

pub fn analyze_schema(path: impl AsRef<Path>, name: Option<&str>) -> Result<InferredSchema> {
    let path = path.as_ref();
    let format = DatasetFormat::detect(path)?;
    let records = load_records(path, format)?;
    Ok(infer_schema(
        &records,
        format,
        name.unwrap_or_else(|| default_schema_name(path)),
    ))
}

pub fn transform_dataset(
    input_path: impl AsRef<Path>,
    output_path: impl AsRef<Path>,
    output_format: Option<DatasetFormat>,
) -> Result<TransformReport> {
    let input_path = input_path.as_ref();
    let output_path = output_path.as_ref();
    let source_format = DatasetFormat::detect(input_path)?;
    let target_format = output_format.unwrap_or(DatasetFormat::detect(output_path)?);
    let records = load_records(input_path, source_format)?;
    write_records(output_path, target_format, &records)?;

    Ok(TransformReport {
        source_path: input_path.to_path_buf(),
        source_format,
        output_path: output_path.to_path_buf(),
        output_format: target_format,
        row_count: records.len(),
        column_count: collect_column_names(&records).len(),
    })
}

pub fn preview_dataset(path: impl AsRef<Path>, row_limit: usize) -> Result<DatasetPreview> {
    let path = path.as_ref();
    let format = DatasetFormat::detect(path)?;
    let records = load_records(path, format)?;
    let total_row_count = records.len();
    let columns = collect_column_names(&records);
    let rows = records.into_iter().take(row_limit).collect::<Vec<_>>();

    Ok(DatasetPreview {
        source_path: path.to_path_buf(),
        format,
        total_row_count,
        returned_row_count: rows.len(),
        column_count: columns.len(),
        columns,
        rows,
    })
}

pub fn smote_dataset(
    input_path: impl AsRef<Path>,
    output_path: impl AsRef<Path>,
    output_format: Option<DatasetFormat>,
    target_column: &str,
    minority_label: Option<&str>,
    synthetic_samples: Option<usize>,
    target_rows: Option<usize>,
    k: usize,
    seed: Option<u64>,
    feature_columns: &[String],
) -> Result<SmoteReport> {
    if k == 0 {
        bail!("k must be greater than zero");
    }

    let input_path = input_path.as_ref();
    let output_path = output_path.as_ref();
    let source_format = DatasetFormat::detect(input_path)?;
    let target_format = output_format.unwrap_or(DatasetFormat::detect(output_path)?);
    let records = load_records(input_path, source_format)?;
    if let Some(target_rows) = target_rows {
        if target_rows == 0 {
            bail!("target_rows must be greater than zero");
        }
    }
    let synthetic_samples = synthetic_samples.unwrap_or(records.len());
    if synthetic_samples == 0 {
        bail!("synthetic sample count must be greater than zero");
    }
    let minority_value = match minority_label {
        Some(label) => label.to_string(),
        None => detect_minority_label(&records, target_column)
            .with_context(|| format!("failed to detect minority label for `{target_column}`"))?,
    };
    let minority_target_value =
        find_target_value_for_label(&records, target_column, &minority_value)?.ok_or_else(
            || anyhow!("minority label `{minority_value}` not found in `{target_column}`"),
        )?;

    let resolved_features = if feature_columns.is_empty() {
        detect_smote_feature_columns(&records, target_column)?
    } else {
        feature_columns.to_vec()
    };
    if resolved_features.is_empty() {
        bail!("smote requires at least one numeric feature column");
    }

    let minority_rows =
        collect_minority_rows(&records, target_column, &minority_value, &resolved_features)?;
    if minority_rows.len() < 2 {
        bail!("smote requires at least two minority rows with complete numeric features");
    }

    let effective_k = k.min(minority_rows.len().saturating_sub(1));
    if effective_k == 0 {
        bail!("smote requires at least one minority neighbor");
    }

    let mut augmented = records.clone();
    let mut synthetic_records = Vec::with_capacity(synthetic_samples);
    let mut rng = match seed {
        Some(seed) => SmoteRng::Seeded(StdRng::seed_from_u64(seed)),
        None => SmoteRng::Thread(rand::rng()),
    };

    for synthetic_index in 0..synthetic_samples {
        let seed_index = synthetic_index % minority_rows.len();
        let seed = &minority_rows[seed_index];
        let neighbor_indices = nearest_neighbor_indices(seed_index, &minority_rows, effective_k);
        if neighbor_indices.is_empty() {
            bail!("failed to find neighbors for smote generation");
        }
        let neighbor =
            &minority_rows[neighbor_indices[rng.random_range(0..neighbor_indices.len())]];
        let gap = rng.random::<f64>();

        let mut synthetic = seed.record.clone();
        synthetic.insert(target_column.to_string(), minority_target_value.clone());

        for feature in &resolved_features {
            let start = seed.features[feature];
            let end = neighbor.features[feature];
            let interpolated = start + gap * (end - start);
            synthetic.insert(
                feature.clone(),
                JsonValue::Number(JsonNumber::from_f64(interpolated).ok_or_else(|| {
                    anyhow!("failed to encode interpolated value for `{feature}`")
                })?),
            );
        }

        synthetic_records.push(synthetic.clone());
        augmented.push(synthetic);
    }

    let final_records = if let Some(target_rows) = target_rows {
        if target_rows > augmented.len() {
            bail!(
                "target_rows `{target_rows}` is greater than the available augmented row count `{}`",
                augmented.len()
            );
        }
        sample_records(&augmented, target_rows, &mut rng)
    } else {
        augmented.clone()
    };

    write_records(output_path, target_format, &final_records)?;
    let original_stats = compute_stats(input_path, source_format, &records);
    let generated_stats = compute_stats(output_path, target_format, &final_records);
    let minority_reference_records = minority_rows
        .iter()
        .map(|row| row.record.clone())
        .collect::<Vec<_>>();
    let evaluation = evaluate_generation_records(
        "minority_reference_vs_synthetic",
        &minority_reference_records,
        &synthetic_records,
        &resolved_features,
        smote_evaluation_caveats(),
    )?;

    Ok(SmoteReport {
        source_path: input_path.to_path_buf(),
        source_format,
        output_path: output_path.to_path_buf(),
        output_format: target_format,
        target_column: target_column.to_string(),
        minority_label: minority_value,
        feature_columns: resolved_features,
        original_row_count: records.len(),
        synthetic_row_count: synthetic_samples,
        output_row_count: final_records.len(),
        k: effective_k,
        seed,
        stats_diff: diff_dataset_stats(&original_stats, &generated_stats),
        evaluation,
    })
}

pub fn dp_noise_dataset(
    input_path: impl AsRef<Path>,
    output_path: impl AsRef<Path>,
    output_format: Option<DatasetFormat>,
    epsilon: f64,
    seed: Option<u64>,
    feature_columns: &[String],
) -> Result<DpNoiseReport> {
    if epsilon <= 0.0 {
        bail!("epsilon must be greater than zero");
    }

    let input_path = input_path.as_ref();
    let output_path = output_path.as_ref();
    let source_format = DatasetFormat::detect(input_path)?;
    let target_format = output_format.unwrap_or(DatasetFormat::detect(output_path)?);
    let records = load_records(input_path, source_format)?;
    if records.is_empty() {
        bail!("input dataset is empty");
    }

    let resolved_features = if feature_columns.is_empty() {
        detect_numeric_columns(&records)
    } else {
        feature_columns.to_vec()
    };
    if resolved_features.is_empty() {
        bail!("dp-noise requires at least one numeric column");
    }

    let bounds = compute_numeric_bounds(&records, &resolved_features)?;
    let mut rng = match seed {
        Some(seed) => SmoteRng::Seeded(StdRng::seed_from_u64(seed)),
        None => SmoteRng::Thread(rand::rng()),
    };
    let mut synthetic_records = Vec::with_capacity(records.len());

    for record in &records {
        let mut synthetic = record.clone();
        for feature in &resolved_features {
            let value = record
                .get(feature)
                .ok_or_else(|| anyhow!("numeric column `{feature}` not found in every row"))?;
            let numeric = value_as_f64(value)
                .ok_or_else(|| anyhow!("numeric column `{feature}` must be numeric"))?;
            let (min_value, max_value) = bounds[feature];
            let scale = ((max_value - min_value).abs()).max(1e-9) / epsilon;
            let noisy = (numeric + sample_laplace(&mut rng, scale)).clamp(min_value, max_value);
            let encoded = if value_as_i64_if_integral(value).is_some() {
                JsonValue::Number((noisy.round() as i64).into())
            } else {
                JsonValue::Number(
                    JsonNumber::from_f64(noisy)
                        .ok_or_else(|| anyhow!("failed to encode noisy value for `{feature}`"))?,
                )
            };
            synthetic.insert(feature.clone(), encoded);
        }
        synthetic_records.push(synthetic);
    }

    write_records(output_path, target_format, &synthetic_records)?;
    let original_stats = compute_stats(input_path, source_format, &records);
    let generated_stats = compute_stats(output_path, target_format, &synthetic_records);
    let evaluation = evaluate_generation_records(
        "full_dataset_vs_dp_noisy_dataset",
        &records,
        &synthetic_records,
        &resolved_features,
        dp_noise_evaluation_caveats(epsilon),
    )?;

    Ok(DpNoiseReport {
        source_path: input_path.to_path_buf(),
        source_format,
        output_path: output_path.to_path_buf(),
        output_format: target_format,
        epsilon,
        row_count: synthetic_records.len(),
        noisy_columns: resolved_features,
        seed,
        stats_diff: diff_dataset_stats(&original_stats, &generated_stats),
        evaluation,
    })
}

pub fn render_schema_markdown(schema: &InferredSchema) -> String {
    let mut output = String::new();
    let _ = writeln!(&mut output, "# Dataset Schema");
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "- Name: `{}`", schema.name);
    let _ = writeln!(
        &mut output,
        "- Source Format: `{}`",
        format_label(schema.format)
    );
    let _ = writeln!(
        &mut output,
        "- Root Types: {}",
        schema
            .root
            .kinds
            .iter()
            .map(|(kind, count)| format!("{kind}:{count}"))
            .collect::<Vec<_>>()
            .join(", ")
    );
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "## Fields");
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "| Path | Required | Types | Semantic Hints |");
    let _ = writeln!(&mut output, "| --- | --- | --- | --- |");
    render_schema_markdown_rows("$", &schema.root, &mut output);
    output
}

pub fn render_schema_json(schema: &InferredSchema) -> Result<String> {
    Ok(serde_json::to_string_pretty(schema)?)
}

pub fn render_schema_json_schema(schema: &InferredSchema) -> Result<String> {
    let document = JsonValue::Object(JsonMap::from_iter([
        (
            "$schema".to_string(),
            JsonValue::String("https://json-schema.org/draft/2020-12/schema".to_string()),
        ),
        ("title".to_string(), JsonValue::String(schema.name.clone())),
        ("type".to_string(), JsonValue::String("object".to_string())),
        (
            "properties".to_string(),
            json_schema_properties(&schema.root),
        ),
        ("required".to_string(), json_schema_required(&schema.root)),
    ]));
    Ok(serde_json::to_string_pretty(&document)?)
}

pub fn render_schema_openapi(schema: &InferredSchema) -> Result<String> {
    let schema_value = openapi_schema_node(&schema.root);
    let document = JsonValue::Object(JsonMap::from_iter([
        (
            "openapi".to_string(),
            JsonValue::String("3.1.0".to_string()),
        ),
        (
            "info".to_string(),
            JsonValue::Object(JsonMap::from_iter([
                ("title".to_string(), JsonValue::String(schema.name.clone())),
                (
                    "version".to_string(),
                    JsonValue::String("1.0.0".to_string()),
                ),
            ])),
        ),
        (
            "components".to_string(),
            JsonValue::Object(JsonMap::from_iter([(
                "schemas".to_string(),
                JsonValue::Object(JsonMap::from_iter([(schema.name.clone(), schema_value)])),
            )])),
        ),
    ]));
    Ok(serde_json::to_string_pretty(&document)?)
}

pub fn render_schema_avro(schema: &InferredSchema) -> Result<String> {
    Ok(serde_json::to_string_pretty(&avro_schema_node(
        &schema.root,
        &schema.name,
    ))?)
}

pub fn render_schema_typescript(schema: &InferredSchema) -> String {
    format!(
        "export interface {} {}",
        to_type_name(&schema.name),
        typescript_object_body(schema.root.object.as_ref())
    )
}

pub fn render_schema_python(schema: &InferredSchema) -> String {
    format!(
        "from typing import Any, Dict, List, Optional, TypedDict\n\n\nclass {}(TypedDict, total=False):\n{}",
        to_type_name(&schema.name),
        python_object_body(schema.root.object.as_ref(), 1)
    )
}

pub fn render_markdown(stats: &DatasetStats) -> String {
    let mut output = String::new();
    let _ = writeln!(&mut output, "# Dataset Statistics Report");
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "- Source: `{}`", stats.source_path.display());
    let _ = writeln!(&mut output, "- Format: `{}`", format_label(stats.format));
    let _ = writeln!(&mut output, "- Rows: `{}`", stats.row_count);
    let _ = writeln!(&mut output, "- Columns: `{}`", stats.column_count);
    let _ = writeln!(
        &mut output,
        "- Column Pairs: `{}`",
        stats.column_pairs.len()
    );
    let _ = writeln!(
        &mut output,
        "- Nested Fields: `{}`",
        stats.structure.nested_field_count
    );
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "## Structure Overview");
    let _ = writeln!(&mut output);
    let _ = writeln!(
        &mut output,
        "- Dataset Types: {}",
        stats
            .structure
            .dataset_type_counts
            .iter()
            .map(|(kind, count)| format!("{kind}:{count}"))
            .collect::<Vec<_>>()
            .join(", ")
    );
    let _ = writeln!(&mut output);
    let _ = writeln!(
        &mut output,
        "| Column | Observed Types | Structure | Semantic Hints |"
    );
    let _ = writeln!(&mut output, "| --- | --- | --- | --- |");

    for column in &stats.structure.columns {
        let structure_note = structure_notes(column);
        let semantic_hints = if column.semantic_hints.is_empty() {
            "-".to_string()
        } else {
            column.semantic_hints.join(", ")
        };
        let observed_types = column
            .observed_types
            .iter()
            .map(|(kind, count)| format!("{kind}:{count}"))
            .collect::<Vec<_>>()
            .join(", ");
        let _ = writeln!(
            &mut output,
            "| {} | {} | {} | {} |",
            column.name, observed_types, structure_note, semantic_hints
        );
    }

    if !stats.structure.nested_fields.is_empty() {
        let _ = writeln!(&mut output);
        let _ = writeln!(&mut output, "## Nested Fields");
        let _ = writeln!(&mut output);
        let _ = writeln!(
            &mut output,
            "| Path | Occurrences | Nulls | Observed Types |"
        );
        let _ = writeln!(&mut output, "| --- | ---: | ---: | --- |");
        for field in stats.structure.nested_fields.iter().take(25) {
            let observed_types = field
                .observed_types
                .iter()
                .map(|(kind, count)| format!("{kind}:{count}"))
                .collect::<Vec<_>>()
                .join(", ");
            let _ = writeln!(
                &mut output,
                "| {} | {} | {} | {} |",
                field.path, field.occurrence_count, field.null_count, observed_types
            );
        }
    }

    let _ = writeln!(&mut output);
    let _ = writeln!(
        &mut output,
        "| Column | Dominant Type | Non-Null | Null | Missing | Distinct | Notes |"
    );
    let _ = writeln!(
        &mut output,
        "| --- | --- | ---: | ---: | ---: | ---: | --- |"
    );

    for column in &stats.columns {
        let notes = column_notes(column);
        let _ = writeln!(
            &mut output,
            "| {} | {} | {} | {} | {} | {} | {} |",
            column.name,
            column.dominant_type.label(),
            column.non_null_count,
            column.null_count,
            column.missing_count,
            column.distinct_count,
            notes
        );
    }

    let numeric_pairs = stats
        .column_pairs
        .iter()
        .filter(|pair| pair.numeric_relationship.is_some())
        .collect::<Vec<_>>();

    if !numeric_pairs.is_empty() {
        let _ = writeln!(&mut output);
        let _ = writeln!(&mut output, "## Numeric Column Pairs");
        let _ = writeln!(&mut output);
        let _ = writeln!(
            &mut output,
            "| Left | Right | Paired Rows | Pearson | Covariance | Equal Scalars |"
        );
        let _ = writeln!(&mut output, "| --- | --- | ---: | ---: | ---: | ---: |");

        for pair in numeric_pairs {
            if let Some(summary) = &pair.numeric_relationship {
                let _ = writeln!(
                    &mut output,
                    "| {} | {} | {} | {:.4} | {:.4} | {} |",
                    pair.left,
                    pair.right,
                    pair.paired_non_null_count,
                    summary.pearson_correlation,
                    summary.covariance,
                    pair.equal_scalar_count
                );
            }
        }
    }

    output
}

pub fn render_head_markdown(preview: &DatasetPreview) -> String {
    let mut output = String::new();
    let _ = writeln!(&mut output, "# Dataset Head");
    let _ = writeln!(&mut output);
    let _ = writeln!(&mut output, "- Source: `{}`", preview.source_path.display());
    let _ = writeln!(&mut output, "- Format: `{}`", format_label(preview.format));
    let _ = writeln!(&mut output, "- Total Rows: `{}`", preview.total_row_count);
    let _ = writeln!(
        &mut output,
        "- Returned Rows: `{}`",
        preview.returned_row_count
    );
    let _ = writeln!(&mut output, "- Columns: `{}`", preview.column_count);
    let _ = writeln!(&mut output);

    if preview.columns.is_empty() {
        let _ = writeln!(&mut output, "Dataset has no columns.");
        return output;
    }

    let _ = writeln!(&mut output, "| {} |", preview.columns.join(" | "));
    let _ = writeln!(
        &mut output,
        "| {} |",
        preview
            .columns
            .iter()
            .map(|_| "---")
            .collect::<Vec<_>>()
            .join(" | ")
    );

    for row in &preview.rows {
        let values = preview
            .columns
            .iter()
            .map(|column| {
                row.get(column)
                    .map(stringify_json_value)
                    .unwrap_or_default()
                    .replace('\n', "\\n")
                    .replace('|', "\\|")
            })
            .collect::<Vec<_>>();
        let _ = writeln!(&mut output, "| {} |", values.join(" | "));
    }

    output
}

pub fn load_records(path: &Path, format: DatasetFormat) -> Result<Vec<Record>> {
    match format {
        DatasetFormat::Csv => load_csv(path),
        DatasetFormat::Json => load_json(path),
        DatasetFormat::Jsonl => load_jsonl(path),
        DatasetFormat::Parquet => load_parquet(path),
        DatasetFormat::Avro => load_avro(path),
    }
}

pub fn write_records(path: &Path, format: DatasetFormat, records: &[Record]) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("failed to create output directory {}", parent.display()))?;
    }

    match format {
        DatasetFormat::Csv => write_csv(path, records),
        DatasetFormat::Json => write_json(path, records),
        DatasetFormat::Jsonl => write_jsonl(path, records),
        DatasetFormat::Parquet => write_parquet(path, records),
        DatasetFormat::Avro => write_avro(path, records),
    }
}

fn write_csv(path: &Path, records: &[Record]) -> Result<()> {
    let mut writer = csv::Writer::from_path(path)
        .with_context(|| format!("failed to create csv file {}", path.display()))?;
    let headers = collect_column_names(records);

    writer
        .write_record(headers.iter())
        .with_context(|| format!("failed to write csv headers to {}", path.display()))?;

    for record in records {
        let row = headers
            .iter()
            .map(|column| {
                record
                    .get(column)
                    .map(stringify_json_value)
                    .unwrap_or_default()
            })
            .collect::<Vec<_>>();
        writer
            .write_record(row)
            .with_context(|| format!("failed to write csv row to {}", path.display()))?;
    }

    writer
        .flush()
        .with_context(|| format!("failed to flush csv writer for {}", path.display()))?;
    Ok(())
}

fn write_json(path: &Path, records: &[Record]) -> Result<()> {
    let file = File::create(path)
        .with_context(|| format!("failed to create json file {}", path.display()))?;
    serde_json::to_writer_pretty(BufWriter::new(file), records)
        .with_context(|| format!("failed to write json dataset to {}", path.display()))?;
    Ok(())
}

fn write_jsonl(path: &Path, records: &[Record]) -> Result<()> {
    let file = File::create(path)
        .with_context(|| format!("failed to create jsonl file {}", path.display()))?;
    let mut writer = BufWriter::new(file);
    for record in records {
        serde_json::to_writer(&mut writer, record)
            .with_context(|| format!("failed to write jsonl row to {}", path.display()))?;
        writer
            .write_all(b"\n")
            .with_context(|| format!("failed to write jsonl newline to {}", path.display()))?;
    }
    writer
        .flush()
        .with_context(|| format!("failed to flush jsonl writer for {}", path.display()))?;
    Ok(())
}

fn write_parquet(path: &Path, records: &[Record]) -> Result<()> {
    let tabular = tabularize_records(records);
    let schema = Arc::new(ArrowSchema::new(
        tabular
            .columns
            .iter()
            .map(|column| ArrowField::new(&column.name, column.arrow_data_type(), true))
            .collect::<Vec<_>>(),
    ));
    let arrays = tabular
        .columns
        .iter()
        .map(build_arrow_array)
        .collect::<Vec<_>>();
    let batch = RecordBatch::try_new(schema.clone(), arrays)
        .with_context(|| format!("failed to build parquet batch for {}", path.display()))?;

    let file = File::create(path)
        .with_context(|| format!("failed to create parquet file {}", path.display()))?;
    let mut writer = ArrowWriter::try_new(file, schema, None)
        .with_context(|| format!("failed to create parquet writer for {}", path.display()))?;
    writer
        .write(&batch)
        .with_context(|| format!("failed to write parquet data to {}", path.display()))?;
    writer
        .close()
        .with_context(|| format!("failed to finalize parquet file {}", path.display()))?;
    Ok(())
}

fn write_avro(path: &Path, records: &[Record]) -> Result<()> {
    let tabular = tabularize_records(records);
    let schema_json = build_avro_schema_json(path, &tabular);
    let schema = AvroSchema::parse_str(&serde_json::to_string(&schema_json)?)
        .with_context(|| format!("failed to build avro schema for {}", path.display()))?;
    let file = File::create(path)
        .with_context(|| format!("failed to create avro file {}", path.display()))?;
    let mut writer = AvroWriter::with_codec(&schema, file, AvroCodec::Snappy);

    for row_index in 0..tabular.row_count {
        let mut values = Vec::with_capacity(tabular.columns.len());
        for column in &tabular.columns {
            values.push((
                avro_safe_name(&column.name),
                json_value_to_avro_union_value(column.value_at(row_index), column),
            ));
        }
        writer.append(AvroValue::Record(values)).with_context(|| {
            format!(
                "failed to append avro row {row_index} to {}",
                path.display()
            )
        })?;
    }

    writer
        .flush()
        .with_context(|| format!("failed to flush avro writer for {}", path.display()))?;
    Ok(())
}

fn load_csv(path: &Path) -> Result<Vec<Record>> {
    let mut reader = csv::Reader::from_path(path)
        .with_context(|| format!("failed to open csv file {}", path.display()))?;
    let headers = reader
        .headers()
        .with_context(|| format!("failed to read csv headers from {}", path.display()))?
        .clone();

    let mut records = Vec::new();
    for row in reader.records() {
        let row = row.with_context(|| format!("failed to read csv row from {}", path.display()))?;
        let mut record = Record::new();
        for (header, value) in headers.iter().zip(row.iter()) {
            record.insert(header.to_string(), parse_scalar_text(value));
        }
        records.push(record);
    }

    Ok(records)
}

fn load_json(path: &Path) -> Result<Vec<Record>> {
    let mut file =
        File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let mut content = String::new();
    file.read_to_string(&mut content)
        .with_context(|| format!("failed to read {}", path.display()))?;

    let value: JsonValue = serde_json::from_str(&content)
        .with_context(|| format!("invalid json in {}", path.display()))?;

    match value {
        JsonValue::Array(items) => items
            .into_iter()
            .map(json_value_to_record)
            .collect::<Result<Vec<_>>>(),
        JsonValue::Object(map) => Ok(vec![map]),
        _ => bail!("json dataset must be an object or an array of objects"),
    }
}

fn load_jsonl(path: &Path) -> Result<Vec<Record>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = BufReader::new(file);
    let mut records = Vec::new();

    for (line_index, line) in reader.lines().enumerate() {
        let line = line.with_context(|| {
            format!(
                "failed to read line {} from {}",
                line_index + 1,
                path.display()
            )
        })?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let value: JsonValue = serde_json::from_str(trimmed).with_context(|| {
            format!(
                "invalid jsonl record at line {} in {}",
                line_index + 1,
                path.display()
            )
        })?;
        records.push(json_value_to_record(value)?);
    }

    Ok(records)
}

fn load_parquet(path: &Path) -> Result<Vec<Record>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader = SerializedFileReader::new(file)
        .with_context(|| format!("failed to read parquet file {}", path.display()))?;
    let iter = reader
        .get_row_iter(None)
        .with_context(|| format!("failed to iterate parquet rows from {}", path.display()))?;

    let mut records = Vec::new();
    for row in iter {
        let row =
            row.with_context(|| format!("failed to decode parquet row from {}", path.display()))?;
        records.push(parquet_row_to_record(&row)?);
    }

    Ok(records)
}

fn load_avro(path: &Path) -> Result<Vec<Record>> {
    let file = File::open(path).with_context(|| format!("failed to open {}", path.display()))?;
    let reader =
        AvroReader::new(file).with_context(|| format!("failed to read avro {}", path.display()))?;
    let mut records = Vec::new();

    for value in reader {
        let value = value
            .with_context(|| format!("failed to decode avro value from {}", path.display()))?;
        records.push(avro_value_to_record(value)?);
    }

    Ok(records)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TabularColumnType {
    Boolean,
    Int64,
    Float64,
    String,
}

#[derive(Debug, Clone)]
struct TabularColumn {
    name: String,
    data_type: TabularColumnType,
    values: Vec<Option<JsonValue>>,
}

impl TabularColumn {
    fn arrow_data_type(&self) -> ArrowDataType {
        match self.data_type {
            TabularColumnType::Boolean => ArrowDataType::Boolean,
            TabularColumnType::Int64 => ArrowDataType::Int64,
            TabularColumnType::Float64 => ArrowDataType::Float64,
            TabularColumnType::String => ArrowDataType::Utf8,
        }
    }

    fn avro_type_name(&self) -> &'static str {
        match self.data_type {
            TabularColumnType::Boolean => "boolean",
            TabularColumnType::Int64 => "long",
            TabularColumnType::Float64 => "double",
            TabularColumnType::String => "string",
        }
    }

    fn value_at(&self, index: usize) -> Option<&JsonValue> {
        self.values.get(index).and_then(Option::as_ref)
    }
}

#[derive(Debug, Clone)]
struct TabularDataset {
    columns: Vec<TabularColumn>,
    row_count: usize,
}

#[derive(Debug, Clone)]
struct MinorityRow {
    record: Record,
    features: HashMap<String, f64>,
}

enum SmoteRng {
    Seeded(StdRng),
    Thread(rand::rngs::ThreadRng),
}

impl SmoteRng {
    fn random_range(&mut self, range: std::ops::Range<usize>) -> usize {
        match self {
            Self::Seeded(rng) => rng.random_range(range),
            Self::Thread(rng) => rng.random_range(range),
        }
    }

    fn random<T>(&mut self) -> T
    where
        rand::distr::StandardUniform: rand::distr::Distribution<T>,
    {
        match self {
            Self::Seeded(rng) => rng.random(),
            Self::Thread(rng) => rng.random(),
        }
    }
}

fn tabularize_records(records: &[Record]) -> TabularDataset {
    let columns = collect_column_names(records)
        .into_iter()
        .map(|name| {
            let values = records
                .iter()
                .map(|record| record.get(&name).cloned())
                .collect::<Vec<_>>();
            let data_type = infer_tabular_column_type(&values);
            TabularColumn {
                name,
                data_type,
                values,
            }
        })
        .collect::<Vec<_>>();

    TabularDataset {
        columns,
        row_count: records.len(),
    }
}

fn detect_minority_label(records: &[Record], target_column: &str) -> Result<String> {
    let mut counts: HashMap<String, usize> = HashMap::new();
    for record in records {
        let value = record
            .get(target_column)
            .ok_or_else(|| anyhow!("target column `{target_column}` not found in every row"))?;
        let label = scalar_value_label(value)
            .ok_or_else(|| anyhow!("target column `{target_column}` must contain scalar values"))?;
        *counts.entry(label).or_default() += 1;
    }

    counts
        .into_iter()
        .min_by(|(left_label, left_count), (right_label, right_count)| {
            left_count
                .cmp(right_count)
                .then_with(|| left_label.cmp(right_label))
        })
        .map(|(label, _)| label)
        .ok_or_else(|| anyhow!("target column `{target_column}` has no values"))
}

fn detect_smote_feature_columns(records: &[Record], target_column: &str) -> Result<Vec<String>> {
    let mut features = Vec::new();
    for column in collect_column_names(records) {
        if column == target_column {
            continue;
        }

        let mut saw_value = false;
        let mut all_numeric = true;
        for record in records {
            match record.get(&column) {
                None | Some(JsonValue::Null) => {
                    all_numeric = false;
                    break;
                }
                Some(value) => match value_as_f64(value) {
                    Some(_) => saw_value = true,
                    None => {
                        all_numeric = false;
                        break;
                    }
                },
            }
        }

        if saw_value && all_numeric {
            features.push(column);
        }
    }

    Ok(features)
}

fn find_target_value_for_label(
    records: &[Record],
    target_column: &str,
    label: &str,
) -> Result<Option<JsonValue>> {
    for record in records {
        let value = record
            .get(target_column)
            .ok_or_else(|| anyhow!("target column `{target_column}` not found in every row"))?;
        let candidate = scalar_value_label(value)
            .ok_or_else(|| anyhow!("target column `{target_column}` must contain scalar values"))?;
        if candidate == label {
            return Ok(Some(value.clone()));
        }
    }
    Ok(None)
}

fn collect_minority_rows(
    records: &[Record],
    target_column: &str,
    minority_label: &str,
    feature_columns: &[String],
) -> Result<Vec<MinorityRow>> {
    let mut minority_rows = Vec::new();

    for record in records {
        let target_value = record
            .get(target_column)
            .ok_or_else(|| anyhow!("target column `{target_column}` not found in every row"))?;
        let label = scalar_value_label(target_value)
            .ok_or_else(|| anyhow!("target column `{target_column}` must contain scalar values"))?;
        if label != minority_label {
            continue;
        }

        let mut features = HashMap::new();
        for feature in feature_columns {
            let value = record
                .get(feature)
                .ok_or_else(|| anyhow!("feature column `{feature}` not found in minority rows"))?;
            let numeric = value_as_f64(value)
                .ok_or_else(|| anyhow!("feature column `{feature}` must be numeric for SMOTE"))?;
            features.insert(feature.clone(), numeric);
        }

        minority_rows.push(MinorityRow {
            record: record.clone(),
            features,
        });
    }

    Ok(minority_rows)
}

fn nearest_neighbor_indices(seed_index: usize, rows: &[MinorityRow], k: usize) -> Vec<usize> {
    let seed = &rows[seed_index];
    let mut distances = rows
        .iter()
        .enumerate()
        .filter(|(index, _)| *index != seed_index)
        .map(|(index, row)| (index, euclidean_distance(&seed.features, &row.features)))
        .collect::<Vec<_>>();
    distances.sort_by(|(_, left), (_, right)| compare_f64(left, right));
    distances
        .into_iter()
        .take(k)
        .map(|(index, _)| index)
        .collect()
}

fn sample_records(records: &[Record], target_rows: usize, rng: &mut SmoteRng) -> Vec<Record> {
    let mut indices = (0..records.len()).collect::<Vec<_>>();
    for current in 0..target_rows.min(indices.len()) {
        let swap_index = rng.random_range(current..indices.len());
        indices.swap(current, swap_index);
    }
    indices
        .into_iter()
        .take(target_rows)
        .map(|index| records[index].clone())
        .collect()
}

fn euclidean_distance(left: &HashMap<String, f64>, right: &HashMap<String, f64>) -> f64 {
    left.iter()
        .map(|(feature, left_value)| {
            let right_value = right.get(feature).copied().unwrap_or(*left_value);
            let delta = *left_value - right_value;
            delta * delta
        })
        .sum::<f64>()
        .sqrt()
}

fn collect_column_names(records: &[Record]) -> Vec<String> {
    let mut names = BTreeSet::new();
    for record in records {
        for key in record.keys() {
            names.insert(key.clone());
        }
    }
    names.into_iter().collect()
}

fn infer_tabular_column_type(values: &[Option<JsonValue>]) -> TabularColumnType {
    let non_null = values
        .iter()
        .filter_map(|value| value.as_ref())
        .filter(|value| !value.is_null())
        .collect::<Vec<_>>();

    if non_null.is_empty() {
        return TabularColumnType::String;
    }

    if non_null.iter().all(|value| value.is_boolean()) {
        return TabularColumnType::Boolean;
    }

    if non_null
        .iter()
        .all(|value| json_value_to_i64(value).is_some())
    {
        return TabularColumnType::Int64;
    }

    if non_null.iter().all(|value| value.as_f64().is_some()) {
        return TabularColumnType::Float64;
    }

    TabularColumnType::String
}

fn build_arrow_array(column: &TabularColumn) -> ArrayRef {
    match column.data_type {
        TabularColumnType::Boolean => Arc::new(BooleanArray::from(
            column
                .values
                .iter()
                .map(|value| value.as_ref().and_then(JsonValue::as_bool))
                .collect::<Vec<_>>(),
        )),
        TabularColumnType::Int64 => Arc::new(Int64Array::from(
            column
                .values
                .iter()
                .map(|value| value.as_ref().and_then(json_value_to_i64))
                .collect::<Vec<_>>(),
        )),
        TabularColumnType::Float64 => Arc::new(Float64Array::from(
            column
                .values
                .iter()
                .map(|value| value.as_ref().and_then(JsonValue::as_f64))
                .collect::<Vec<_>>(),
        )),
        TabularColumnType::String => Arc::new(StringArray::from(
            column
                .values
                .iter()
                .map(|value| value.as_ref().map(stringify_json_value))
                .collect::<Vec<_>>(),
        )),
    }
}

fn build_avro_schema_json(path: &Path, tabular: &TabularDataset) -> JsonValue {
    JsonValue::Object(JsonMap::from_iter([
        ("type".to_string(), JsonValue::String("record".to_string())),
        (
            "name".to_string(),
            JsonValue::String(to_type_name(default_schema_name(path))),
        ),
        (
            "fields".to_string(),
            JsonValue::Array(
                tabular
                    .columns
                    .iter()
                    .map(|column| {
                        JsonValue::Object(JsonMap::from_iter([
                            (
                                "name".to_string(),
                                JsonValue::String(avro_safe_name(&column.name)),
                            ),
                            (
                                "type".to_string(),
                                JsonValue::Array(vec![
                                    JsonValue::String("null".to_string()),
                                    JsonValue::String(column.avro_type_name().to_string()),
                                ]),
                            ),
                            ("default".to_string(), JsonValue::Null),
                        ]))
                    })
                    .collect(),
            ),
        ),
    ]))
}

fn json_value_to_avro_union_value(value: Option<&JsonValue>, column: &TabularColumn) -> AvroValue {
    match value {
        None | Some(JsonValue::Null) => AvroValue::Union(0, Box::new(AvroValue::Null)),
        Some(value) => {
            let inner = match column.data_type {
                TabularColumnType::Boolean => value
                    .as_bool()
                    .map(AvroValue::Boolean)
                    .unwrap_or(AvroValue::Null),
                TabularColumnType::Int64 => json_value_to_i64(value)
                    .map(AvroValue::Long)
                    .unwrap_or(AvroValue::Null),
                TabularColumnType::Float64 => value
                    .as_f64()
                    .map(AvroValue::Double)
                    .unwrap_or(AvroValue::Null),
                TabularColumnType::String => AvroValue::String(stringify_json_value(value)),
            };

            if matches!(inner, AvroValue::Null) {
                AvroValue::Union(0, Box::new(AvroValue::Null))
            } else {
                AvroValue::Union(1, Box::new(inner))
            }
        }
    }
}

fn json_value_to_i64(value: &JsonValue) -> Option<i64> {
    value
        .as_i64()
        .or_else(|| value.as_u64().and_then(|number| i64::try_from(number).ok()))
}

fn stringify_json_value(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => String::new(),
        JsonValue::String(value) => value.clone(),
        JsonValue::Bool(value) => value.to_string(),
        JsonValue::Number(value) => value.to_string(),
        JsonValue::Array(_) | JsonValue::Object(_) => {
            serde_json::to_string(value).unwrap_or_else(|_| String::new())
        }
    }
}

fn avro_safe_name(name: &str) -> String {
    let mut output = String::new();
    for (index, ch) in name.chars().enumerate() {
        let valid = if index == 0 {
            ch.is_ascii_alphabetic() || ch == '_'
        } else {
            ch.is_ascii_alphanumeric() || ch == '_'
        };
        output.push(if valid { ch } else { '_' });
    }

    if output.is_empty() {
        "_field".to_string()
    } else if output.chars().next().is_some_and(|ch| ch.is_ascii_digit()) {
        format!("_{output}")
    } else {
        output
    }
}

fn compute_stats(path: &Path, format: DatasetFormat, records: &[Record]) -> DatasetStats {
    let column_names = collect_column_names(records);
    let columns = column_names
        .iter()
        .map(|name| compute_column_stats(name, records))
        .collect::<Vec<_>>();
    let structure = compute_structure_report(&column_names, records, &columns);
    let column_pairs = compute_column_pair_stats(&column_names, records);

    DatasetStats {
        source_path: path.to_path_buf(),
        format,
        row_count: records.len(),
        column_count: columns.len(),
        structure,
        columns,
        column_pairs,
    }
}

fn diff_dataset_stats(original: &DatasetStats, generated: &DatasetStats) -> StatsDiffReport {
    let mut original_columns = BTreeMap::new();
    for column in &original.columns {
        original_columns.insert(column.name.clone(), column);
    }

    let mut generated_columns = BTreeMap::new();
    for column in &generated.columns {
        generated_columns.insert(column.name.clone(), column);
    }

    let mut names = BTreeSet::new();
    names.extend(original_columns.keys().cloned());
    names.extend(generated_columns.keys().cloned());

    let columns = names
        .into_iter()
        .filter_map(|name| {
            let before = original_columns.get(&name)?;
            let after = generated_columns.get(&name)?;
            Some(ColumnStatsDiff {
                name,
                dominant_type_before: before.dominant_type.label().to_string(),
                dominant_type_after: after.dominant_type.label().to_string(),
                non_null_delta: after.non_null_count as isize - before.non_null_count as isize,
                null_delta: after.null_count as isize - before.null_count as isize,
                missing_delta: after.missing_count as isize - before.missing_count as isize,
                distinct_delta: after.distinct_count as isize - before.distinct_count as isize,
                mode_count_delta: after.mode_count as isize - before.mode_count as isize,
                top_values_before: before.top_values.clone(),
                top_values_after: after.top_values.clone(),
                numeric_summary: match (&before.numeric_summary, &after.numeric_summary) {
                    (Some(before), Some(after)) => Some(NumericSummaryDiff {
                        min_delta: after.min - before.min,
                        max_delta: after.max - before.max,
                        mean_delta: after.mean - before.mean,
                        median_delta: after.median - before.median,
                        stddev_delta: after.stddev - before.stddev,
                        sum_delta: after.sum - before.sum,
                    }),
                    _ => None,
                },
                string_summary: match (&before.string_summary, &after.string_summary) {
                    (Some(before), Some(after)) => Some(StringSummaryDiff {
                        average_length_delta: after.average_length - before.average_length,
                        median_length_delta: after.median_length - before.median_length,
                        empty_count_delta: after.empty_count as isize - before.empty_count as isize,
                    }),
                    _ => None,
                },
            })
        })
        .collect::<Vec<_>>();

    let mut original_pairs = BTreeMap::new();
    for pair in &original.column_pairs {
        original_pairs.insert((pair.left.clone(), pair.right.clone()), pair);
    }

    let mut generated_pairs = BTreeMap::new();
    for pair in &generated.column_pairs {
        generated_pairs.insert((pair.left.clone(), pair.right.clone()), pair);
    }

    let mut pair_names = BTreeSet::new();
    pair_names.extend(original_pairs.keys().cloned());
    pair_names.extend(generated_pairs.keys().cloned());

    let column_pairs = pair_names
        .into_iter()
        .filter_map(|(left, right)| {
            let before = original_pairs.get(&(left.clone(), right.clone()))?;
            let after = generated_pairs.get(&(left.clone(), right.clone()))?;
            Some(ColumnPairStatsDiff {
                left,
                right,
                paired_non_null_delta: after.paired_non_null_count as isize
                    - before.paired_non_null_count as isize,
                overlap_ratio_delta: after.overlap_ratio - before.overlap_ratio,
                equal_scalar_ratio_delta: after.equal_scalar_ratio - before.equal_scalar_ratio,
                numeric_relationship: match (
                    &before.numeric_relationship,
                    &after.numeric_relationship,
                ) {
                    (Some(before), Some(after)) => Some(NumericPairSummaryDiff {
                        covariance_delta: after.covariance - before.covariance,
                        pearson_correlation_delta: after.pearson_correlation
                            - before.pearson_correlation,
                        spearman_correlation_delta: after.spearman_correlation
                            - before.spearman_correlation,
                        slope_delta: after.slope - before.slope,
                        intercept_delta: after.intercept - before.intercept,
                        r_squared_delta: after.r_squared - before.r_squared,
                    }),
                    _ => None,
                },
                categorical_relationship: match (
                    &before.categorical_relationship,
                    &after.categorical_relationship,
                ) {
                    (Some(before), Some(after)) => Some(CategoricalPairSummaryDiff {
                        mutual_information_delta: after.mutual_information
                            - before.mutual_information,
                        normalized_mutual_information_delta: after.normalized_mutual_information
                            - before.normalized_mutual_information,
                        chi_square_delta: after.chi_square - before.chi_square,
                        cramers_v_delta: after.cramers_v - before.cramers_v,
                    }),
                    _ => None,
                },
            })
        })
        .collect::<Vec<_>>();

    StatsDiffReport {
        original_row_count: original.row_count,
        generated_row_count: generated.row_count,
        row_count_delta: generated.row_count as isize - original.row_count as isize,
        original_column_count: original.column_count,
        generated_column_count: generated.column_count,
        column_count_delta: generated.column_count as isize - original.column_count as isize,
        columns,
        column_pairs,
    }
}

fn evaluate_generation_records(
    reference_population: &str,
    reference_records: &[Record],
    synthetic_records: &[Record],
    feature_columns: &[String],
    caveats: Vec<String>,
) -> Result<GenerationEvaluationReport> {
    let real_feature_vectors =
        collect_feature_vectors_from_records(reference_records, feature_columns)?;
    let synthetic_feature_vectors =
        collect_feature_vectors_from_records(synthetic_records, feature_columns)?;
    let standardized =
        standardize_feature_spaces(&real_feature_vectors, &synthetic_feature_vectors);

    let propensity_scores =
        train_propensity_scores(&standardized.real_vectors, &standardized.synthetic_vectors);
    let propensity_labels = [
        vec![0.0; standardized.real_vectors.len()],
        vec![1.0; standardized.synthetic_vectors.len()],
    ]
    .concat();
    let synthetic_prior =
        standardized.synthetic_vectors.len() as f64 / propensity_labels.len().max(1) as f64;
    let propensity_mse = propensity_scores
        .iter()
        .map(|score| {
            let delta = score - synthetic_prior;
            delta * delta
        })
        .sum::<f64>()
        / propensity_scores.len().max(1) as f64;
    let propensity_predictions = propensity_scores
        .iter()
        .map(|score| if *score >= 0.5 { 1.0 } else { 0.0 })
        .collect::<Vec<_>>();
    let propensity_accuracy = propensity_predictions
        .iter()
        .zip(&propensity_labels)
        .filter(|(prediction, label)| (**prediction >= 0.5) == (**label >= 0.5))
        .count() as f64
        / propensity_predictions.len().max(1) as f64;
    let true_positive = propensity_predictions
        .iter()
        .zip(&propensity_labels)
        .filter(|(prediction, label)| **label >= 0.5 && **prediction >= 0.5)
        .count();
    let true_negative = propensity_predictions
        .iter()
        .zip(&propensity_labels)
        .filter(|(prediction, label)| **label < 0.5 && **prediction < 0.5)
        .count();
    let false_negative = propensity_predictions
        .iter()
        .zip(&propensity_labels)
        .filter(|(prediction, label)| **label >= 0.5 && **prediction < 0.5)
        .count();
    let false_positive = propensity_predictions
        .iter()
        .zip(&propensity_labels)
        .filter(|(prediction, label)| **label < 0.5 && **prediction >= 0.5)
        .count();
    let true_positive_rate = ratio(true_positive, true_positive + false_negative);
    let true_negative_rate = ratio(true_negative, true_negative + false_positive);
    let propensity_balanced_accuracy = (true_positive_rate + true_negative_rate) / 2.0;
    let propensity_auc = binary_auc(&propensity_scores, &propensity_labels);

    let ks_distances = feature_columns
        .iter()
        .enumerate()
        .map(|(feature_index, _)| {
            kolmogorov_smirnov_distance(
                &real_feature_vectors
                    .iter()
                    .map(|row| row[feature_index])
                    .collect::<Vec<_>>(),
                &synthetic_feature_vectors
                    .iter()
                    .map(|row| row[feature_index])
                    .collect::<Vec<_>>(),
            )
        })
        .collect::<Vec<_>>();
    let mean_univariate_ks_distance = if ks_distances.is_empty() {
        0.0
    } else {
        ks_distances.iter().sum::<f64>() / ks_distances.len() as f64
    };
    let max_univariate_ks_distance = ks_distances
        .iter()
        .copied()
        .max_by(compare_f64)
        .unwrap_or(0.0);

    let feature_correlation_drift = correlation_drift_summary(
        feature_columns,
        &real_feature_vectors,
        &synthetic_feature_vectors,
    );

    let real_record_signatures = reference_records
        .iter()
        .map(canonical_record_signature)
        .collect::<HashSet<_>>();
    let exact_row_match_count = synthetic_records
        .iter()
        .filter(|record| real_record_signatures.contains(&canonical_record_signature(record)))
        .count();
    let real_feature_signatures = real_feature_vectors
        .iter()
        .map(|row| canonical_feature_signature(row))
        .collect::<HashSet<_>>();
    let exact_feature_match_count = synthetic_feature_vectors
        .iter()
        .filter(|row| real_feature_signatures.contains(&canonical_feature_signature(row)))
        .count();

    let dcr_values = nearest_neighbor_distances(
        &standardized.synthetic_vectors,
        &standardized.real_vectors,
        false,
    );
    let nndr_values = nearest_neighbor_distance_ratios(
        &standardized.synthetic_vectors,
        &standardized.real_vectors,
    );
    let real_baseline =
        nearest_neighbor_distances(&standardized.real_vectors, &standardized.real_vectors, true);
    let real_baseline_summary = summarize_distance_distribution(&real_baseline);
    let dcr_summary = summarize_distance_distribution(&dcr_values);
    let nndr_summary = summarize_distance_distribution(&nndr_values);
    let real_dcr_p5 = percentile(&real_baseline, 0.05);
    let real_dcr_median = percentile(&real_baseline, 0.5);
    let rare_value_alerts = summarize_rare_value_alerts(
        reference_records,
        synthetic_records,
        DEFAULT_RARE_VALUE_ALERT_THRESHOLD,
    );

    Ok(GenerationEvaluationReport {
        reference_population: reference_population.to_string(),
        reference_row_count: reference_records.len(),
        synthetic_row_count: synthetic_records.len(),
        feature_columns: feature_columns.to_vec(),
        quality: SyntheticDataQualityReport {
            propensity_mse,
            propensity_classifier_accuracy: propensity_accuracy,
            propensity_classifier_balanced_accuracy: propensity_balanced_accuracy,
            propensity_classifier_auc: propensity_auc,
            mean_univariate_ks_distance,
            max_univariate_ks_distance,
            feature_correlation_drift,
        },
        privacy: SyntheticDataPrivacyReport {
            exact_row_match_count,
            exact_row_match_ratio: ratio(exact_row_match_count, synthetic_records.len()),
            exact_feature_match_count,
            exact_feature_match_ratio: ratio(exact_feature_match_count, synthetic_records.len()),
            distance_to_closest_record: dcr_summary,
            nearest_neighbor_distance_ratio: nndr_summary,
            real_to_real_distance_baseline: real_baseline_summary,
            synthetic_below_real_dcr_p5_count: dcr_values
                .iter()
                .filter(|value| **value <= real_dcr_p5)
                .count(),
            synthetic_below_real_dcr_median_count: dcr_values
                .iter()
                .filter(|value| **value <= real_dcr_median)
                .count(),
            rare_value_alerts,
        },
        references: evaluation_references(),
        caveats,
    })
}

fn collect_feature_vectors_from_records(
    records: &[Record],
    feature_columns: &[String],
) -> Result<Vec<Vec<f64>>> {
    records
        .iter()
        .map(|record| {
            feature_columns
                .iter()
                .map(|feature| {
                    let value = record.get(feature).ok_or_else(|| {
                        anyhow!("feature column `{feature}` not found in generated rows")
                    })?;
                    value_as_f64(value).ok_or_else(|| {
                        anyhow!("feature column `{feature}` must be numeric in generated rows")
                    })
                })
                .collect::<Result<Vec<_>>>()
        })
        .collect()
}

fn summarize_rare_value_alerts(
    reference_records: &[Record],
    synthetic_records: &[Record],
    threshold: usize,
) -> RareValueAlertSummary {
    let reviewed_columns =
        detect_common_non_numeric_scalar_columns(reference_records, synthetic_records);
    let mut alerts = reviewed_columns
        .iter()
        .filter_map(|column| {
            rare_value_alert_for_column(reference_records, synthetic_records, column, threshold)
        })
        .collect::<Vec<_>>();
    alerts.sort_by(|left, right| {
        right
            .overlapping_unique_value_count
            .cmp(&left.overlapping_unique_value_count)
            .then_with(|| {
                right
                    .overlapping_rare_value_count
                    .cmp(&left.overlapping_rare_value_count)
            })
            .then_with(|| {
                right
                    .synthetic_unique_value_count
                    .cmp(&left.synthetic_unique_value_count)
            })
            .then_with(|| left.column.cmp(&right.column))
    });
    let columns_with_alerts = alerts.len();
    alerts.truncate(MAX_RARE_VALUE_ALERTS);

    RareValueAlertSummary {
        threshold,
        reviewed_columns: reviewed_columns.len(),
        columns_with_alerts,
        alerts,
    }
}

fn detect_common_non_numeric_scalar_columns(
    reference_records: &[Record],
    synthetic_records: &[Record],
) -> Vec<String> {
    let reference_columns = collect_column_names(reference_records)
        .into_iter()
        .collect::<BTreeSet<_>>();
    let synthetic_columns = collect_column_names(synthetic_records)
        .into_iter()
        .collect::<BTreeSet<_>>();

    reference_columns
        .intersection(&synthetic_columns)
        .filter(|column| is_non_numeric_scalar_column(reference_records, synthetic_records, column))
        .cloned()
        .collect()
}

fn is_non_numeric_scalar_column(
    reference_records: &[Record],
    synthetic_records: &[Record],
    column: &str,
) -> bool {
    let mut saw_value = false;
    for record in reference_records.iter().chain(synthetic_records) {
        let Some(value) = record.get(column) else {
            continue;
        };
        match value {
            JsonValue::Null => {}
            JsonValue::Bool(_) | JsonValue::String(_) => {
                saw_value = true;
            }
            JsonValue::Number(_) | JsonValue::Array(_) | JsonValue::Object(_) => {
                return false;
            }
        }
    }

    saw_value
}

fn rare_value_alert_for_column(
    reference_records: &[Record],
    synthetic_records: &[Record],
    column: &str,
    threshold: usize,
) -> Option<RareValueAlert> {
    let reference_counts = scalar_value_frequencies(reference_records, column);
    let synthetic_counts = scalar_value_frequencies(synthetic_records, column);
    if synthetic_counts.is_empty() {
        return None;
    }

    let reference_unique_value_count = reference_counts
        .values()
        .filter(|count| **count == 1)
        .count();
    let synthetic_unique_value_count = synthetic_counts
        .values()
        .filter(|count| **count == 1)
        .count();
    let reference_rare_value_count = reference_counts
        .values()
        .filter(|count| **count < threshold)
        .count();
    let synthetic_rare_value_count = synthetic_counts
        .values()
        .filter(|count| **count < threshold)
        .count();
    if synthetic_unique_value_count == 0 && synthetic_rare_value_count == 0 {
        return None;
    }

    let overlapping_unique_values = synthetic_counts
        .iter()
        .filter_map(|(value, count)| {
            (*count == 1 && reference_counts.contains_key(value)).then_some(value.clone())
        })
        .collect::<Vec<_>>();
    let overlapping_rare_values = synthetic_counts
        .iter()
        .filter_map(|(value, count)| {
            (*count < threshold && reference_counts.contains_key(value)).then_some(value.clone())
        })
        .collect::<Vec<_>>();

    Some(RareValueAlert {
        column: column.to_string(),
        reference_distinct_value_count: reference_counts.len(),
        synthetic_distinct_value_count: synthetic_counts.len(),
        reference_unique_value_count,
        synthetic_unique_value_count,
        reference_rare_value_count,
        synthetic_rare_value_count,
        overlapping_unique_value_count: overlapping_unique_values.len(),
        overlapping_rare_value_count: overlapping_rare_values.len(),
        overlapping_unique_examples: truncate_sorted_strings(overlapping_unique_values),
        overlapping_rare_examples: truncate_sorted_strings(overlapping_rare_values),
    })
}

fn scalar_value_frequencies(records: &[Record], column: &str) -> BTreeMap<String, usize> {
    let mut counts = BTreeMap::new();
    for record in records {
        let Some(value) = record.get(column) else {
            continue;
        };
        let Some(signature) = canonical_non_numeric_scalar_value(value) else {
            continue;
        };
        *counts.entry(signature).or_insert(0) += 1;
    }
    counts
}

fn truncate_sorted_strings(mut values: Vec<String>) -> Vec<String> {
    values.sort();
    values.truncate(MAX_RARE_VALUE_EXAMPLES);
    values
}

fn detect_numeric_columns(records: &[Record]) -> Vec<String> {
    let mut features = Vec::new();
    for column in collect_column_names(records) {
        let mut saw_value = false;
        let mut all_numeric = true;
        for record in records {
            match record.get(&column) {
                None | Some(JsonValue::Null) => {
                    all_numeric = false;
                    break;
                }
                Some(value) => match value_as_f64(value) {
                    Some(_) => saw_value = true,
                    None => {
                        all_numeric = false;
                        break;
                    }
                },
            }
        }
        if saw_value && all_numeric {
            features.push(column);
        }
    }
    features
}

fn compute_numeric_bounds(
    records: &[Record],
    feature_columns: &[String],
) -> Result<HashMap<String, (f64, f64)>> {
    let mut bounds = HashMap::new();
    for feature in feature_columns {
        let mut min_value = f64::INFINITY;
        let mut max_value = f64::NEG_INFINITY;
        for record in records {
            let value = record
                .get(feature)
                .ok_or_else(|| anyhow!("numeric column `{feature}` not found in every row"))?;
            let numeric = value_as_f64(value)
                .ok_or_else(|| anyhow!("numeric column `{feature}` must be numeric"))?;
            min_value = min_value.min(numeric);
            max_value = max_value.max(numeric);
        }
        bounds.insert(feature.clone(), (min_value, max_value));
    }
    Ok(bounds)
}

fn sample_laplace(rng: &mut SmoteRng, scale: f64) -> f64 {
    let uniform = rng.random::<f64>() - 0.5;
    let sign = if uniform < 0.0 { -1.0 } else { 1.0 };
    let magnitude = 1.0 - 2.0 * uniform.abs();
    -sign * scale * magnitude.max(f64::MIN_POSITIVE).ln()
}

fn smote_evaluation_caveats() -> Vec<String> {
    vec![
        "DCR and NNDR are nearest-neighbor privacy proxies. They do not replace membership inference attacks.".to_string(),
        "The utility and privacy evaluation compares synthetic rows against the minority-class reference rows used by SMOTE, not against the full original dataset.".to_string(),
        format!(
            "Rare-value alerts review only shared non-numeric scalar columns and use a default frequency threshold of {}. Treat them as release-review diagnostics, not as an automatic anonymity guarantee.",
            DEFAULT_RARE_VALUE_ALERT_THRESHOLD
        ),
    ]
}

fn dp_noise_evaluation_caveats(epsilon: f64) -> Vec<String> {
    vec![
        "DCR and NNDR are nearest-neighbor privacy proxies. They do not replace membership inference attacks.".to_string(),
        format!("This generator applies Laplace noise with epsilon={epsilon} to numeric columns. Treat it as a lightweight DP-style perturbation method, not as an audited end-to-end private synthetic-data release."),
        "Noise is clipped to the observed numeric range of each column, which is pragmatic for data quality but weakens any strict formal privacy interpretation.".to_string(),
        format!(
            "Rare-value alerts review only shared non-numeric scalar columns and use a default frequency threshold of {}. Treat them as release-review diagnostics, not as an automatic anonymity guarantee.",
            DEFAULT_RARE_VALUE_ALERT_THRESHOLD
        ),
    ]
}

struct StandardizedFeatureSpaces {
    real_vectors: Vec<Vec<f64>>,
    synthetic_vectors: Vec<Vec<f64>>,
}

fn standardize_feature_spaces(
    real_vectors: &[Vec<f64>],
    synthetic_vectors: &[Vec<f64>],
) -> StandardizedFeatureSpaces {
    if real_vectors.is_empty() {
        return StandardizedFeatureSpaces {
            real_vectors: Vec::new(),
            synthetic_vectors: Vec::new(),
        };
    }

    let dimension = real_vectors[0].len();
    let mut means = vec![0.0; dimension];
    let mut stddevs = vec![0.0; dimension];

    for row in real_vectors {
        for (index, value) in row.iter().enumerate() {
            means[index] += *value;
        }
    }
    for mean in &mut means {
        *mean /= real_vectors.len() as f64;
    }
    for row in real_vectors {
        for (index, value) in row.iter().enumerate() {
            let delta = *value - means[index];
            stddevs[index] += delta * delta;
        }
    }
    for stddev in &mut stddevs {
        *stddev = (*stddev / real_vectors.len().max(1) as f64).sqrt();
        if *stddev == 0.0 {
            *stddev = 1.0;
        }
    }

    let transform = |rows: &[Vec<f64>]| {
        rows.iter()
            .map(|row| {
                row.iter()
                    .enumerate()
                    .map(|(index, value)| (*value - means[index]) / stddevs[index])
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>()
    };

    StandardizedFeatureSpaces {
        real_vectors: transform(real_vectors),
        synthetic_vectors: transform(synthetic_vectors),
    }
}

fn train_propensity_scores(real_vectors: &[Vec<f64>], synthetic_vectors: &[Vec<f64>]) -> Vec<f64> {
    let rows = real_vectors
        .iter()
        .map(|row| (row.clone(), 0.0))
        .chain(synthetic_vectors.iter().map(|row| (row.clone(), 1.0)))
        .collect::<Vec<_>>();
    if rows.is_empty() {
        return Vec::new();
    }

    let dimension = rows[0].0.len() + 1;
    let mut weights = vec![0.0; dimension];
    let learning_rate = 0.1;
    let l2 = 1e-4;

    for _ in 0..400 {
        let mut gradient = vec![0.0; dimension];
        for (features, label) in &rows {
            let prediction = sigmoid(dot_with_bias(&weights, features));
            let error = prediction - *label;
            gradient[0] += error;
            for (index, value) in features.iter().enumerate() {
                gradient[index + 1] += error * *value;
            }
        }

        for index in 0..weights.len() {
            let regularization = if index == 0 { 0.0 } else { l2 * weights[index] };
            weights[index] -=
                learning_rate * ((gradient[index] / rows.len() as f64) + regularization);
        }
    }

    rows.iter()
        .map(|(features, _)| sigmoid(dot_with_bias(&weights, features)))
        .collect()
}

fn dot_with_bias(weights: &[f64], features: &[f64]) -> f64 {
    let mut total = weights[0];
    for (weight, value) in weights.iter().skip(1).zip(features) {
        total += weight * value;
    }
    total
}

fn sigmoid(value: f64) -> f64 {
    if value >= 0.0 {
        let exp = (-value).exp();
        1.0 / (1.0 + exp)
    } else {
        let exp = value.exp();
        exp / (1.0 + exp)
    }
}

fn binary_auc(scores: &[f64], labels: &[f64]) -> f64 {
    if scores.len() != labels.len() || scores.is_empty() {
        return 0.0;
    }

    let positive_count = labels.iter().filter(|label| **label >= 0.5).count();
    let negative_count = labels.len().saturating_sub(positive_count);
    if positive_count == 0 || negative_count == 0 {
        return 0.0;
    }

    let indexed_scores = scores
        .iter()
        .enumerate()
        .map(|(index, score)| (index, *score))
        .collect::<Vec<_>>();
    let ranks_map = ranks(&indexed_scores);
    let positive_rank_sum = labels
        .iter()
        .enumerate()
        .filter(|(_, label)| **label >= 0.5)
        .map(|(index, _)| ranks_map[&index])
        .sum::<f64>();

    (positive_rank_sum - (positive_count * (positive_count + 1) / 2) as f64)
        / (positive_count as f64 * negative_count as f64)
}

fn kolmogorov_smirnov_distance(left: &[f64], right: &[f64]) -> f64 {
    if left.is_empty() || right.is_empty() {
        return 0.0;
    }

    let mut left_sorted = left.to_vec();
    let mut right_sorted = right.to_vec();
    left_sorted.sort_by(compare_f64);
    right_sorted.sort_by(compare_f64);

    let mut i = 0usize;
    let mut j = 0usize;
    let mut max_delta: f64 = 0.0;

    while i < left_sorted.len() && j < right_sorted.len() {
        let next = if left_sorted[i] <= right_sorted[j] {
            left_sorted[i]
        } else {
            right_sorted[j]
        };
        while i < left_sorted.len() && left_sorted[i] <= next {
            i += 1;
        }
        while j < right_sorted.len() && right_sorted[j] <= next {
            j += 1;
        }

        let left_cdf = i as f64 / left_sorted.len() as f64;
        let right_cdf = j as f64 / right_sorted.len() as f64;
        max_delta = max_delta.max((left_cdf - right_cdf).abs());
    }

    max_delta
}

fn correlation_drift_summary(
    feature_columns: &[String],
    real_vectors: &[Vec<f64>],
    synthetic_vectors: &[Vec<f64>],
) -> CorrelationDriftSummary {
    let mut drifts = Vec::new();

    for left_index in 0..feature_columns.len() {
        for right_index in (left_index + 1)..feature_columns.len() {
            let real_pairs = real_vectors
                .iter()
                .map(|row| (row[left_index], row[right_index]))
                .collect::<Vec<_>>();
            let synthetic_pairs = synthetic_vectors
                .iter()
                .map(|row| (row[left_index], row[right_index]))
                .collect::<Vec<_>>();
            let Some(real_summary) = summarize_numeric_pair(&real_pairs) else {
                continue;
            };
            let Some(synthetic_summary) = summarize_numeric_pair(&synthetic_pairs) else {
                continue;
            };

            drifts.push(CorrelationDriftPair {
                left: feature_columns[left_index].clone(),
                right: feature_columns[right_index].clone(),
                pearson_delta: synthetic_summary.pearson_correlation
                    - real_summary.pearson_correlation,
                spearman_delta: synthetic_summary.spearman_correlation
                    - real_summary.spearman_correlation,
            });
        }
    }

    let mean_absolute_pearson_delta = if drifts.is_empty() {
        0.0
    } else {
        drifts
            .iter()
            .map(|pair| pair.pearson_delta.abs())
            .sum::<f64>()
            / drifts.len() as f64
    };
    let max_absolute_pearson_delta = drifts
        .iter()
        .map(|pair| pair.pearson_delta.abs())
        .max_by(compare_f64)
        .unwrap_or(0.0);
    let mean_absolute_spearman_delta = if drifts.is_empty() {
        0.0
    } else {
        drifts
            .iter()
            .map(|pair| pair.spearman_delta.abs())
            .sum::<f64>()
            / drifts.len() as f64
    };
    let max_absolute_spearman_delta = drifts
        .iter()
        .map(|pair| pair.spearman_delta.abs())
        .max_by(compare_f64)
        .unwrap_or(0.0);

    drifts.sort_by(|left, right| {
        let left_score = left.pearson_delta.abs().max(left.spearman_delta.abs());
        let right_score = right.pearson_delta.abs().max(right.spearman_delta.abs());
        compare_f64(&right_score, &left_score)
    });

    CorrelationDriftSummary {
        pair_count: drifts.len(),
        mean_absolute_pearson_delta,
        max_absolute_pearson_delta,
        mean_absolute_spearman_delta,
        max_absolute_spearman_delta,
        top_drift_pairs: drifts.into_iter().take(5).collect(),
    }
}

fn nearest_neighbor_distances(
    queries: &[Vec<f64>],
    candidates: &[Vec<f64>],
    exclude_self: bool,
) -> Vec<f64> {
    let mut distances = Vec::new();

    for (query_index, query) in queries.iter().enumerate() {
        let nearest = candidates
            .iter()
            .enumerate()
            .filter(|(candidate_index, _)| !exclude_self || *candidate_index != query_index)
            .map(|(_, candidate)| euclidean_distance_from_vectors(query, candidate))
            .min_by(compare_f64)
            .unwrap_or(0.0);
        distances.push(nearest);
    }

    distances
}

fn nearest_neighbor_distance_ratios(queries: &[Vec<f64>], candidates: &[Vec<f64>]) -> Vec<f64> {
    let mut ratios = Vec::new();

    for query in queries {
        let mut distances = candidates
            .iter()
            .map(|candidate| euclidean_distance_from_vectors(query, candidate))
            .collect::<Vec<_>>();
        distances.sort_by(compare_f64);
        if distances.is_empty() {
            ratios.push(0.0);
        } else if distances.len() == 1 || distances[1] == 0.0 {
            ratios.push(1.0);
        } else {
            ratios.push(distances[0] / distances[1]);
        }
    }

    ratios
}

fn summarize_distance_distribution(values: &[f64]) -> DistanceSummary {
    if values.is_empty() {
        return DistanceSummary {
            count: 0,
            min: 0.0,
            p5: 0.0,
            median: 0.0,
            mean: 0.0,
            p95: 0.0,
            max: 0.0,
        };
    }

    let mut sorted = values.to_vec();
    sorted.sort_by(compare_f64);

    DistanceSummary {
        count: sorted.len(),
        min: *sorted.first().unwrap_or(&0.0),
        p5: percentile(&sorted, 0.05),
        median: percentile(&sorted, 0.5),
        mean: sorted.iter().sum::<f64>() / sorted.len() as f64,
        p95: percentile(&sorted, 0.95),
        max: *sorted.last().unwrap_or(&0.0),
    }
}

fn euclidean_distance_from_vectors(left: &[f64], right: &[f64]) -> f64 {
    left.iter()
        .zip(right)
        .map(|(left_value, right_value)| {
            let delta = *left_value - *right_value;
            delta * delta
        })
        .sum::<f64>()
        .sqrt()
}

fn canonical_record_signature(record: &Record) -> String {
    let mut keys = record.keys().cloned().collect::<Vec<_>>();
    keys.sort();
    let parts = keys
        .into_iter()
        .map(|key| {
            let value = record.get(&key).cloned().unwrap_or(JsonValue::Null);
            format!("{key}={}", canonical_json_value(&value))
        })
        .collect::<Vec<_>>();
    parts.join("|")
}

fn canonical_json_value(value: &JsonValue) -> String {
    match value {
        JsonValue::Null => "null".to_string(),
        JsonValue::Bool(value) => value.to_string(),
        JsonValue::Number(value) => value.to_string(),
        JsonValue::String(value) => value.clone(),
        JsonValue::Array(values) => format!(
            "[{}]",
            values
                .iter()
                .map(canonical_json_value)
                .collect::<Vec<_>>()
                .join(",")
        ),
        JsonValue::Object(map) => {
            let mut keys = map.keys().cloned().collect::<Vec<_>>();
            keys.sort();
            format!(
                "{{{}}}",
                keys.into_iter()
                    .map(|key| {
                        let value = map.get(&key).cloned().unwrap_or(JsonValue::Null);
                        format!("{key}:{}", canonical_json_value(&value))
                    })
                    .collect::<Vec<_>>()
                    .join(",")
            )
        }
    }
}

fn canonical_feature_signature(values: &[f64]) -> String {
    values
        .iter()
        .map(|value| format!("{value:.12}"))
        .collect::<Vec<_>>()
        .join("|")
}

fn evaluation_references() -> Vec<EvaluationReference> {
    vec![
        EvaluationReference {
            metric: "propensity_mse".to_string(),
            citation: "Snoke et al. (2018), General and specific utility measures for synthetic data".to_string(),
            url: "https://academic.oup.com/jrsssa/article/181/3/663/7072005".to_string(),
            note: "Uses distinguishability between real and synthetic rows as a general utility signal.".to_string(),
        },
        EvaluationReference {
            metric: "distance_to_closest_record".to_string(),
            citation: "Yao et al. (2025), The DCR Delusion: Measuring the Privacy Risk of Synthetic Data".to_string(),
            url: "https://arxiv.org/abs/2505.01524".to_string(),
            note: "DCR is included as a proxy privacy metric, with an explicit warning that it is not sufficient on its own.".to_string(),
        },
        EvaluationReference {
            metric: "nearest_neighbor_distance_ratio".to_string(),
            citation: "Common synthetic-data privacy literature using nearest-neighbor proxies, discussed critically by Yao et al. (2025)".to_string(),
            url: "https://arxiv.org/abs/2505.01524".to_string(),
            note: "NNDR complements DCR by showing whether a synthetic row sits unusually close to one real row versus the second-nearest alternative.".to_string(),
        },
    ]
}

fn infer_schema(records: &[Record], format: DatasetFormat, name: &str) -> InferredSchema {
    let mut state = SchemaState::default();
    for record in records {
        merge_schema_state(&mut state, &JsonValue::Object(record.clone()));
    }

    InferredSchema {
        name: to_type_name(name),
        format,
        root: finalize_schema_state(state),
    }
}

fn compute_column_stats(name: &str, records: &[Record]) -> ColumnStats {
    let row_count = records.len();
    let mut null_count = 0usize;
    let mut missing_count = 0usize;
    let mut non_null_count = 0usize;
    let mut type_counts: BTreeMap<ValueType, usize> = BTreeMap::new();
    let mut distinct_values = HashSet::new();
    let mut numeric_values = Vec::new();
    let mut string_values = Vec::new();
    let mut boolean_values = Vec::new();
    let mut scalar_counts: HashMap<String, usize> = HashMap::new();
    let mut temporal_values = Vec::new();

    for record in records {
        match record.get(name) {
            None => missing_count += 1,
            Some(JsonValue::Null) => null_count += 1,
            Some(value) => {
                non_null_count += 1;
                let value_type = classify_value(value);
                *type_counts.entry(value_type).or_default() += 1;
                let canonical = canonical_value(value);
                distinct_values.insert(canonical.clone());

                if let Some(label) = scalar_value_label(value) {
                    *scalar_counts.entry(label).or_default() += 1;
                }

                match value {
                    JsonValue::Number(number) => {
                        if let Some(value) = number.as_f64() {
                            numeric_values.push(value);
                        }
                    }
                    JsonValue::String(text) => string_values.push(text.clone()),
                    JsonValue::Bool(value) => boolean_values.push(*value),
                    _ => {}
                }

                if let Some(timestamp) = value_as_timestamp(value) {
                    temporal_values.push(timestamp);
                }
            }
        }
    }

    let dominant_type = type_counts
        .iter()
        .max_by_key(|(_, count)| *count)
        .map(|(value_type, _)| *value_type)
        .unwrap_or(ValueType::Null);

    let value_type_counts = type_counts
        .into_iter()
        .map(|(value_type, count)| (value_type.label().to_string(), count))
        .collect::<BTreeMap<_, _>>();

    let distinct_count = distinct_values.len();
    let mode_count = scalar_counts.values().copied().max().unwrap_or(0);

    ColumnStats {
        name: name.to_string(),
        dominant_type,
        non_null_count,
        null_count,
        missing_count,
        completeness_ratio: ratio(non_null_count, row_count),
        null_ratio: ratio(null_count + missing_count, row_count),
        distinct_count,
        distinct_ratio: ratio(distinct_count, non_null_count),
        uniqueness_ratio: ratio(distinct_count, row_count),
        mode_count,
        mode_ratio: ratio(mode_count, non_null_count),
        entropy: shannon_entropy(&scalar_counts, non_null_count),
        value_type_counts,
        top_values: top_value_frequencies(&scalar_counts, non_null_count),
        numeric_summary: summarize_numbers(&numeric_values),
        string_summary: summarize_strings(&string_values),
        boolean_summary: summarize_booleans(&boolean_values),
        temporal_summary: summarize_temporal(&temporal_values),
    }
}

fn compute_column_pair_stats(names: &[String], records: &[Record]) -> Vec<ColumnPairStats> {
    let mut pairs = Vec::new();

    for left_index in 0..names.len() {
        for right_index in (left_index + 1)..names.len() {
            let left = &names[left_index];
            let right = &names[right_index];

            let mut paired_non_null_count = 0usize;
            let mut both_null_or_missing_count = 0usize;
            let mut equal_scalar_count = 0usize;
            let mut numeric_pairs = Vec::new();
            let mut left_distinct = HashSet::new();
            let mut right_distinct = HashSet::new();
            let mut pair_counts: HashMap<String, usize> = HashMap::new();
            let mut left_scalar_counts: HashMap<String, usize> = HashMap::new();
            let mut right_scalar_counts: HashMap<String, usize> = HashMap::new();

            for record in records {
                let left_value = record.get(left).unwrap_or(&JsonValue::Null);
                let right_value = record.get(right).unwrap_or(&JsonValue::Null);

                let left_present = !left_value.is_null();
                let right_present = !right_value.is_null();

                if left_present && right_present {
                    paired_non_null_count += 1;

                    if let Some(left_scalar) = scalar_value_label(left_value) {
                        left_distinct.insert(left_scalar.clone());
                        *left_scalar_counts.entry(left_scalar.clone()).or_default() += 1;
                        if let Some(right_scalar) = scalar_value_label(right_value) {
                            right_distinct.insert(right_scalar.clone());
                            *right_scalar_counts.entry(right_scalar.clone()).or_default() += 1;
                            *pair_counts
                                .entry(format!("{left_scalar} | {right_scalar}"))
                                .or_default() += 1;
                        }
                    }

                    if scalar_value_label(left_value).is_some()
                        && scalar_value_label(left_value) == scalar_value_label(right_value)
                    {
                        equal_scalar_count += 1;
                    }

                    if let (Some(left_number), Some(right_number)) =
                        (value_as_f64(left_value), value_as_f64(right_value))
                    {
                        numeric_pairs.push((left_number, right_number));
                    }
                } else if !left_present && !right_present {
                    both_null_or_missing_count += 1;
                }
            }

            pairs.push(ColumnPairStats {
                left: left.clone(),
                right: right.clone(),
                paired_non_null_count,
                overlap_ratio: ratio(paired_non_null_count, records.len()),
                both_null_or_missing_count,
                equal_scalar_count,
                equal_scalar_ratio: ratio(equal_scalar_count, paired_non_null_count),
                shared_distinct_scalar_count: left_distinct.intersection(&right_distinct).count(),
                scalar_jaccard_index: jaccard_index(&left_distinct, &right_distinct),
                numeric_relationship: summarize_numeric_pair(&numeric_pairs),
                categorical_relationship: summarize_categorical_pair(
                    &pair_counts,
                    &left_scalar_counts,
                    &right_scalar_counts,
                    paired_non_null_count,
                ),
            });
        }
    }

    pairs
}

fn compute_structure_report(
    names: &[String],
    records: &[Record],
    column_stats: &[ColumnStats],
) -> StructureReport {
    let mut dataset_type_counts: BTreeMap<String, usize> = BTreeMap::new();
    let mut nested_stats: BTreeMap<String, NestedAccumulator> = BTreeMap::new();
    let mut columns = Vec::new();

    for (name, stats) in names.iter().zip(column_stats.iter()) {
        let mut observed_types_raw: BTreeMap<ValueType, usize> = BTreeMap::new();
        let mut array_lengths = Vec::new();
        let mut array_element_types: BTreeMap<ValueType, usize> = BTreeMap::new();
        let mut object_key_counts = Vec::new();
        let mut object_key_frequency: HashMap<String, usize> = HashMap::new();

        for record in records {
            if let Some(value) = record.get(name) {
                let value_type = classify_value(value);
                *dataset_type_counts
                    .entry(value_type.label().to_string())
                    .or_default() += 1;
                *observed_types_raw.entry(value_type).or_default() += 1;
                collect_nested_stats(name, value, &mut nested_stats);

                match value {
                    JsonValue::Array(items) => {
                        array_lengths.push(items.len());
                        for item in items {
                            *array_element_types.entry(classify_value(item)).or_default() += 1;
                        }
                    }
                    JsonValue::Object(map) => {
                        object_key_counts.push(map.len());
                        for key in map.keys() {
                            *object_key_frequency.entry(key.clone()).or_default() += 1;
                        }
                    }
                    _ => {}
                }
            }
        }

        let observed_types = observed_types_raw
            .into_iter()
            .map(|(kind, count)| (kind.label().to_string(), count))
            .collect::<BTreeMap<_, _>>();

        let array_summary = if array_lengths.is_empty() {
            None
        } else {
            Some(ArrayStructureSummary {
                row_count_with_arrays: array_lengths.len(),
                min_length: *array_lengths.iter().min().unwrap_or(&0),
                max_length: *array_lengths.iter().max().unwrap_or(&0),
                average_length: array_lengths.iter().sum::<usize>() as f64
                    / array_lengths.len() as f64,
                element_type_counts: array_element_types
                    .into_iter()
                    .map(|(kind, count)| (kind.label().to_string(), count))
                    .collect(),
            })
        };

        let object_summary = if object_key_counts.is_empty() {
            None
        } else {
            Some(ObjectStructureSummary {
                row_count_with_objects: object_key_counts.len(),
                key_count_min: *object_key_counts.iter().min().unwrap_or(&0),
                key_count_max: *object_key_counts.iter().max().unwrap_or(&0),
                average_key_count: object_key_counts.iter().sum::<usize>() as f64
                    / object_key_counts.len() as f64,
                top_keys: top_value_frequencies(&object_key_frequency, object_key_counts.len()),
            })
        };

        columns.push(ColumnStructure {
            name: name.clone(),
            observed_types,
            array_summary,
            object_summary,
            semantic_hints: semantic_hints(stats),
        });
    }

    let mut nested_fields = nested_stats
        .into_iter()
        .map(|(path, stats)| NestedFieldStats {
            path,
            occurrence_count: stats.occurrence_count,
            null_count: stats.null_count,
            observed_types: stats
                .observed_types
                .into_iter()
                .map(|(kind, count)| (kind.label().to_string(), count))
                .collect(),
        })
        .collect::<Vec<_>>();
    nested_fields.sort_by(|left, right| left.path.cmp(&right.path));

    StructureReport {
        dataset_type_counts,
        nested_field_count: nested_fields.len(),
        nested_fields,
        columns,
    }
}

fn summarize_numbers(values: &[f64]) -> Option<NumericSummary> {
    if values.is_empty() {
        return None;
    }

    let mut sorted = values.to_vec();
    sorted.sort_by(compare_f64);

    let count = sorted.len();
    let sum = sorted.iter().copied().sum::<f64>();
    let mean = sum / count as f64;
    let median = percentile(&sorted, 0.5);
    let p25 = percentile(&sorted, 0.25);
    let p50 = percentile(&sorted, 0.50);
    let p75 = percentile(&sorted, 0.75);
    let p95 = percentile(&sorted, 0.95);
    let variance = sorted
        .iter()
        .map(|value| {
            let diff = *value - mean;
            diff * diff
        })
        .sum::<f64>()
        / count as f64;
    let stddev = variance.sqrt();
    let range = sorted.last().unwrap_or(&0.0) - sorted.first().unwrap_or(&0.0);
    let iqr = p75 - p25;
    let deviations = sorted
        .iter()
        .map(|value| (*value - median).abs())
        .collect::<Vec<_>>();
    let mut sorted_deviations = deviations;
    sorted_deviations.sort_by(compare_f64);
    let mad = percentile(&sorted_deviations, 0.5);
    let zero_count = sorted.iter().filter(|value| **value == 0.0).count();
    let positive_count = sorted.iter().filter(|value| **value > 0.0).count();
    let negative_count = sorted.iter().filter(|value| **value < 0.0).count();
    let integer_like_count = sorted
        .iter()
        .filter(|value| (**value - value.round()).abs() < 1e-9)
        .count();
    let duplicate_count = count.saturating_sub(
        sorted
            .windows(2)
            .filter(|window| (window[0] - window[1]).abs() >= 1e-12)
            .count()
            + usize::from(!sorted.is_empty()),
    );
    let lower_fence = p25 - 1.5 * iqr;
    let upper_fence = p75 + 1.5 * iqr;
    let outlier_count_tukey = sorted
        .iter()
        .filter(|value| **value < lower_fence || **value > upper_fence)
        .count();
    let monotonic_increasing = values.windows(2).all(|window| window[0] <= window[1]);
    let monotonic_decreasing = values.windows(2).all(|window| window[0] >= window[1]);
    let is_constant = range.abs() < 1e-12;
    let skewness = if stddev == 0.0 {
        0.0
    } else {
        sorted
            .iter()
            .map(|value| ((*value - mean) / stddev).powi(3))
            .sum::<f64>()
            / count as f64
    };
    let kurtosis_excess = if stddev == 0.0 {
        0.0
    } else {
        sorted
            .iter()
            .map(|value| ((*value - mean) / stddev).powi(4))
            .sum::<f64>()
            / count as f64
            - 3.0
    };

    Some(NumericSummary {
        count,
        min: *sorted.first().unwrap_or(&0.0),
        max: *sorted.last().unwrap_or(&0.0),
        sum,
        mean,
        median,
        variance,
        stddev,
        p25,
        p50,
        p75,
        p95,
        range,
        iqr,
        mad,
        coefficient_of_variation: if mean == 0.0 {
            0.0
        } else {
            stddev / mean.abs()
        },
        zero_count,
        positive_count,
        negative_count,
        integer_like_count,
        duplicate_count,
        duplicate_ratio: ratio(duplicate_count, count),
        outlier_count_tukey,
        monotonic_increasing,
        monotonic_decreasing,
        is_constant,
        skewness,
        kurtosis_excess,
    })
}

fn summarize_strings(values: &[String]) -> Option<StringSummary> {
    if values.is_empty() {
        return None;
    }

    let mut lengths = values
        .iter()
        .map(|value| value.chars().count() as f64)
        .collect::<Vec<_>>();
    lengths.sort_by(compare_f64);

    Some(StringSummary {
        count: values.len(),
        min_length: lengths.first().copied().unwrap_or(0.0) as usize,
        max_length: lengths.last().copied().unwrap_or(0.0) as usize,
        average_length: lengths.iter().copied().sum::<f64>() / values.len() as f64,
        median_length: percentile(&lengths, 0.5),
        empty_count: values.iter().filter(|value| value.is_empty()).count(),
        whitespace_only_count: values
            .iter()
            .filter(|value| !value.is_empty() && value.trim().is_empty())
            .count(),
        average_word_count: values
            .iter()
            .map(|value| value.split_whitespace().count() as f64)
            .sum::<f64>()
            / values.len() as f64,
        max_word_count: values
            .iter()
            .map(|value| value.split_whitespace().count())
            .max()
            .unwrap_or(0),
        date_like_count: values
            .iter()
            .filter(|value| parse_datetime_string(value).is_some())
            .count(),
        email_like_count: values
            .iter()
            .filter(|value| looks_like_email(value))
            .count(),
        ip_like_count: values.iter().filter(|value| looks_like_ip(value)).count(),
        uuid_like_count: values.iter().filter(|value| looks_like_uuid(value)).count(),
        url_like_count: values.iter().filter(|value| looks_like_url(value)).count(),
        phone_like_count: values
            .iter()
            .filter(|value| looks_like_phone(value))
            .count(),
        json_like_count: values.iter().filter(|value| looks_like_json(value)).count(),
        numeric_like_count: values
            .iter()
            .filter(|value| looks_like_numeric_text(value))
            .count(),
        boolean_like_count: values
            .iter()
            .filter(|value| looks_like_boolean_text(value))
            .count(),
        ascii_only_count: values.iter().filter(|value| value.is_ascii()).count(),
        hex_like_count: values.iter().filter(|value| looks_like_hex(value)).count(),
        base64_like_count: values
            .iter()
            .filter(|value| looks_like_base64(value))
            .count(),
        mac_address_like_count: values
            .iter()
            .filter(|value| looks_like_mac_address(value))
            .count(),
        zip_code_like_count: values
            .iter()
            .filter(|value| looks_like_zip_code(value))
            .count(),
    })
}

fn summarize_booleans(values: &[bool]) -> Option<BooleanSummary> {
    if values.is_empty() {
        return None;
    }

    let true_count = values.iter().filter(|value| **value).count();
    let false_count = values.len() - true_count;

    Some(BooleanSummary {
        true_count,
        false_count,
        true_ratio: ratio(true_count, values.len()),
    })
}

fn summarize_numeric_pair(values: &[(f64, f64)]) -> Option<NumericPairSummary> {
    if values.len() < 2 {
        return None;
    }

    let count = values.len() as f64;
    let left_mean = values.iter().map(|(left, _)| *left).sum::<f64>() / count;
    let right_mean = values.iter().map(|(_, right)| *right).sum::<f64>() / count;
    let mut covariance_acc = 0.0;
    let mut left_variance_acc = 0.0;
    let mut right_variance_acc = 0.0;

    for (left, right) in values {
        let left_diff = *left - left_mean;
        let right_diff = *right - right_mean;
        covariance_acc += left_diff * right_diff;
        left_variance_acc += left_diff * left_diff;
        right_variance_acc += right_diff * right_diff;
    }

    let covariance = covariance_acc / count;
    let left_std = (left_variance_acc / count).sqrt();
    let right_std = (right_variance_acc / count).sqrt();
    let pearson_correlation = if left_std == 0.0 || right_std == 0.0 {
        0.0
    } else {
        covariance / (left_std * right_std)
    };
    let slope = if left_variance_acc == 0.0 {
        0.0
    } else {
        covariance_acc / left_variance_acc
    };
    let intercept = right_mean - slope * left_mean;
    let ranked_pairs = values
        .iter()
        .enumerate()
        .map(|(index, (left, right))| (index, *left, *right))
        .collect::<Vec<_>>();
    let left_ranks = ranks(
        &ranked_pairs
            .iter()
            .map(|(index, left, _)| (*index, *left))
            .collect::<Vec<_>>(),
    );
    let right_ranks = ranks(
        &ranked_pairs
            .iter()
            .map(|(index, _, right)| (*index, *right))
            .collect::<Vec<_>>(),
    );
    let rank_pairs = ranked_pairs
        .iter()
        .map(|(index, _, _)| (left_ranks[index], right_ranks[index]))
        .collect::<Vec<_>>();
    let spearman_correlation = pearson_for_pairs(&rank_pairs);

    Some(NumericPairSummary {
        covariance,
        pearson_correlation,
        spearman_correlation,
        slope,
        intercept,
        r_squared: pearson_correlation * pearson_correlation,
    })
}

fn summarize_temporal(values: &[DateTime<Utc>]) -> Option<TemporalSummary> {
    if values.is_empty() {
        return None;
    }

    let min = values.iter().min().cloned()?;
    let max = values.iter().max().cloned()?;

    Some(TemporalSummary {
        count: values.len(),
        min: min.to_rfc3339(),
        max: max.to_rfc3339(),
    })
}

fn summarize_categorical_pair(
    pair_counts: &HashMap<String, usize>,
    left_counts: &HashMap<String, usize>,
    right_counts: &HashMap<String, usize>,
    total: usize,
) -> Option<CategoricalPairSummary> {
    if pair_counts.is_empty() || total == 0 {
        return None;
    }

    let left_entropy = shannon_entropy(left_counts, total);
    let right_entropy = shannon_entropy(right_counts, total);
    let joint_entropy = shannon_entropy(pair_counts, total);
    let mutual_information = (left_entropy + right_entropy - joint_entropy).max(0.0);
    let normalized_mutual_information = if left_entropy == 0.0 || right_entropy == 0.0 {
        0.0
    } else {
        mutual_information / (left_entropy * right_entropy).sqrt()
    };
    let chi_square = categorical_chi_square(pair_counts, left_counts, right_counts, total);
    let min_dim = left_counts.len().min(right_counts.len());
    let cramers_v = if min_dim <= 1 {
        0.0
    } else {
        (chi_square / (total as f64 * (min_dim as f64 - 1.0))).sqrt()
    };

    Some(CategoricalPairSummary {
        distinct_pair_count: pair_counts.len(),
        top_combinations: top_value_frequencies(pair_counts, total),
        mutual_information,
        normalized_mutual_information,
        chi_square,
        cramers_v,
    })
}

fn classify_value(value: &JsonValue) -> ValueType {
    match value {
        JsonValue::Null => ValueType::Null,
        JsonValue::Bool(_) => ValueType::Boolean,
        JsonValue::Number(_) => ValueType::Number,
        JsonValue::String(_) => ValueType::String,
        JsonValue::Array(_) => ValueType::Array,
        JsonValue::Object(_) => ValueType::Object,
    }
}

fn merge_schema_state(state: &mut SchemaState, value: &JsonValue) {
    let kind = classify_value(value);
    *state.kinds.entry(kind).or_default() += 1;
    if value.is_null() {
        state.null_count += 1;
    }

    match value {
        JsonValue::Null => {}
        JsonValue::String(text) => {
            for hint in semantic_hints_for_string(text) {
                state.string_semantics.insert(hint);
            }
        }
        JsonValue::Array(items) => {
            let item_state = state
                .array
                .get_or_insert_with(|| Box::<SchemaState>::default());
            for item in items {
                merge_schema_state(item_state, item);
            }
        }
        JsonValue::Object(map) => {
            let object_state = state.object.get_or_insert_with(ObjectSchemaState::default);
            object_state.sample_count += 1;
            for (key, child) in map {
                *object_state
                    .field_occurrences
                    .entry(key.clone())
                    .or_default() += 1;
                let field_state = object_state.fields.entry(key.clone()).or_default();
                merge_schema_state(field_state, child);
            }
        }
        _ => {}
    }
}

fn finalize_schema_state(state: SchemaState) -> SchemaNode {
    let semantic_hints = state.string_semantics.into_iter().collect::<Vec<_>>();
    let object = state.object.map(|object_state| {
        let sample_count = object_state.sample_count;
        let fields = object_state
            .fields
            .into_iter()
            .map(|(name, field_state)| SchemaField {
                required: object_state
                    .field_occurrences
                    .get(&name)
                    .copied()
                    .unwrap_or(0)
                    == sample_count
                    && field_state.null_count == 0,
                name,
                schema: finalize_schema_state(field_state),
            })
            .collect::<Vec<_>>();
        ObjectSchema { fields }
    });
    let array = state.array.map(|item| ArraySchema {
        item: Box::new(finalize_schema_state(*item)),
    });

    SchemaNode {
        kinds: state
            .kinds
            .into_iter()
            .map(|(kind, count)| (kind.label().to_string(), count))
            .collect(),
        nullable: state.null_count > 0,
        semantic_hints,
        object,
        array,
    }
}

fn semantic_hints_for_string(text: &str) -> Vec<String> {
    let mut hints = Vec::new();
    if parse_datetime_string(text).is_some() {
        hints.push("temporal".to_string());
    }
    if looks_like_email(text) {
        hints.push("email_like".to_string());
    }
    if looks_like_ip(text) {
        hints.push("ip_like".to_string());
    }
    if looks_like_uuid(text) {
        hints.push("uuid_like".to_string());
    }
    if looks_like_url(text) {
        hints.push("url_like".to_string());
    }
    if looks_like_phone(text) {
        hints.push("phone_like".to_string());
    }
    if looks_like_json(text) {
        hints.push("json_like".to_string());
    }
    if looks_like_mac_address(text) {
        hints.push("mac_address_like".to_string());
    }
    if looks_like_zip_code(text) {
        hints.push("zip_code_like".to_string());
    }
    hints
}

fn canonical_value(value: &JsonValue) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| format!("{value:?}"))
}

fn scalar_value_label(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::Null => None,
        JsonValue::Bool(value) => Some(value.to_string()),
        JsonValue::Number(value) => Some(value.to_string()),
        JsonValue::String(value) => Some(value.clone()),
        _ => None,
    }
}

fn value_as_f64(value: &JsonValue) -> Option<f64> {
    match value {
        JsonValue::Number(number) => number.as_f64(),
        _ => None,
    }
}

fn canonical_non_numeric_scalar_value(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::Bool(boolean) => Some(boolean.to_string()),
        JsonValue::String(text) => Some(text.clone()),
        _ => None,
    }
}

fn value_as_i64_if_integral(value: &JsonValue) -> Option<i64> {
    match value {
        JsonValue::Number(number) => number
            .as_i64()
            .or_else(|| number.as_u64().and_then(|raw| i64::try_from(raw).ok())),
        _ => None,
    }
}

fn value_as_timestamp(value: &JsonValue) -> Option<DateTime<Utc>> {
    match value {
        JsonValue::String(value) => parse_datetime_string(value),
        _ => None,
    }
}

fn parse_datetime_string(input: &str) -> Option<DateTime<Utc>> {
    if let Ok(value) = DateTime::parse_from_rfc3339(input) {
        return Some(value.with_timezone(&Utc));
    }

    if let Ok(value) = NaiveDate::parse_from_str(input, "%Y-%m-%d") {
        return Some(DateTime::from_naive_utc_and_offset(
            value.and_hms_opt(0, 0, 0)?,
            Utc,
        ));
    }

    None
}

fn top_value_frequencies(counts: &HashMap<String, usize>, total: usize) -> Vec<ValueFrequency> {
    let mut entries = counts.iter().collect::<Vec<_>>();
    entries.sort_by(|(left_value, left_count), (right_value, right_count)| {
        right_count
            .cmp(left_count)
            .then_with(|| left_value.cmp(right_value))
    });

    entries
        .into_iter()
        .take(5)
        .map(|(value, count)| ValueFrequency {
            value: value.clone(),
            count: *count,
            ratio: ratio(*count, total),
        })
        .collect()
}

fn shannon_entropy(counts: &HashMap<String, usize>, total: usize) -> f64 {
    if total == 0 {
        return 0.0;
    }

    counts
        .values()
        .map(|count| {
            let p = *count as f64 / total as f64;
            if p == 0.0 { 0.0 } else { -p * p.log2() }
        })
        .sum()
}

fn ranks(values: &[(usize, f64)]) -> HashMap<usize, f64> {
    let mut sorted = values.to_vec();
    sorted.sort_by(|(_, left), (_, right)| compare_f64(left, right));

    let mut result = HashMap::new();
    let mut i = 0usize;
    while i < sorted.len() {
        let mut j = i + 1;
        while j < sorted.len() && (sorted[j].1 - sorted[i].1).abs() < 1e-12 {
            j += 1;
        }
        let avg_rank = (i + j - 1) as f64 / 2.0 + 1.0;
        for (index, _) in &sorted[i..j] {
            result.insert(*index, avg_rank);
        }
        i = j;
    }
    result
}

fn pearson_for_pairs(values: &[(f64, f64)]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let count = values.len() as f64;
    let left_mean = values.iter().map(|(left, _)| *left).sum::<f64>() / count;
    let right_mean = values.iter().map(|(_, right)| *right).sum::<f64>() / count;
    let mut covariance = 0.0;
    let mut left_var = 0.0;
    let mut right_var = 0.0;
    for (left, right) in values {
        let ld = *left - left_mean;
        let rd = *right - right_mean;
        covariance += ld * rd;
        left_var += ld * ld;
        right_var += rd * rd;
    }
    if left_var == 0.0 || right_var == 0.0 {
        0.0
    } else {
        covariance / (left_var.sqrt() * right_var.sqrt())
    }
}

fn looks_like_email(value: &str) -> bool {
    let value = value.trim();
    let parts = value.split('@').collect::<Vec<_>>();
    parts.len() == 2 && !parts[0].is_empty() && parts[1].contains('.')
}

fn looks_like_ip(value: &str) -> bool {
    value.parse::<std::net::Ipv4Addr>().is_ok() || value.parse::<std::net::Ipv6Addr>().is_ok()
}

fn looks_like_uuid(value: &str) -> bool {
    uuid::Uuid::parse_str(value).is_ok()
}

fn looks_like_url(value: &str) -> bool {
    let lower = value.trim().to_ascii_lowercase();
    lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("www.")
}

fn looks_like_phone(value: &str) -> bool {
    let trimmed = value.trim();
    if looks_like_ip(trimmed) || parse_datetime_string(trimmed).is_some() {
        return false;
    }

    let digits = trimmed.chars().filter(|ch| ch.is_ascii_digit()).count();
    let separator_count = trimmed.chars().filter(|ch| "+-() .".contains(*ch)).count();
    digits >= 7
        && separator_count >= 1
        && trimmed
            .chars()
            .all(|ch| ch.is_ascii_digit() || "+-() .".contains(ch))
}

fn looks_like_json(value: &str) -> bool {
    let trimmed = value.trim();
    (trimmed.starts_with('{') && trimmed.ends_with('}'))
        || (trimmed.starts_with('[') && trimmed.ends_with(']'))
}

fn looks_like_numeric_text(value: &str) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty() && trimmed.parse::<f64>().is_ok()
}

fn looks_like_boolean_text(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "true" | "false" | "yes" | "no" | "y" | "n" | "0" | "1"
    )
}

fn looks_like_hex(value: &str) -> bool {
    let trimmed = value.trim();
    let body = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        .unwrap_or(trimmed);
    body.len() >= 4 && body.chars().all(|ch| ch.is_ascii_hexdigit())
}

fn looks_like_base64(value: &str) -> bool {
    let trimmed = value.trim();
    if trimmed.len() < 8 || trimmed.len() % 4 != 0 {
        return false;
    }
    let pad_count = trimmed.chars().rev().take_while(|ch| *ch == '=').count();
    pad_count <= 2
        && trimmed
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '+' || ch == '/' || ch == '=')
}

fn looks_like_mac_address(value: &str) -> bool {
    let trimmed = value.trim();
    let separator = if trimmed.contains(':') {
        ':'
    } else if trimmed.contains('-') {
        '-'
    } else {
        return false;
    };
    let parts = trimmed.split(separator).collect::<Vec<_>>();
    parts.len() == 6
        && parts
            .iter()
            .all(|part| part.len() == 2 && part.chars().all(|ch| ch.is_ascii_hexdigit()))
}

fn looks_like_zip_code(value: &str) -> bool {
    let trimmed = value.trim();
    (trimmed.len() == 5 && trimmed.chars().all(|ch| ch.is_ascii_digit()))
        || (trimmed.len() == 10
            && trimmed.chars().enumerate().all(|(index, ch)| {
                if index == 5 {
                    ch == '-'
                } else {
                    ch.is_ascii_digit()
                }
            }))
}

fn jaccard_index(left: &HashSet<String>, right: &HashSet<String>) -> f64 {
    let union_count = left.union(right).count();
    if union_count == 0 {
        0.0
    } else {
        left.intersection(right).count() as f64 / union_count as f64
    }
}

fn categorical_chi_square(
    pair_counts: &HashMap<String, usize>,
    left_counts: &HashMap<String, usize>,
    right_counts: &HashMap<String, usize>,
    total: usize,
) -> f64 {
    if total == 0 {
        return 0.0;
    }

    pair_counts
        .iter()
        .filter_map(|(pair, observed)| {
            let (left, right) = pair.split_once(" | ")?;
            let expected =
                *left_counts.get(left)? as f64 * *right_counts.get(right)? as f64 / total as f64;
            if expected == 0.0 {
                None
            } else {
                Some((*observed as f64 - expected).powi(2) / expected)
            }
        })
        .sum()
}

fn collect_nested_stats(
    path: &str,
    value: &JsonValue,
    nested_stats: &mut BTreeMap<String, NestedAccumulator>,
) {
    let entry = nested_stats.entry(path.to_string()).or_default();
    entry.occurrence_count += 1;
    if value.is_null() {
        entry.null_count += 1;
    }
    *entry
        .observed_types
        .entry(classify_value(value))
        .or_default() += 1;

    match value {
        JsonValue::Object(map) => {
            for (key, child) in map {
                collect_nested_stats(&format!("{path}.{key}"), child, nested_stats);
            }
        }
        JsonValue::Array(items) => {
            for child in items {
                collect_nested_stats(&format!("{path}[]"), child, nested_stats);
            }
        }
        _ => {}
    }
}

fn semantic_hints(column: &ColumnStats) -> Vec<String> {
    let mut hints = Vec::new();

    if column
        .numeric_summary
        .as_ref()
        .is_some_and(|summary| summary.is_constant)
    {
        hints.push("constant_numeric".to_string());
    }
    if column
        .numeric_summary
        .as_ref()
        .is_some_and(|summary| summary.monotonic_increasing)
    {
        hints.push("monotonic_increasing".to_string());
    }
    if column
        .numeric_summary
        .as_ref()
        .is_some_and(|summary| summary.monotonic_decreasing)
    {
        hints.push("monotonic_decreasing".to_string());
    }
    if column.temporal_summary.is_some() {
        hints.push("temporal".to_string());
    }
    if let Some(summary) = &column.string_summary {
        if summary.email_like_count > 0 {
            hints.push("email_like".to_string());
        }
        if summary.ip_like_count > 0 {
            hints.push("ip_like".to_string());
        }
        if summary.uuid_like_count > 0 {
            hints.push("uuid_like".to_string());
        }
        if summary.url_like_count > 0 {
            hints.push("url_like".to_string());
        }
        if summary.phone_like_count > 0 {
            hints.push("phone_like".to_string());
        }
        if summary.json_like_count > 0 {
            hints.push("json_like".to_string());
        }
        if summary.mac_address_like_count > 0 {
            hints.push("mac_address_like".to_string());
        }
        if summary.zip_code_like_count > 0 {
            hints.push("zip_code_like".to_string());
        }
        if summary.hex_like_count > 0 {
            hints.push("hex_like".to_string());
        }
        if summary.base64_like_count > 0 {
            hints.push("base64_like".to_string());
        }
    }

    hints
}

fn percentile(sorted_values: &[f64], quantile: f64) -> f64 {
    if sorted_values.is_empty() {
        return 0.0;
    }

    if sorted_values.len() == 1 {
        return sorted_values[0];
    }

    let position = quantile * (sorted_values.len() - 1) as f64;
    let lower_index = position.floor() as usize;
    let upper_index = position.ceil() as usize;

    if lower_index == upper_index {
        sorted_values[lower_index]
    } else {
        let weight = position - lower_index as f64;
        sorted_values[lower_index] * (1.0 - weight) + sorted_values[upper_index] * weight
    }
}

fn ratio(numerator: usize, denominator: usize) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64
    }
}

fn compare_f64(left: &f64, right: &f64) -> Ordering {
    left.partial_cmp(right).unwrap_or(Ordering::Equal)
}

fn json_value_to_record(value: JsonValue) -> Result<Record> {
    match value {
        JsonValue::Object(map) => Ok(map),
        _ => bail!("expected a json object record"),
    }
}

fn parse_scalar_text(input: &str) -> JsonValue {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return JsonValue::Null;
    }

    if trimmed.eq_ignore_ascii_case("true") {
        return JsonValue::Bool(true);
    }

    if trimmed.eq_ignore_ascii_case("false") {
        return JsonValue::Bool(false);
    }

    if let Ok(value) = trimmed.parse::<i64>() {
        return JsonValue::Number(value.into());
    }

    if let Ok(value) = trimmed.parse::<u64>() {
        return JsonValue::Number(value.into());
    }

    if let Ok(value) = trimmed.parse::<f64>() {
        if let Some(number) = JsonNumber::from_f64(value) {
            return JsonValue::Number(number);
        }
    }

    JsonValue::String(trimmed.to_string())
}

fn parquet_row_to_record(row: &ParquetRow) -> Result<Record> {
    let mut record = Record::new();
    for (name, field) in row.get_column_iter() {
        record.insert(name.to_string(), parquet_field_to_json(field)?);
    }
    Ok(record)
}

fn parquet_field_to_json(field: &ParquetField) -> Result<JsonValue> {
    let value = match field {
        ParquetField::Null => JsonValue::Null,
        ParquetField::Bool(value) => JsonValue::Bool(*value),
        ParquetField::Byte(value) => JsonValue::Number((*value as i64).into()),
        ParquetField::Short(value) => JsonValue::Number((*value as i64).into()),
        ParquetField::Int(value) => JsonValue::Number((*value as i64).into()),
        ParquetField::Long(value) => JsonValue::Number((*value).into()),
        ParquetField::UByte(value) => JsonValue::Number((*value as u64).into()),
        ParquetField::UShort(value) => JsonValue::Number((*value as u64).into()),
        ParquetField::UInt(value) => JsonValue::Number((*value as u64).into()),
        ParquetField::ULong(value) => JsonValue::Number((*value).into()),
        ParquetField::Float16(value) => json_number_from_f64(f32::from(*value) as f64)?,
        ParquetField::Float(value) => json_number_from_f64(*value as f64)?,
        ParquetField::Double(value) => json_number_from_f64(*value)?,
        ParquetField::Str(value) => JsonValue::String(value.clone()),
        ParquetField::Bytes(value) => JsonValue::String(format!("{value:?}")),
        ParquetField::Decimal(value) => JsonValue::String(format!("{value:?}")),
        ParquetField::Date(value) => JsonValue::Number((*value as i64).into()),
        ParquetField::TimeMillis(value) => JsonValue::Number((*value as i64).into()),
        ParquetField::TimeMicros(value) => JsonValue::Number((*value).into()),
        ParquetField::TimestampMillis(value) => JsonValue::Number((*value).into()),
        ParquetField::TimestampMicros(value) => JsonValue::Number((*value).into()),
        ParquetField::Group(row) => parquet_row_to_json_object(row)?,
        ParquetField::ListInternal(list) => {
            let values = list
                .elements()
                .iter()
                .map(parquet_field_to_json)
                .collect::<Result<Vec<_>>>()?;
            JsonValue::Array(values)
        }
        ParquetField::MapInternal(map) => parquet_map_to_json(map)?,
    };

    Ok(value)
}

fn parquet_row_to_json_object(row: &ParquetRow) -> Result<JsonValue> {
    let mut map = JsonMap::new();
    for (name, field) in row.get_column_iter() {
        map.insert(name.to_string(), parquet_field_to_json(field)?);
    }
    Ok(JsonValue::Object(map))
}

fn parquet_map_to_json(map: &parquet::record::Map) -> Result<JsonValue> {
    let mut values = Vec::new();
    for (key, value) in map.entries() {
        values.push(JsonValue::Object(JsonMap::from_iter([
            ("key".to_string(), parquet_field_to_json(key)?),
            ("value".to_string(), parquet_field_to_json(value)?),
        ])));
    }
    Ok(JsonValue::Array(values))
}

fn avro_value_to_record(value: AvroValue) -> Result<Record> {
    match value {
        AvroValue::Record(fields) => {
            let mut record = Record::new();
            for (name, value) in fields {
                record.insert(name, avro_value_to_json(value)?);
            }
            Ok(record)
        }
        _ => bail!("expected avro record values"),
    }
}

fn avro_value_to_json(value: AvroValue) -> Result<JsonValue> {
    let json = match value {
        AvroValue::Null => JsonValue::Null,
        AvroValue::Boolean(value) => JsonValue::Bool(value),
        AvroValue::Int(value) => JsonValue::Number((value as i64).into()),
        AvroValue::Long(value) => JsonValue::Number(value.into()),
        AvroValue::Float(value) => json_number_from_f64(value as f64)?,
        AvroValue::Double(value) => json_number_from_f64(value)?,
        AvroValue::String(value) => JsonValue::String(value),
        AvroValue::Bytes(value) => JsonValue::Array(
            value
                .into_iter()
                .map(|item| JsonValue::Number((item as u64).into()))
                .collect(),
        ),
        AvroValue::Array(values) => JsonValue::Array(
            values
                .into_iter()
                .map(avro_value_to_json)
                .collect::<Result<Vec<_>>>()?,
        ),
        AvroValue::Map(values) => JsonValue::Object(
            values
                .into_iter()
                .map(|(key, value)| Ok((key, avro_value_to_json(value)?)))
                .collect::<Result<JsonMap<_, _>>>()?,
        ),
        AvroValue::Record(values) => JsonValue::Object(
            values
                .into_iter()
                .map(|(key, value)| Ok((key, avro_value_to_json(value)?)))
                .collect::<Result<JsonMap<_, _>>>()?,
        ),
        AvroValue::Union(_, boxed) => avro_value_to_json(*boxed)?,
        AvroValue::Enum(_, value) => JsonValue::String(value),
        AvroValue::Fixed(_, value) => JsonValue::Array(
            value
                .into_iter()
                .map(|item| JsonValue::Number((item as u64).into()))
                .collect(),
        ),
        AvroValue::Date(value) => JsonValue::Number((value as i64).into()),
        AvroValue::Decimal(value) => JsonValue::String(format!("{value:?}")),
        AvroValue::BigDecimal(value) => JsonValue::String(value.to_string()),
        AvroValue::TimeMillis(value) => JsonValue::Number((value as i64).into()),
        AvroValue::TimeMicros(value) => JsonValue::Number(value.into()),
        AvroValue::TimestampMillis(value) => JsonValue::Number(value.into()),
        AvroValue::TimestampMicros(value) => JsonValue::Number(value.into()),
        AvroValue::TimestampNanos(value) => JsonValue::Number(value.into()),
        AvroValue::LocalTimestampMillis(value) => JsonValue::Number(value.into()),
        AvroValue::LocalTimestampMicros(value) => JsonValue::Number(value.into()),
        AvroValue::LocalTimestampNanos(value) => JsonValue::Number(value.into()),
        AvroValue::Duration(value) => JsonValue::String(format!("{value:?}")),
        AvroValue::Uuid(value) => JsonValue::String(value.to_string()),
    };

    Ok(json)
}

fn json_number_from_f64(value: f64) -> Result<JsonValue> {
    JsonNumber::from_f64(value)
        .map(JsonValue::Number)
        .ok_or_else(|| anyhow!("cannot represent non-finite floating point value in json"))
}

fn format_label(format: DatasetFormat) -> &'static str {
    match format {
        DatasetFormat::Csv => "csv",
        DatasetFormat::Json => "json",
        DatasetFormat::Jsonl => "jsonl",
        DatasetFormat::Parquet => "parquet",
        DatasetFormat::Avro => "avro",
    }
}

fn column_notes(column: &ColumnStats) -> String {
    if let Some(summary) = &column.numeric_summary {
        return format!(
            "min={}, max={}, mean={:.3}, median={:.3}, p95={:.3}, dup_ratio={:.2}, outliers={}, entropy={:.2}",
            summary.min,
            summary.max,
            summary.mean,
            summary.median,
            summary.p95,
            summary.duplicate_ratio,
            summary.outlier_count_tukey,
            column.entropy
        );
    }

    if let Some(summary) = &column.string_summary {
        return format!(
            "min_len={}, max_len={}, avg_len={:.2}, empty={}, date_like={}, email_like={}, ip_like={}, url_like={}, json_like={}",
            summary.min_length,
            summary.max_length,
            summary.average_length,
            summary.empty_count,
            summary.date_like_count,
            summary.email_like_count,
            summary.ip_like_count,
            summary.url_like_count,
            summary.json_like_count
        );
    }

    if let Some(summary) = &column.boolean_summary {
        return format!(
            "true={}, false={}, true_ratio={:.2}",
            summary.true_count, summary.false_count, summary.true_ratio
        );
    }

    if column.value_type_counts.is_empty() {
        "no non-null values".to_string()
    } else {
        column
            .value_type_counts
            .iter()
            .map(|(kind, count)| format!("{kind}:{count}"))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn structure_notes(column: &ColumnStructure) -> String {
    if let Some(summary) = &column.array_summary {
        return format!(
            "array rows={}, len {}..{}, avg_len={:.2}",
            summary.row_count_with_arrays,
            summary.min_length,
            summary.max_length,
            summary.average_length
        );
    }

    if let Some(summary) = &column.object_summary {
        return format!(
            "object rows={}, keys {}..{}, avg_keys={:.2}",
            summary.row_count_with_objects,
            summary.key_count_min,
            summary.key_count_max,
            summary.average_key_count
        );
    }

    "flat scalar".to_string()
}

fn render_schema_markdown_rows(path: &str, node: &SchemaNode, output: &mut String) {
    let types = schema_type_labels(node).join(" | ");
    let hints = if node.semantic_hints.is_empty() {
        "-".to_string()
    } else {
        node.semantic_hints.join(", ")
    };
    let required = if path == "$" { "-" } else { "yes" };
    let _ = writeln!(
        output,
        "| {} | {} | {} | {} |",
        path, required, types, hints
    );

    if let Some(object) = &node.object {
        for field in &object.fields {
            let child_required = if field.required { "yes" } else { "no" };
            let child_types = schema_type_labels(&field.schema).join(" | ");
            let child_hints = if field.schema.semantic_hints.is_empty() {
                "-".to_string()
            } else {
                field.schema.semantic_hints.join(", ")
            };
            let child_path = format!("{path}.{}", field.name);
            let _ = writeln!(
                output,
                "| {} | {} | {} | {} |",
                child_path, child_required, child_types, child_hints
            );
            if field.schema.object.is_some() || field.schema.array.is_some() {
                render_schema_markdown_children(&child_path, &field.schema, output);
            }
        }
    }
}

fn render_schema_markdown_children(path: &str, node: &SchemaNode, output: &mut String) {
    if let Some(array) = &node.array {
        let array_path = format!("{path}[]");
        let types = schema_type_labels(&array.item).join(" | ");
        let hints = if array.item.semantic_hints.is_empty() {
            "-".to_string()
        } else {
            array.item.semantic_hints.join(", ")
        };
        let _ = writeln!(output, "| {} | - | {} | {} |", array_path, types, hints);
        if array.item.object.is_some() || array.item.array.is_some() {
            render_schema_markdown_children(&array_path, &array.item, output);
        }
    }

    if let Some(object) = &node.object {
        for field in &object.fields {
            let child_path = format!("{path}.{}", field.name);
            let child_required = if field.required { "yes" } else { "no" };
            let child_types = schema_type_labels(&field.schema).join(" | ");
            let child_hints = if field.schema.semantic_hints.is_empty() {
                "-".to_string()
            } else {
                field.schema.semantic_hints.join(", ")
            };
            let _ = writeln!(
                output,
                "| {} | {} | {} | {} |",
                child_path, child_required, child_types, child_hints
            );
            if field.schema.object.is_some() || field.schema.array.is_some() {
                render_schema_markdown_children(&child_path, &field.schema, output);
            }
        }
    }
}

fn json_schema_properties(node: &SchemaNode) -> JsonValue {
    let mut properties = JsonMap::new();
    if let Some(object) = &node.object {
        for field in &object.fields {
            properties.insert(field.name.clone(), json_schema_node(&field.schema));
        }
    }
    JsonValue::Object(properties)
}

fn json_schema_required(node: &SchemaNode) -> JsonValue {
    let required = node
        .object
        .as_ref()
        .map(|object| {
            object
                .fields
                .iter()
                .filter(|field| field.required)
                .map(|field| JsonValue::String(field.name.clone()))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    JsonValue::Array(required)
}

fn json_schema_node(node: &SchemaNode) -> JsonValue {
    let mut map = JsonMap::new();
    let types = schema_type_labels(node);
    if types.len() == 1 {
        map.insert("type".to_string(), JsonValue::String(types[0].clone()));
    } else {
        map.insert(
            "type".to_string(),
            JsonValue::Array(types.into_iter().map(JsonValue::String).collect()),
        );
    }
    if !node.semantic_hints.is_empty() {
        map.insert(
            "x-semantic-hints".to_string(),
            JsonValue::Array(
                node.semantic_hints
                    .iter()
                    .cloned()
                    .map(JsonValue::String)
                    .collect(),
            ),
        );
    }
    if let Some(object) = &node.object {
        map.insert(
            "properties".to_string(),
            JsonValue::Object(JsonMap::from_iter(
                object
                    .fields
                    .iter()
                    .map(|field| (field.name.clone(), json_schema_node(&field.schema))),
            )),
        );
        map.insert(
            "required".to_string(),
            JsonValue::Array(
                object
                    .fields
                    .iter()
                    .filter(|field| field.required)
                    .map(|field| JsonValue::String(field.name.clone()))
                    .collect(),
            ),
        );
    }
    if let Some(array) = &node.array {
        map.insert("items".to_string(), json_schema_node(&array.item));
    }
    JsonValue::Object(map)
}

fn openapi_schema_node(node: &SchemaNode) -> JsonValue {
    json_schema_node(node)
}

fn avro_schema_node(node: &SchemaNode, name: &str) -> JsonValue {
    let base = if let Some(object) = &node.object {
        JsonValue::Object(JsonMap::from_iter([
            ("type".to_string(), JsonValue::String("record".to_string())),
            ("name".to_string(), JsonValue::String(to_type_name(name))),
            (
                "fields".to_string(),
                JsonValue::Array(
                    object
                        .fields
                        .iter()
                        .map(|field| {
                            JsonValue::Object(JsonMap::from_iter([
                                ("name".to_string(), JsonValue::String(field.name.clone())),
                                (
                                    "type".to_string(),
                                    avro_field_type(
                                        &field.schema,
                                        &format!("{}_{}", name, field.name),
                                    ),
                                ),
                            ]))
                        })
                        .collect(),
                ),
            ),
        ]))
    } else if let Some(array) = &node.array {
        JsonValue::Object(JsonMap::from_iter([
            ("type".to_string(), JsonValue::String("array".to_string())),
            (
                "items".to_string(),
                avro_field_type(&array.item, &format!("{}_item", name)),
            ),
        ]))
    } else {
        avro_scalar_type(node)
    };

    if node.nullable {
        JsonValue::Array(vec![JsonValue::String("null".to_string()), base])
    } else {
        base
    }
}

fn avro_field_type(node: &SchemaNode, name: &str) -> JsonValue {
    avro_schema_node(node, name)
}

fn avro_scalar_type(node: &SchemaNode) -> JsonValue {
    let primary = primary_schema_kind(node).unwrap_or("string");
    JsonValue::String(
        match primary {
            "boolean" => "boolean",
            "number" => "double",
            "string" => "string",
            "array" => "array",
            "object" => "record",
            _ => "string",
        }
        .to_string(),
    )
}

fn typescript_object_body(object: Option<&ObjectSchema>) -> String {
    let Some(object) = object else {
        return "{\n  [key: string]: unknown;\n}".to_string();
    };
    let mut lines = String::from("{\n");
    for field in &object.fields {
        let optional = if field.required { "" } else { "?" };
        let _ = writeln!(
            &mut lines,
            "  {}{}: {};",
            field.name,
            optional,
            typescript_type(&field.schema)
        );
    }
    lines.push('}');
    lines
}

fn typescript_type(node: &SchemaNode) -> String {
    if let Some(object) = &node.object {
        return typescript_object_body(Some(object));
    }
    if let Some(array) = &node.array {
        return format!("{}[]", typescript_type(&array.item));
    }

    let mut kinds = schema_type_labels(node)
        .into_iter()
        .map(|kind| match kind.as_str() {
            "boolean" => "boolean".to_string(),
            "number" => "number".to_string(),
            "string" => "string".to_string(),
            "null" => "null".to_string(),
            _ => "unknown".to_string(),
        })
        .collect::<Vec<_>>();
    if kinds.is_empty() {
        kinds.push("unknown".to_string());
    }
    kinds.join(" | ")
}

fn python_object_body(object: Option<&ObjectSchema>, indent: usize) -> String {
    let Some(object) = object else {
        return format!("{}value: Any\n", "    ".repeat(indent));
    };
    if object.fields.is_empty() {
        return format!("{}pass\n", "    ".repeat(indent));
    }
    let mut body = String::new();
    for field in &object.fields {
        let _ = writeln!(
            &mut body,
            "{}{}: {}",
            "    ".repeat(indent),
            field.name,
            python_type(&field.schema, !field.required)
        );
    }
    body
}

fn python_type(node: &SchemaNode, optional: bool) -> String {
    let base = if let Some(object) = &node.object {
        format!(
            "Dict[str, Any]  # nested object with {} fields",
            object.fields.len()
        )
    } else if let Some(array) = &node.array {
        format!("List[{}]", python_type(&array.item, false))
    } else {
        match primary_schema_kind(node).unwrap_or("string") {
            "boolean" => "bool".to_string(),
            "number" => "float".to_string(),
            "string" => "str".to_string(),
            _ => "Any".to_string(),
        }
    };

    if optional || node.nullable {
        format!("Optional[{base}]")
    } else {
        base
    }
}

fn schema_type_labels(node: &SchemaNode) -> Vec<String> {
    let mut labels = node.kinds.keys().cloned().collect::<Vec<_>>();
    labels.sort();
    labels
}

fn primary_schema_kind(node: &SchemaNode) -> Option<&str> {
    node.kinds
        .iter()
        .filter(|(kind, _)| kind.as_str() != "null")
        .max_by_key(|(_, count)| *count)
        .map(|(kind, _)| kind.as_str())
}

fn default_schema_name(path: &Path) -> &str {
    path.file_stem()
        .and_then(|v| v.to_str())
        .unwrap_or("DatasetSchema")
}

fn to_type_name(input: &str) -> String {
    let mut output = String::new();
    let mut uppercase_next = true;
    for ch in input.chars() {
        if ch.is_ascii_alphanumeric() {
            if uppercase_next {
                output.push(ch.to_ascii_uppercase());
                uppercase_next = false;
            } else {
                output.push(ch);
            }
        } else {
            uppercase_next = true;
        }
    }
    if output.is_empty() {
        "DatasetSchema".to_string()
    } else {
        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn computes_extended_stats_from_sparse_records() {
        let records = vec![
            JsonMap::from_iter([
                ("id".to_string(), JsonValue::Number(1.into())),
                ("score".to_string(), JsonValue::Number(10.into())),
                ("name".to_string(), JsonValue::String("alice".to_string())),
                (
                    "category".to_string(),
                    JsonValue::String("group_a".to_string()),
                ),
                (
                    "event_date".to_string(),
                    JsonValue::String("2024-01-01".to_string()),
                ),
                (
                    "email".to_string(),
                    JsonValue::String("alice@example.com".to_string()),
                ),
                (
                    "profile_url".to_string(),
                    JsonValue::String("https://example.com/alice".to_string()),
                ),
                (
                    "payload".to_string(),
                    JsonValue::String("{\"role\":\"admin\"}".to_string()),
                ),
            ]),
            JsonMap::from_iter([
                ("id".to_string(), JsonValue::Number(2.into())),
                ("score".to_string(), JsonValue::Number(20.into())),
                ("name".to_string(), JsonValue::String("bob".to_string())),
                (
                    "category".to_string(),
                    JsonValue::String("group_b".to_string()),
                ),
                (
                    "event_date".to_string(),
                    JsonValue::String("2024-01-02".to_string()),
                ),
                (
                    "email".to_string(),
                    JsonValue::String("bob@example.com".to_string()),
                ),
                (
                    "profile_url".to_string(),
                    JsonValue::String("https://example.com/bob".to_string()),
                ),
                (
                    "payload".to_string(),
                    JsonValue::String("[1,2,3]".to_string()),
                ),
            ]),
            JsonMap::from_iter([
                ("id".to_string(), JsonValue::Number(3.into())),
                ("score".to_string(), JsonValue::Number(30.into())),
                ("name".to_string(), JsonValue::Null),
                (
                    "category".to_string(),
                    JsonValue::String("group_b".to_string()),
                ),
                (
                    "event_date".to_string(),
                    JsonValue::String("2024-01-03".to_string()),
                ),
                ("email".to_string(), JsonValue::String("".to_string())),
                (
                    "profile_url".to_string(),
                    JsonValue::String("www.example.com/charlie".to_string()),
                ),
                (
                    "payload".to_string(),
                    JsonValue::String("{\"role\":\"guest\"}".to_string()),
                ),
            ]),
        ];

        let stats = compute_stats(Path::new("sample.json"), DatasetFormat::Json, &records);
        assert_eq!(stats.row_count, 3);
        assert_eq!(stats.column_count, 8);

        let name_column = stats
            .columns
            .iter()
            .find(|column| column.name == "name")
            .unwrap();
        assert_eq!(name_column.non_null_count, 2);
        assert_eq!(name_column.null_count, 1);
        assert_eq!(name_column.missing_count, 0);
        assert_eq!(name_column.top_values.len(), 2);

        let score_column = stats
            .columns
            .iter()
            .find(|column| column.name == "score")
            .unwrap();
        let numeric = score_column.numeric_summary.as_ref().unwrap();
        assert_eq!(numeric.count, 3);
        assert_eq!(numeric.sum, 60.0);
        assert_eq!(numeric.median, 20.0);
        assert_eq!(numeric.p95, 29.0);
        assert_eq!(numeric.integer_like_count, 3);
        assert!(numeric.monotonic_increasing);
        assert!(!numeric.is_constant);

        let date_column = stats
            .columns
            .iter()
            .find(|column| column.name == "event_date")
            .unwrap();
        assert_eq!(
            date_column.string_summary.as_ref().unwrap().date_like_count,
            3
        );
        assert!(date_column.temporal_summary.is_some());

        let email_column = stats
            .columns
            .iter()
            .find(|column| column.name == "email")
            .unwrap();
        let email_summary = email_column.string_summary.as_ref().unwrap();
        assert_eq!(email_summary.email_like_count, 2);
        assert!(email_column.entropy > 0.0);

        let profile_url_column = stats
            .columns
            .iter()
            .find(|column| column.name == "profile_url")
            .unwrap();
        assert_eq!(
            profile_url_column
                .string_summary
                .as_ref()
                .unwrap()
                .url_like_count,
            3
        );

        let payload_column = stats
            .columns
            .iter()
            .find(|column| column.name == "payload")
            .unwrap();
        assert_eq!(
            payload_column
                .string_summary
                .as_ref()
                .unwrap()
                .json_like_count,
            3
        );

        let pair = stats
            .column_pairs
            .iter()
            .find(|pair| pair.left == "id" && pair.right == "score")
            .unwrap();
        assert_eq!(pair.paired_non_null_count, 3);
        assert_eq!(pair.shared_distinct_scalar_count, 0);
        let numeric_relationship = pair.numeric_relationship.as_ref().unwrap();
        assert!((numeric_relationship.pearson_correlation - 1.0).abs() < 1e-9);
        assert!((numeric_relationship.spearman_correlation - 1.0).abs() < 1e-9);
        assert!((numeric_relationship.r_squared - 1.0).abs() < 1e-9);

        let categorical_pair = stats
            .column_pairs
            .iter()
            .find(|pair| pair.left == "category" && pair.right == "email")
            .unwrap()
            .categorical_relationship
            .as_ref()
            .unwrap();
        assert_eq!(categorical_pair.distinct_pair_count, 3);
        assert!(categorical_pair.mutual_information >= 0.0);
        assert!(categorical_pair.cramers_v >= 0.0);
    }

    #[test]
    fn computes_structure_report_for_nested_records() {
        let records = vec![
            JsonMap::from_iter([
                (
                    "id".to_string(),
                    JsonValue::Number(serde_json::Number::from(1)),
                ),
                (
                    "profile".to_string(),
                    JsonValue::Object(JsonMap::from_iter([
                        (
                            "email".to_string(),
                            JsonValue::String("a@example.com".to_string()),
                        ),
                        ("active".to_string(), JsonValue::Bool(true)),
                    ])),
                ),
                (
                    "tags".to_string(),
                    JsonValue::Array(vec![
                        JsonValue::String("red".to_string()),
                        JsonValue::String("blue".to_string()),
                    ]),
                ),
            ]),
            JsonMap::from_iter([
                (
                    "id".to_string(),
                    JsonValue::Number(serde_json::Number::from(2)),
                ),
                (
                    "profile".to_string(),
                    JsonValue::Object(JsonMap::from_iter([
                        (
                            "email".to_string(),
                            JsonValue::String("b@example.com".to_string()),
                        ),
                        ("active".to_string(), JsonValue::Bool(false)),
                    ])),
                ),
                (
                    "tags".to_string(),
                    JsonValue::Array(vec![JsonValue::String("green".to_string())]),
                ),
            ]),
        ];

        let stats = compute_stats(Path::new("nested.json"), DatasetFormat::Json, &records);
        assert_eq!(stats.structure.nested_field_count, 6);

        let profile_column = stats
            .structure
            .columns
            .iter()
            .find(|column| column.name == "profile")
            .unwrap();
        assert!(profile_column.object_summary.is_some());

        let tags_column = stats
            .structure
            .columns
            .iter()
            .find(|column| column.name == "tags")
            .unwrap();
        let array_summary = tags_column.array_summary.as_ref().unwrap();
        assert_eq!(array_summary.min_length, 1);
        assert_eq!(array_summary.max_length, 2);

        let nested_email = stats
            .structure
            .nested_fields
            .iter()
            .find(|field| field.path == "profile.email")
            .unwrap();
        assert_eq!(nested_email.occurrence_count, 2);
        assert_eq!(
            nested_email
                .observed_types
                .get("string")
                .copied()
                .unwrap_or(0),
            2
        );
    }

    #[test]
    fn infers_schema_and_renders_multiple_formats() {
        let records = vec![
            JsonMap::from_iter([
                ("id".to_string(), JsonValue::Number(1.into())),
                (
                    "profile".to_string(),
                    JsonValue::Object(JsonMap::from_iter([
                        (
                            "email".to_string(),
                            JsonValue::String("a@example.com".to_string()),
                        ),
                        ("active".to_string(), JsonValue::Bool(true)),
                    ])),
                ),
                (
                    "tags".to_string(),
                    JsonValue::Array(vec![JsonValue::String("red".to_string())]),
                ),
            ]),
            JsonMap::from_iter([
                ("id".to_string(), JsonValue::Number(2.into())),
                (
                    "profile".to_string(),
                    JsonValue::Object(JsonMap::from_iter([(
                        "email".to_string(),
                        JsonValue::String("b@example.com".to_string()),
                    )])),
                ),
                ("tags".to_string(), JsonValue::Array(vec![JsonValue::Null])),
            ]),
        ];

        let schema = infer_schema(&records, DatasetFormat::Json, "sample dataset");
        let root_object = schema.root.object.as_ref().unwrap();
        assert_eq!(root_object.fields.len(), 3);
        let profile_field = root_object
            .fields
            .iter()
            .find(|field| field.name == "profile")
            .unwrap();
        assert!(profile_field.schema.object.is_some());

        let json_schema = render_schema_json_schema(&schema).unwrap();
        assert!(json_schema.contains("\"properties\""));
        assert!(json_schema.contains("\"profile\""));

        let openapi = render_schema_openapi(&schema).unwrap();
        assert!(openapi.contains("\"openapi\": \"3.1.0\""));

        let avro = render_schema_avro(&schema).unwrap();
        assert!(avro.contains("\"type\": \"record\""));

        let typescript = render_schema_typescript(&schema);
        assert!(typescript.contains("export interface SampleDataset"));

        let python = render_schema_python(&schema);
        assert!(python.contains("class SampleDataset"));
    }

    #[test]
    fn transforms_csv_to_parquet_and_reads_back() {
        let temp_root = unique_test_dir("csv-parquet");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("sample.csv");
        let output_path = temp_root.join("sample.parquet");
        std::fs::write(&input_path, "id,name,score\n1,alice,10\n2,bob,20\n").unwrap();

        let report = transform_dataset(&input_path, &output_path, None).unwrap();
        assert_eq!(report.source_format, DatasetFormat::Csv);
        assert_eq!(report.output_format, DatasetFormat::Parquet);
        assert!(output_path.exists());

        let transformed = load_records(&output_path, DatasetFormat::Parquet).unwrap();
        assert_eq!(transformed.len(), 2);
        assert_eq!(
            transformed[0].get("name"),
            Some(&JsonValue::String("alice".to_string()))
        );
        assert_eq!(
            transformed[1].get("score"),
            Some(&JsonValue::Number(20.into()))
        );

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn transforms_json_to_avro_and_reads_back() {
        let temp_root = unique_test_dir("json-avro");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("sample.json");
        let output_path = temp_root.join("sample.avro");
        let payload = serde_json::json!([
            { "id": 1, "name": "alice", "active": true, "meta": { "role": "admin" } },
            { "id": 2, "name": "bob", "active": false, "meta": { "role": "user" } }
        ]);
        std::fs::write(&input_path, serde_json::to_string_pretty(&payload).unwrap()).unwrap();

        let report = transform_dataset(&input_path, &output_path, None).unwrap();
        assert_eq!(report.source_format, DatasetFormat::Json);
        assert_eq!(report.output_format, DatasetFormat::Avro);
        assert!(output_path.exists());

        let transformed = load_records(&output_path, DatasetFormat::Avro).unwrap();
        assert_eq!(transformed.len(), 2);
        assert_eq!(transformed[0].get("active"), Some(&JsonValue::Bool(true)));
        assert_eq!(
            transformed[0].get("meta"),
            Some(&JsonValue::String("{\"role\":\"admin\"}".to_string()))
        );

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn previews_dataset_rows() {
        let temp_root = unique_test_dir("head");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("sample.jsonl");
        std::fs::write(
            &input_path,
            "{\"id\":1,\"name\":\"alice\"}\n{\"id\":2,\"name\":\"bob\"}\n{\"id\":3,\"name\":\"carol\"}\n",
        )
        .unwrap();

        let preview = preview_dataset(&input_path, 2).unwrap();
        assert_eq!(preview.total_row_count, 3);
        assert_eq!(preview.returned_row_count, 2);
        assert_eq!(preview.column_count, 2);
        assert_eq!(preview.columns, vec!["id".to_string(), "name".to_string()]);
        assert_eq!(
            preview.rows[1].get("name"),
            Some(&JsonValue::String("bob".to_string()))
        );

        let markdown = render_head_markdown(&preview);
        assert!(markdown.contains("# Dataset Head"));
        assert!(markdown.contains("| id | name |"));
        assert!(markdown.contains("alice"));

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn generates_smote_rows_for_minority_class() {
        let temp_root = unique_test_dir("smote");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("imbalanced.json");
        let output_path = temp_root.join("smote.json");
        let payload = serde_json::json!([
            { "x": 1.0, "y": 1.0, "class": "minority", "note": "a" },
            { "x": 1.2, "y": 1.1, "class": "minority", "note": "b" },
            { "x": 5.0, "y": 5.0, "class": "majority", "note": "c" },
            { "x": 5.2, "y": 5.1, "class": "majority", "note": "d" },
            { "x": 5.3, "y": 5.4, "class": "majority", "note": "e" }
        ]);
        std::fs::write(&input_path, serde_json::to_string_pretty(&payload).unwrap()).unwrap();

        let report = smote_dataset(
            &input_path,
            &output_path,
            None,
            "class",
            Some("minority"),
            None,
            None,
            5,
            Some(42),
            &[],
        )
        .unwrap();

        assert_eq!(report.synthetic_row_count, 5);
        assert_eq!(report.output_row_count, 10);
        assert_eq!(report.seed, Some(42));
        assert_eq!(
            report.feature_columns,
            vec!["x".to_string(), "y".to_string()]
        );
        assert_eq!(report.stats_diff.row_count_delta, 5);
        assert_eq!(
            report.evaluation.reference_population,
            "minority_reference_vs_synthetic"
        );
        assert_eq!(report.evaluation.reference_row_count, 2);
        assert_eq!(report.evaluation.synthetic_row_count, 5);
        assert_eq!(
            report.evaluation.feature_columns,
            vec!["x".to_string(), "y".to_string()]
        );
        assert!(report.evaluation.quality.propensity_mse >= 0.0);
        assert!(report.evaluation.quality.propensity_classifier_auc >= 0.0);
        assert!(report.evaluation.privacy.distance_to_closest_record.count > 0);
        assert!(
            report
                .evaluation
                .privacy
                .nearest_neighbor_distance_ratio
                .count
                > 0
        );
        assert_eq!(
            report.evaluation.privacy.rare_value_alerts.threshold,
            DEFAULT_RARE_VALUE_ALERT_THRESHOLD
        );
        assert!(report.evaluation.privacy.rare_value_alerts.reviewed_columns >= 1);
        assert!(
            report
                .evaluation
                .privacy
                .rare_value_alerts
                .columns_with_alerts
                >= 1
        );
        assert_eq!(report.evaluation.references.len(), 3);
        assert_eq!(report.evaluation.caveats.len(), 3);
        assert!(
            report
                .stats_diff
                .column_pairs
                .iter()
                .any(|pair| pair.left == "x"
                    && pair.right == "y"
                    && pair.numeric_relationship.is_some())
        );
        assert!(output_path.exists());

        let transformed = load_records(&output_path, DatasetFormat::Json).unwrap();
        let synthetic = &transformed[5..];
        for row in synthetic {
            assert_eq!(
                row.get("class"),
                Some(&JsonValue::String("minority".to_string()))
            );
            assert!(row.get("x").and_then(JsonValue::as_f64).unwrap() >= 1.0);
            assert!(row.get("x").and_then(JsonValue::as_f64).unwrap() <= 1.2);
            assert!(row.get("y").and_then(JsonValue::as_f64).unwrap() >= 1.0);
            assert!(row.get("y").and_then(JsonValue::as_f64).unwrap() <= 1.1);
        }

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn generates_smote_dataset_with_exact_target_rows() {
        let temp_root = unique_test_dir("smote-target-rows");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("imbalanced.json");
        let output_path = temp_root.join("smote-target.json");
        let payload = serde_json::json!([
            { "x": 1.0, "y": 1.0, "class": "minority", "note": "a" },
            { "x": 1.2, "y": 1.1, "class": "minority", "note": "b" },
            { "x": 5.0, "y": 5.0, "class": "majority", "note": "c" },
            { "x": 5.2, "y": 5.1, "class": "majority", "note": "d" },
            { "x": 5.3, "y": 5.4, "class": "majority", "note": "e" }
        ]);
        std::fs::write(&input_path, serde_json::to_string_pretty(&payload).unwrap()).unwrap();

        let report = smote_dataset(
            &input_path,
            &output_path,
            None,
            "class",
            Some("minority"),
            None,
            Some(5),
            5,
            Some(42),
            &[],
        )
        .unwrap();

        assert_eq!(report.synthetic_row_count, 5);
        assert_eq!(report.output_row_count, 5);
        let transformed = load_records(&output_path, DatasetFormat::Json).unwrap();
        assert_eq!(transformed.len(), 5);

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn generates_dp_noisy_dataset_for_numeric_columns() {
        let temp_root = unique_test_dir("dp-noise");
        std::fs::create_dir_all(&temp_root).unwrap();

        let input_path = temp_root.join("numeric.json");
        let output_path = temp_root.join("numeric-dp.json");
        let payload = serde_json::json!([
            { "id": 1, "x": 10.0, "y": 100.0, "class": "a" },
            { "id": 2, "x": 11.0, "y": 105.0, "class": "b" },
            { "id": 3, "x": 12.0, "y": 110.0, "class": "c" }
        ]);
        std::fs::write(&input_path, serde_json::to_string_pretty(&payload).unwrap()).unwrap();

        let report = dp_noise_dataset(&input_path, &output_path, None, 1.0, Some(42), &[]).unwrap();

        assert_eq!(report.row_count, 3);
        assert_eq!(report.seed, Some(42));
        assert!(report.noisy_columns.contains(&"id".to_string()));
        assert!(report.noisy_columns.contains(&"x".to_string()));
        assert!(report.noisy_columns.contains(&"y".to_string()));
        assert_eq!(report.stats_diff.row_count_delta, 0);
        assert_eq!(
            report.evaluation.reference_population,
            "full_dataset_vs_dp_noisy_dataset"
        );
        assert_eq!(report.evaluation.reference_row_count, 3);
        assert_eq!(report.evaluation.synthetic_row_count, 3);
        assert_eq!(
            report.evaluation.privacy.rare_value_alerts.reviewed_columns,
            1
        );
        assert_eq!(
            report
                .evaluation
                .privacy
                .rare_value_alerts
                .columns_with_alerts,
            1
        );
        assert_eq!(report.evaluation.caveats.len(), 4);
        assert!(output_path.exists());

        let transformed = load_records(&output_path, DatasetFormat::Json).unwrap();
        assert_eq!(transformed.len(), 3);
        assert_eq!(
            transformed[0].get("class"),
            Some(&JsonValue::String("a".to_string()))
        );
        assert!(
            transformed[0]
                .get("x")
                .and_then(JsonValue::as_f64)
                .is_some()
        );

        std::fs::remove_dir_all(&temp_root).unwrap();
    }

    #[test]
    fn flags_overlapping_rare_values_in_privacy_evaluation() {
        let reference = vec![
            JsonMap::from_iter([
                ("x".to_string(), JsonValue::Number(1.into())),
                ("diagnosis".to_string(), JsonValue::String("A".to_string())),
            ]),
            JsonMap::from_iter([
                ("x".to_string(), JsonValue::Number(2.into())),
                ("diagnosis".to_string(), JsonValue::String("A".to_string())),
            ]),
            JsonMap::from_iter([
                ("x".to_string(), JsonValue::Number(3.into())),
                ("diagnosis".to_string(), JsonValue::String("B".to_string())),
            ]),
            JsonMap::from_iter([
                ("x".to_string(), JsonValue::Number(4.into())),
                ("diagnosis".to_string(), JsonValue::String("C".to_string())),
            ]),
        ];
        let synthetic = vec![
            JsonMap::from_iter([
                (
                    "x".to_string(),
                    JsonValue::Number(JsonNumber::from_f64(1.1).unwrap()),
                ),
                ("diagnosis".to_string(), JsonValue::String("A".to_string())),
            ]),
            JsonMap::from_iter([
                (
                    "x".to_string(),
                    JsonValue::Number(JsonNumber::from_f64(2.1).unwrap()),
                ),
                ("diagnosis".to_string(), JsonValue::String("B".to_string())),
            ]),
            JsonMap::from_iter([
                (
                    "x".to_string(),
                    JsonValue::Number(JsonNumber::from_f64(3.1).unwrap()),
                ),
                ("diagnosis".to_string(), JsonValue::String("B".to_string())),
            ]),
            JsonMap::from_iter([
                (
                    "x".to_string(),
                    JsonValue::Number(JsonNumber::from_f64(4.1).unwrap()),
                ),
                ("diagnosis".to_string(), JsonValue::String("C".to_string())),
            ]),
        ];

        let report = evaluate_generation_records(
            "reference_vs_synthetic",
            &reference,
            &synthetic,
            &["x".to_string()],
            Vec::new(),
        )
        .unwrap();

        assert_eq!(report.privacy.rare_value_alerts.threshold, 5);
        assert_eq!(report.privacy.rare_value_alerts.reviewed_columns, 1);
        assert_eq!(report.privacy.rare_value_alerts.columns_with_alerts, 1);
        assert_eq!(report.privacy.rare_value_alerts.alerts.len(), 1);

        let alert = &report.privacy.rare_value_alerts.alerts[0];
        assert_eq!(alert.column, "diagnosis");
        assert_eq!(alert.reference_distinct_value_count, 3);
        assert_eq!(alert.synthetic_distinct_value_count, 3);
        assert_eq!(alert.reference_unique_value_count, 2);
        assert_eq!(alert.synthetic_unique_value_count, 2);
        assert_eq!(alert.reference_rare_value_count, 3);
        assert_eq!(alert.synthetic_rare_value_count, 3);
        assert_eq!(alert.overlapping_unique_value_count, 2);
        assert_eq!(alert.overlapping_rare_value_count, 3);
        assert_eq!(
            alert.overlapping_unique_examples,
            vec!["A".to_string(), "C".to_string()]
        );
        assert_eq!(
            alert.overlapping_rare_examples,
            vec!["A".to_string(), "B".to_string(), "C".to_string()]
        );
    }

    fn unique_test_dir(label: &str) -> std::path::PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("rata-transform-{label}-{nanos}"))
    }
}
