use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, ValueEnum};
use rata_core::{
    DatasetFormat, DiffusionGenerateOptions, DiffusionTrainOptions, analyze_dataset,
    analyze_schema, dp_noise_dataset, generate_from_diffusion_model, preview_dataset,
    render_head_markdown, render_markdown, render_schema_avro, render_schema_json,
    render_schema_json_schema, render_schema_markdown, render_schema_openapi, render_schema_python,
    render_schema_typescript, smote_dataset, train_diffusion_model, transform_dataset,
};

#[derive(Debug, Parser)]
#[command(name = "rata")]
#[command(about = "Dataset statistics reporting")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, clap::Subcommand)]
enum Command {
    Stats(StatsCommand),
    Schema(SchemaCommand),
    Head(HeadCommand),
    Transform(TransformCommand),
    Synth(SynthCommand),
    Train(TrainCommand),
    Gen(GenCommand),
}

#[derive(Debug, Parser)]
struct StatsCommand {
    #[arg(value_name = "DATASET_PATH")]
    path: PathBuf,
    #[arg(long, value_enum, default_value_t = OutputFormat::Markdown)]
    output: OutputFormat,
}

#[derive(Debug, Parser)]
struct SchemaCommand {
    #[arg(value_name = "DATASET_PATH")]
    path: PathBuf,
    #[arg(long, value_enum, default_value_t = SchemaFormat::Markdown)]
    format: SchemaFormat,
    #[arg(long)]
    name: Option<String>,
}

#[derive(Debug, Parser)]
struct TransformCommand {
    #[arg(value_name = "INPUT_PATH")]
    input: PathBuf,
    #[arg(value_name = "OUTPUT_PATH")]
    output: PathBuf,
    #[arg(long, value_enum)]
    format: Option<TransformFormat>,
}

#[derive(Debug, Parser)]
struct HeadCommand {
    #[arg(value_name = "DATASET_PATH")]
    path: PathBuf,
    #[arg(long, short = 'n', default_value_t = 5)]
    rows: usize,
    #[arg(long, value_enum, default_value_t = OutputFormat::Markdown)]
    output: OutputFormat,
}

#[derive(Debug, Parser)]
struct SynthCommand {
    #[command(subcommand)]
    command: SynthSubcommand,
}

#[derive(Debug, Parser)]
struct TrainCommand {
    #[command(subcommand)]
    command: TrainSubcommand,
}

#[derive(Debug, Parser)]
struct GenCommand {
    #[command(subcommand)]
    command: GenSubcommand,
}

#[derive(Debug, clap::Subcommand)]
enum SynthSubcommand {
    Smote(SmoteCommand),
    DpNoise(DpNoiseCommand),
}

#[derive(Debug, clap::Subcommand)]
enum TrainSubcommand {
    Df(TrainDiffusionCommand),
}

#[derive(Debug, clap::Subcommand)]
enum GenSubcommand {
    Df(GenerateDiffusionCommand),
}

#[derive(Debug, Parser)]
struct SmoteCommand {
    #[arg(value_name = "INPUT_PATH")]
    input: PathBuf,
    #[arg(value_name = "OUTPUT_PATH")]
    output: PathBuf,
    #[arg(long, value_name = "COLUMN")]
    target: String,
    #[arg(long, value_name = "LABEL")]
    minority_label: Option<String>,
    #[arg(long)]
    samples: Option<usize>,
    #[arg(long)]
    target_rows: Option<usize>,
    #[arg(long, default_value_t = 5)]
    k: usize,
    #[arg(long)]
    seed: Option<u64>,
    #[arg(long, value_delimiter = ',', value_name = "COLUMN")]
    features: Vec<String>,
    #[arg(long, value_enum)]
    format: Option<TransformFormat>,
}

#[derive(Debug, Parser)]
struct DpNoiseCommand {
    #[arg(value_name = "INPUT_PATH")]
    input: PathBuf,
    #[arg(value_name = "OUTPUT_PATH")]
    output: PathBuf,
    #[arg(long, default_value_t = 1.0)]
    epsilon: f64,
    #[arg(long)]
    seed: Option<u64>,
    #[arg(long, value_delimiter = ',', value_name = "COLUMN")]
    features: Vec<String>,
    #[arg(long, value_enum)]
    format: Option<TransformFormat>,
}

#[derive(Debug, Parser)]
struct TrainDiffusionCommand {
    #[arg(value_name = "DATASET_INPUT")]
    input: PathBuf,
    #[arg(value_name = "MODEL_OUTPUT")]
    output: Option<PathBuf>,
    #[arg(long, default_value_t = 100)]
    timesteps: usize,
    #[arg(long, default_value_t = 8)]
    examples_per_row: usize,
    #[arg(long, default_value_t = 1e-3)]
    ridge_alpha: f64,
    #[arg(long)]
    seed: Option<u64>,
    #[arg(long, value_delimiter = ',', value_name = "COLUMN")]
    features: Vec<String>,
}

#[derive(Debug, Parser)]
struct GenerateDiffusionCommand {
    #[arg(value_name = "MODEL")]
    model: PathBuf,
    #[arg(value_name = "DATASET_INPUT")]
    input: PathBuf,
    #[arg(value_name = "OUTPUT_PATH")]
    output: Option<PathBuf>,
    #[arg(long)]
    rows: Option<usize>,
    #[arg(long)]
    seed: Option<u64>,
    #[arg(long, value_enum)]
    format: Option<TransformFormat>,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum OutputFormat {
    Markdown,
    Json,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum SchemaFormat {
    Markdown,
    Json,
    JsonSchema,
    Openapi,
    Avro,
    Typescript,
    Python,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
enum TransformFormat {
    Csv,
    Json,
    Jsonl,
    Parquet,
    Avro,
}

impl From<TransformFormat> for DatasetFormat {
    fn from(value: TransformFormat) -> Self {
        match value {
            TransformFormat::Csv => DatasetFormat::Csv,
            TransformFormat::Json => DatasetFormat::Json,
            TransformFormat::Jsonl => DatasetFormat::Jsonl,
            TransformFormat::Parquet => DatasetFormat::Parquet,
            TransformFormat::Avro => DatasetFormat::Avro,
        }
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Command::Stats(command) => {
            let stats = analyze_dataset(&command.path)?;

            match command.output {
                OutputFormat::Markdown => {
                    println!("{}", render_markdown(&stats));
                }
                OutputFormat::Json => {
                    println!("{}", serde_json::to_string_pretty(&stats)?);
                }
            }
        }
        Command::Schema(command) => {
            let schema = analyze_schema(&command.path, command.name.as_deref())?;
            match command.format {
                SchemaFormat::Markdown => println!("{}", render_schema_markdown(&schema)),
                SchemaFormat::Json => println!("{}", render_schema_json(&schema)?),
                SchemaFormat::JsonSchema => println!("{}", render_schema_json_schema(&schema)?),
                SchemaFormat::Openapi => println!("{}", render_schema_openapi(&schema)?),
                SchemaFormat::Avro => println!("{}", render_schema_avro(&schema)?),
                SchemaFormat::Typescript => println!("{}", render_schema_typescript(&schema)),
                SchemaFormat::Python => println!("{}", render_schema_python(&schema)),
            }
        }
        Command::Head(command) => {
            let preview = preview_dataset(&command.path, command.rows)?;
            match command.output {
                OutputFormat::Markdown => println!("{}", render_head_markdown(&preview)),
                OutputFormat::Json => println!("{}", serde_json::to_string_pretty(&preview)?),
            }
        }
        Command::Transform(command) => {
            let report = transform_dataset(
                &command.input,
                &command.output,
                command.format.map(Into::into),
            )?;
            println!("{}", serde_json::to_string_pretty(&report)?);
        }
        Command::Synth(command) => match command.command {
            SynthSubcommand::Smote(command) => {
                let report = smote_dataset(
                    &command.input,
                    &command.output,
                    command.format.map(Into::into),
                    &command.target,
                    command.minority_label.as_deref(),
                    command.samples,
                    command.target_rows,
                    command.k,
                    command.seed,
                    &command.features,
                )?;
                println!("{}", serde_json::to_string_pretty(&report)?);
            }
            SynthSubcommand::DpNoise(command) => {
                let report = dp_noise_dataset(
                    &command.input,
                    &command.output,
                    command.format.map(Into::into),
                    command.epsilon,
                    command.seed,
                    &command.features,
                )?;
                println!("{}", serde_json::to_string_pretty(&report)?);
            }
        },
        Command::Train(command) => match command.command {
            TrainSubcommand::Df(command) => {
                let output_path = default_diffusion_model_path(&command.input, command.output);
                let report = train_diffusion_model(
                    &command.input,
                    &output_path,
                    DiffusionTrainOptions {
                        timesteps: command.timesteps,
                        train_examples_per_row: command.examples_per_row,
                        ridge_alpha: command.ridge_alpha,
                        seed: command.seed,
                        features: command.features,
                    },
                )?;
                println!("{}", serde_json::to_string_pretty(&report)?);
            }
        },
        Command::Gen(command) => match command.command {
            GenSubcommand::Df(command) => {
                let output_path = default_diffusion_generated_path(
                    &command.model,
                    &command.input,
                    command.output,
                );
                let report = generate_from_diffusion_model(
                    &command.model,
                    &command.input,
                    &output_path,
                    DiffusionGenerateOptions {
                        rows: command.rows,
                        seed: command.seed,
                        output_format: command.format.map(Into::into),
                    },
                )?;
                println!("{}", serde_json::to_string_pretty(&report)?);
            }
        },
    }

    Ok(())
}

fn default_diffusion_model_path(input: &std::path::Path, explicit: Option<PathBuf>) -> PathBuf {
    explicit.unwrap_or_else(|| {
        let stem = input
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("dataset");
        PathBuf::from("models").join(format!("{stem}.df.json"))
    })
}

fn default_diffusion_generated_path(
    model: &std::path::Path,
    input: &std::path::Path,
    explicit: Option<PathBuf>,
) -> PathBuf {
    explicit.unwrap_or_else(|| {
        let model_stem = model
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("model");
        let input_stem = input
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("dataset");
        PathBuf::from("datasets")
            .join("generated")
            .join(format!("{model_stem}-{input_stem}.json"))
    })
}
