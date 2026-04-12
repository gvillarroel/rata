mod linear;
mod preprocess;
mod schedule;

use std::fs::File;
use std::io::{BufReader, BufWriter};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use nalgebra::{DMatrix, DVector};
use rand::{Rng, SeedableRng, rngs::StdRng};
use serde::{Deserialize, Serialize};

use crate::{DatasetFormat, analyze_dataset, load_records, write_records};

use self::linear::{fit_ridge_multi_target, predict_row};
use self::preprocess::{FeatureSelection, build_output_records, prepare_numeric_dataset};
use self::schedule::DiffusionSchedule;

#[derive(Debug, Clone, Serialize)]
pub struct DiffusionTrainOptions {
    pub timesteps: usize,
    pub train_examples_per_row: usize,
    pub ridge_alpha: f64,
    pub seed: Option<u64>,
    pub features: Vec<String>,
}

impl Default for DiffusionTrainOptions {
    fn default() -> Self {
        Self {
            timesteps: 100,
            train_examples_per_row: 8,
            ridge_alpha: 1e-3,
            seed: None,
            features: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffusionGenerateOptions {
    pub rows: Option<usize>,
    pub seed: Option<u64>,
    pub output_format: Option<DatasetFormat>,
}

impl Default for DiffusionGenerateOptions {
    fn default() -> Self {
        Self {
            rows: None,
            seed: None,
            output_format: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffusionModelArtifact {
    pub version: String,
    pub method: String,
    pub source_path: PathBuf,
    pub timesteps: usize,
    pub feature_count: usize,
    pub numeric_columns: Vec<String>,
    pub passthrough_columns: Vec<String>,
    pub means: Vec<f64>,
    pub stddevs: Vec<f64>,
    pub mins: Vec<f64>,
    pub maxs: Vec<f64>,
    pub schedule: DiffusionSchedule,
    pub denoiser: LinearDenoiser,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinearDenoiser {
    pub input_dim: usize,
    pub output_dim: usize,
    pub weights: DMatrix<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffusionTrainReport {
    pub source_path: PathBuf,
    pub model_output_path: PathBuf,
    pub timesteps: usize,
    pub row_count: usize,
    pub numeric_columns: Vec<String>,
    pub passthrough_columns: Vec<String>,
    pub training_example_count: usize,
    pub ridge_alpha: f64,
    pub seed: Option<u64>,
    pub training_mse: f64,
    pub references: Vec<DiffusionReference>,
    pub caveats: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffusionGenerateReport {
    pub model_path: PathBuf,
    pub reference_dataset_path: PathBuf,
    pub output_path: PathBuf,
    pub output_format: DatasetFormat,
    pub generated_row_count: usize,
    pub numeric_columns: Vec<String>,
    pub passthrough_columns: Vec<String>,
    pub seed: Option<u64>,
    pub generated_stats: crate::DatasetStats,
    pub caveats: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DiffusionReference {
    pub citation: String,
    pub url: String,
    pub note: String,
}

pub fn train_diffusion_model(
    dataset_input: impl AsRef<Path>,
    model_output_path: impl AsRef<Path>,
    options: DiffusionTrainOptions,
) -> Result<DiffusionTrainReport> {
    if options.timesteps < 2 {
        bail!("timesteps must be at least 2");
    }
    if options.train_examples_per_row == 0 {
        bail!("train_examples_per_row must be greater than zero");
    }
    if options.ridge_alpha <= 0.0 {
        bail!("ridge_alpha must be greater than zero");
    }

    let input_path = dataset_input.as_ref();
    let format = DatasetFormat::detect(input_path)?;
    let records = load_records(input_path, format)?;
    let dataset = prepare_numeric_dataset(
        &records,
        &FeatureSelection::ExplicitOrAuto(&options.features),
    )?;
    if dataset.numeric.columns.is_empty() {
        bail!("diffusion training requires at least one numeric column");
    }

    let schedule = DiffusionSchedule::linear(options.timesteps, 1e-4, 0.02);
    let input_dim = dataset.numeric.columns.len() + 3;
    let output_dim = dataset.numeric.columns.len();
    let total_examples = dataset.numeric.matrix.nrows() * options.train_examples_per_row;

    let mut x_train = DMatrix::zeros(total_examples, input_dim);
    let mut y_train = DMatrix::zeros(total_examples, output_dim);

    let mut rng = diffusion_rng(options.seed);
    let mut row_index = 0usize;
    for row in 0..dataset.numeric.matrix.nrows() {
        let x0 = dataset.numeric.matrix.row(row).transpose();
        for _ in 0..options.train_examples_per_row {
            let timestep = rng.random_range(0..options.timesteps);
            let alpha_bar = schedule.alpha_bars[timestep];
            let sqrt_alpha_bar = alpha_bar.sqrt();
            let sqrt_one_minus_alpha_bar = (1.0 - alpha_bar).sqrt();

            let noise = gaussian_vector(output_dim, &mut rng);
            let xt = x0.scale(sqrt_alpha_bar) + noise.scale(sqrt_one_minus_alpha_bar);
            let features = timestep_features(timestep, options.timesteps);

            for feature_index in 0..output_dim {
                x_train[(row_index, feature_index)] = xt[feature_index];
                y_train[(row_index, feature_index)] = noise[feature_index];
            }
            x_train[(row_index, output_dim)] = features[0];
            x_train[(row_index, output_dim + 1)] = features[1];
            x_train[(row_index, output_dim + 2)] = features[2];
            row_index += 1;
        }
    }

    let weights = fit_ridge_multi_target(&x_train, &y_train, options.ridge_alpha)
        .context("failed to fit diffusion denoiser")?;
    let training_predictions = &x_train * &weights;
    let mse = mean_squared_error(&training_predictions, &y_train);

    let artifact = DiffusionModelArtifact {
        version: "0.1.0".to_string(),
        method: "tabular_gaussian_ddpm_linear".to_string(),
        source_path: input_path.to_path_buf(),
        timesteps: options.timesteps,
        feature_count: output_dim,
        numeric_columns: dataset.numeric.columns.clone(),
        passthrough_columns: dataset.passthrough_columns.clone(),
        means: dataset.numeric.means.clone(),
        stddevs: dataset.numeric.stddevs.clone(),
        mins: dataset.numeric.mins.clone(),
        maxs: dataset.numeric.maxs.clone(),
        schedule,
        denoiser: LinearDenoiser {
            input_dim,
            output_dim,
            weights,
        },
    };

    write_model_artifact(model_output_path.as_ref(), &artifact)?;

    Ok(DiffusionTrainReport {
        source_path: input_path.to_path_buf(),
        model_output_path: model_output_path.as_ref().to_path_buf(),
        timesteps: options.timesteps,
        row_count: records.len(),
        numeric_columns: artifact.numeric_columns.clone(),
        passthrough_columns: artifact.passthrough_columns.clone(),
        training_example_count: total_examples,
        ridge_alpha: options.ridge_alpha,
        seed: options.seed,
        training_mse: mse,
        references: diffusion_references(),
        caveats: diffusion_training_caveats(),
    })
}

pub fn generate_from_diffusion_model(
    model_path: impl AsRef<Path>,
    reference_dataset_input: impl AsRef<Path>,
    output_path: impl AsRef<Path>,
    options: DiffusionGenerateOptions,
) -> Result<DiffusionGenerateReport> {
    let model = read_model_artifact(model_path.as_ref())?;
    let reference_path = reference_dataset_input.as_ref();
    let reference_format = DatasetFormat::detect(reference_path)?;
    let reference_records = load_records(reference_path, reference_format)?;
    if reference_records.is_empty() {
        bail!("reference dataset is empty");
    }
    let reference_view = prepare_numeric_dataset(
        &reference_records,
        &FeatureSelection::Exact(&model.numeric_columns),
    )?;
    if reference_view.numeric.columns != model.numeric_columns {
        bail!("reference dataset numeric columns do not match the trained model");
    }

    let row_count = options.rows.unwrap_or(reference_records.len());
    let output_format = options
        .output_format
        .unwrap_or(DatasetFormat::detect(output_path.as_ref())?);
    let mut rng = diffusion_rng(options.seed);
    let generated_numeric = sample_numeric_matrix(&model, row_count, &mut rng);
    let generated_records = build_output_records(
        &reference_records,
        &reference_view,
        &generated_numeric,
        &model.passthrough_columns,
        &mut rng,
    )?;

    if let Some(parent) = output_path.as_ref().parent() {
        std::fs::create_dir_all(parent)?;
    }
    write_records(output_path.as_ref(), output_format, &generated_records)?;
    let generated_stats = analyze_dataset(output_path.as_ref())?;

    Ok(DiffusionGenerateReport {
        model_path: model_path.as_ref().to_path_buf(),
        reference_dataset_path: reference_path.to_path_buf(),
        output_path: output_path.as_ref().to_path_buf(),
        output_format,
        generated_row_count: generated_records.len(),
        numeric_columns: model.numeric_columns,
        passthrough_columns: model.passthrough_columns,
        seed: options.seed,
        generated_stats,
        caveats: diffusion_generation_caveats(),
    })
}

fn sample_numeric_matrix(
    model: &DiffusionModelArtifact,
    row_count: usize,
    rng: &mut StdRng,
) -> DMatrix<f64> {
    let mut current = DMatrix::from_fn(row_count, model.feature_count, |_, _| {
        sample_standard_normal(rng)
    });
    for timestep in (0..model.timesteps).rev() {
        let alpha = model.schedule.alphas[timestep];
        let alpha_bar = model.schedule.alpha_bars[timestep];
        let beta = model.schedule.betas[timestep];
        let time_features = timestep_features(timestep, model.timesteps);

        for row in 0..row_count {
            let xt = current.row(row).transpose();
            let eps_pred = predict_epsilon(&model.denoiser, &xt, time_features);
            let coeff = beta / (1.0 - alpha_bar).sqrt();
            let mut x_prev = (xt - eps_pred.scale(coeff)).scale(1.0 / alpha.sqrt());
            if timestep > 0 {
                let noise = gaussian_vector(model.feature_count, rng).scale(beta.sqrt());
                x_prev += noise;
            }
            for col in 0..model.feature_count {
                let value = destandardize_and_clip(
                    x_prev[col],
                    model.means[col],
                    model.stddevs[col],
                    model.mins[col],
                    model.maxs[col],
                );
                current[(row, col)] = standardize(value, model.means[col], model.stddevs[col]);
            }
        }
    }

    DMatrix::from_fn(row_count, model.feature_count, |row, col| {
        destandardize_and_clip(
            current[(row, col)],
            model.means[col],
            model.stddevs[col],
            model.mins[col],
            model.maxs[col],
        )
    })
}

fn predict_epsilon(
    denoiser: &LinearDenoiser,
    xt: &DVector<f64>,
    time_features: [f64; 3],
) -> DVector<f64> {
    let mut input = DVector::zeros(denoiser.input_dim);
    for index in 0..xt.len() {
        input[index] = xt[index];
    }
    input[xt.len()] = time_features[0];
    input[xt.len() + 1] = time_features[1];
    input[xt.len() + 2] = time_features[2];
    predict_row(&denoiser.weights, &input)
}

fn timestep_features(timestep: usize, total_steps: usize) -> [f64; 3] {
    let normalized = timestep as f64 / total_steps.max(1) as f64;
    [
        normalized,
        (std::f64::consts::TAU * normalized).sin(),
        (std::f64::consts::TAU * normalized).cos(),
    ]
}

fn write_model_artifact(path: &Path, model: &DiffusionModelArtifact) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let writer = BufWriter::new(File::create(path)?);
    serde_json::to_writer_pretty(writer, model)?;
    Ok(())
}

fn read_model_artifact(path: &Path) -> Result<DiffusionModelArtifact> {
    let reader = BufReader::new(File::open(path)?);
    Ok(serde_json::from_reader(reader)?)
}

fn diffusion_rng(seed: Option<u64>) -> StdRng {
    match seed {
        Some(seed) => StdRng::seed_from_u64(seed),
        None => StdRng::from_os_rng(),
    }
}

fn gaussian_vector(size: usize, rng: &mut StdRng) -> DVector<f64> {
    DVector::from_fn(size, |_, _| sample_standard_normal(rng))
}

fn sample_standard_normal(rng: &mut StdRng) -> f64 {
    let u1 = (1.0 - rng.random::<f64>()).max(f64::MIN_POSITIVE);
    let u2 = rng.random::<f64>();
    (-2.0 * u1.ln()).sqrt() * (std::f64::consts::TAU * u2).cos()
}

fn mean_squared_error(predicted: &DMatrix<f64>, target: &DMatrix<f64>) -> f64 {
    let mut total = 0.0;
    for row in 0..predicted.nrows() {
        for col in 0..predicted.ncols() {
            let delta = predicted[(row, col)] - target[(row, col)];
            total += delta * delta;
        }
    }
    total / (predicted.nrows() * predicted.ncols()).max(1) as f64
}

fn destandardize_and_clip(value: f64, mean: f64, stddev: f64, min: f64, max: f64) -> f64 {
    (value * stddev + mean).clamp(min, max)
}

fn standardize(value: f64, mean: f64, stddev: f64) -> f64 {
    (value - mean) / stddev.max(1e-9)
}

fn diffusion_references() -> Vec<DiffusionReference> {
    vec![
        DiffusionReference {
            citation: "Ho et al. (2020), Denoising Diffusion Probabilistic Models".to_string(),
            url: "https://arxiv.org/abs/2006.11239".to_string(),
            note: "Core Gaussian diffusion training and sampling equations.".to_string(),
        },
        DiffusionReference {
            citation: "Kotelnikov et al. (2023), TabDDPM: Modelling Tabular Data with Diffusion Models".to_string(),
            url: "https://arxiv.org/abs/2209.15421".to_string(),
            note: "Tabular diffusion reference for Gaussian numerical diffusion and mixed-type extensions.".to_string(),
        },
        DiffusionReference {
            citation: "Villaizan-Vallelado et al. (2024), Diffusion Models for Tabular Data Imputation and Synthetic Data Generation".to_string(),
            url: "https://arxiv.org/abs/2407.02549".to_string(),
            note: "Reference for separate numerical and categorical diffusion paths and modular denoising architecture.".to_string(),
        },
    ]
}

fn diffusion_training_caveats() -> Vec<String> {
    vec![
        "This first Rust implementation models numeric columns with Gaussian diffusion and treats non-numeric columns as passthrough metadata for generation time.".to_string(),
        "The denoiser is intentionally linear so the training path stays lightweight and modular. A deeper MLP or transformer denoiser can replace it later without changing the CLI contract.".to_string(),
    ]
}

fn diffusion_generation_caveats() -> Vec<String> {
    vec![
        "Generated numeric columns are synthetic samples from the trained diffusion model.".to_string(),
        "Passthrough columns are bootstrapped from the reference dataset during generation. Full categorical diffusion is a later extension.".to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::json;

    use super::*;
    use crate::JsonValue;

    #[test]
    fn trains_and_generates_numeric_diffusion_model() {
        let temp_root = unique_test_dir("diffusion");
        fs::create_dir_all(&temp_root).unwrap();
        let input_path = temp_root.join("input.json");
        let model_path = temp_root.join("model.json");
        let output_path = temp_root.join("generated.json");
        let payload = json!([
            { "age": 21.0, "income": 1000.0, "segment": "a" },
            { "age": 25.0, "income": 1200.0, "segment": "b" },
            { "age": 31.0, "income": 1800.0, "segment": "a" },
            { "age": 35.0, "income": 2200.0, "segment": "c" }
        ]);
        fs::write(&input_path, serde_json::to_string_pretty(&payload).unwrap()).unwrap();

        let train_report = train_diffusion_model(
            &input_path,
            &model_path,
            DiffusionTrainOptions {
                timesteps: 16,
                train_examples_per_row: 4,
                ridge_alpha: 1e-3,
                seed: Some(42),
                features: Vec::new(),
            },
        )
        .unwrap();
        assert_eq!(
            train_report.numeric_columns,
            vec!["age".to_string(), "income".to_string()]
        );
        assert_eq!(
            train_report.passthrough_columns,
            vec!["segment".to_string()]
        );

        let gen_report = generate_from_diffusion_model(
            &model_path,
            &input_path,
            &output_path,
            DiffusionGenerateOptions {
                rows: Some(6),
                seed: Some(7),
                output_format: None,
            },
        )
        .unwrap();

        assert_eq!(gen_report.generated_row_count, 6);
        assert!(output_path.exists());
        let generated = load_records(&output_path, DatasetFormat::Json).unwrap();
        assert_eq!(generated.len(), 6);
        assert!(
            generated
                .iter()
                .all(|row| row.get("age").and_then(JsonValue::as_f64).is_some())
        );
        assert!(generated.iter().all(|row| row.get("segment").is_some()));

        fs::remove_dir_all(&temp_root).unwrap();
    }

    fn unique_test_dir(label: &str) -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("rata-diffusion-{label}-{nanos}"))
    }
}
