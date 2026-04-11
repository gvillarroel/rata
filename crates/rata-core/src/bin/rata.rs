use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, ValueEnum};
use rata_core::{
    DatasetFormat, analyze_dataset, analyze_schema, dp_noise_dataset, preview_dataset,
    render_head_markdown, render_markdown, render_schema_avro, render_schema_json,
    render_schema_json_schema, render_schema_markdown, render_schema_openapi, render_schema_python,
    render_schema_typescript, smote_dataset, transform_dataset,
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

#[derive(Debug, clap::Subcommand)]
enum SynthSubcommand {
    Smote(SmoteCommand),
    DpNoise(DpNoiseCommand),
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
    }

    Ok(())
}
