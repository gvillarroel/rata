#!/usr/bin/env python3
"""Download compact 3M-row text dataset extracts for local testing.

The script uses the Hugging Face datasets-server API to find Parquet shards,
downloads one source shard at a time, keeps only selected text-bearing columns,
caps text field length, and writes local compressed Parquet files.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests


API_BASE = "https://datasets-server.huggingface.co"
DEFAULT_ROWS_PER_DATASET = 3_000_000
DEFAULT_TEXT_CHAR_LIMIT = 192
REQUEST_TIMEOUT_SECONDS = 120
DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024
WRITE_ROW_GROUP_SIZE = 65_536


@dataclass(frozen=True)
class DatasetSpec:
    slug: str
    dataset: str
    config: str
    split: str
    columns: tuple[str, ...]
    text_columns: tuple[str, ...]
    quality_note: str

    @property
    def dataset_url(self) -> str:
        return f"https://huggingface.co/datasets/{self.dataset}"


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        slug="amazon_polarity_reviews",
        dataset="fancyzhx/amazon_polarity",
        config="amazon_polarity",
        split="train",
        columns=("label", "title", "content"),
        text_columns=("title", "content"),
        quality_note="Amazon review polarity benchmark with review titles and bodies.",
    ),
    DatasetSpec(
        slug="amazon_asnq_qa_sentences",
        dataset="AmazonScience/asnq",
        config="default",
        split="train",
        columns=(
            "question",
            "sentence",
            "label",
            "sentence_in_long_answer",
            "short_answer_in_sentence",
        ),
        text_columns=("question", "sentence"),
        quality_note="Amazon Science answer sentence natural question corpus.",
    ),
    DatasetSpec(
        slug="amazon_tydi_as2_multilingual",
        dataset="AmazonScience/tydi-as2",
        config="default",
        split="train",
        columns=("Question", "Title", "Sentence", "Label"),
        text_columns=("Question", "Title", "Sentence"),
        quality_note="Amazon Science multilingual answer sentence selection corpus.",
    ),
    DatasetSpec(
        slug="msmarco_passages",
        dataset="Tevatron/msmarco-passage-corpus",
        config="default",
        split="train",
        columns=("docid", "title", "text"),
        text_columns=("title", "text"),
        quality_note="MS MARCO passage corpus packaged for Tevatron retrieval training.",
    ),
    DatasetSpec(
        slug="openmathinstruct2_solutions",
        dataset="nvidia/OpenMathInstruct-2",
        config="default",
        split="train",
        columns=(
            "problem",
            "generated_solution",
            "expected_answer",
            "problem_source",
        ),
        text_columns=("problem", "generated_solution", "expected_answer", "problem_source"),
        quality_note="NVIDIA math instruction corpus with problem and solution text.",
    ),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(session: requests.Session, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    response = session.get(
        f"{API_BASE}/{endpoint}",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def source_size_for_spec(session: requests.Session, spec: DatasetSpec) -> dict[str, Any]:
    payload = fetch_json(session, "size", {"dataset": spec.dataset})
    split = next(
        (
            item
            for item in payload.get("size", {}).get("splits", [])
            if item.get("config") == spec.config and item.get("split") == spec.split
        ),
        None,
    )
    if split is None:
        raise RuntimeError(f"No size entry for {spec.dataset}/{spec.config}/{spec.split}")

    dataset = payload.get("size", {}).get("dataset", {})
    return {
        "dataset_num_rows": dataset.get("num_rows"),
        "dataset_estimated_num_rows": dataset.get("estimated_num_rows"),
        "dataset_num_bytes_parquet_files": dataset.get("num_bytes_parquet_files"),
        "split_num_rows": split.get("num_rows"),
        "split_estimated_num_rows": split.get("estimated_num_rows"),
        "split_num_bytes_parquet_files": split.get("num_bytes_parquet_files"),
        "partial": payload.get("partial"),
    }


def parquet_files_for_spec(session: requests.Session, spec: DatasetSpec) -> list[dict[str, Any]]:
    payload = fetch_json(session, "parquet", {"dataset": spec.dataset})
    files = [
        item
        for item in payload.get("parquet_files", [])
        if item.get("config") == spec.config and item.get("split") == spec.split
    ]
    files.sort(key=lambda item: item.get("filename", ""))
    if not files:
        raise RuntimeError(f"No Parquet files for {spec.dataset}/{spec.config}/{spec.split}")
    return files


def download_file(session: requests.Session, url: str, target: Path) -> int:
    partial = target.with_suffix(target.suffix + ".partial")
    partial.unlink(missing_ok=True)
    with session.get(url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                if chunk:
                    handle.write(chunk)
    os.replace(partial, target)
    return target.stat().st_size


def truncate_text_array(array: pa.ChunkedArray | pa.Array, limit: int) -> pa.Array:
    combined = array.combine_chunks() if isinstance(array, pa.ChunkedArray) else array
    text = combined.cast(pa.string())
    if limit <= 0:
        return text
    return pc.utf8_slice_codeunits(text, 0, limit)


def update_text_stats(stats: dict[str, dict[str, int]], table: pa.Table, text_columns: tuple[str, ...]) -> None:
    for column in text_columns:
        array = table[column].combine_chunks()
        lengths = pc.utf8_length(array)
        max_length = pc.max(lengths).as_py()
        greater_than_100 = pc.greater(lengths, 100)
        greater_than_100 = pc.fill_null(greater_than_100, False)
        count_gt_100 = pc.sum(pc.cast(greater_than_100, pa.int64())).as_py() or 0

        column_stats = stats.setdefault(
            column,
            {
                "max_length": 0,
                "rows_longer_than_100": 0,
            },
        )
        if max_length is not None:
            column_stats["max_length"] = max(column_stats["max_length"], int(max_length))
        column_stats["rows_longer_than_100"] += int(count_gt_100)


def project_table(table: pa.Table, spec: DatasetSpec, text_char_limit: int) -> pa.Table:
    arrays: list[pa.Array | pa.ChunkedArray] = []
    for column in spec.columns:
        if column not in table.column_names:
            raise RuntimeError(f"Missing column {column!r} in {spec.dataset}")
        if column in spec.text_columns:
            arrays.append(truncate_text_array(table[column], text_char_limit))
        else:
            arrays.append(table[column])
    return pa.Table.from_arrays(arrays, names=list(spec.columns))


def write_dataset_extract(
    session: requests.Session,
    spec: DatasetSpec,
    rows_per_dataset: int,
    text_char_limit: int,
    output_dir: Path,
    force: bool,
) -> dict[str, Any]:
    output_path = output_dir / f"{spec.slug}.parquet"
    if output_path.exists() and not force:
        metadata_rows = pq.ParquetFile(output_path).metadata.num_rows
        if metadata_rows == rows_per_dataset:
            print(f"Reusing {output_path} ({metadata_rows} rows)")
            return verify_one_output(spec, output_path, rows_per_dataset)

    source_size = source_size_for_spec(session, spec)
    split_rows = source_size.get("split_num_rows") or source_size.get("split_estimated_num_rows")
    if split_rows is None or int(split_rows) < rows_per_dataset:
        raise RuntimeError(
            f"{spec.dataset}/{spec.config}/{spec.split} has {split_rows} rows, "
            f"less than the required {rows_per_dataset}"
        )

    parquet_files = parquet_files_for_spec(session, spec)
    partial_output = output_path.with_suffix(output_path.suffix + ".partial")
    partial_output.unlink(missing_ok=True)

    rows_written = 0
    source_files_used: list[dict[str, Any]] = []
    text_stats: dict[str, dict[str, int]] = {}
    writer: pq.ParquetWriter | None = None

    with tempfile.TemporaryDirectory(prefix=f"{spec.slug}-", dir=output_dir) as temp_root:
        temp_root_path = Path(temp_root)
        try:
            for file_index, item in enumerate(parquet_files):
                if rows_written >= rows_per_dataset:
                    break

                temp_path = temp_root_path / f"{file_index:04d}-{item.get('filename', 'shard.parquet')}"
                print(f"Downloading {spec.slug}: {item['filename']} ({rows_written}/{rows_per_dataset} rows)")
                downloaded_bytes = download_file(session, item["url"], temp_path)

                parquet = pq.ParquetFile(temp_path)
                source_rows_consumed = 0
                for row_group_index in range(parquet.num_row_groups):
                    if rows_written >= rows_per_dataset:
                        break
                    remaining = rows_per_dataset - rows_written
                    table = parquet.read_row_group(row_group_index, columns=list(spec.columns))
                    if table.num_rows > remaining:
                        table = table.slice(0, remaining)
                    table = project_table(table, spec, text_char_limit)
                    update_text_stats(text_stats, table, spec.text_columns)

                    if writer is None:
                        writer = pq.ParquetWriter(
                            partial_output,
                            table.schema,
                            compression="zstd",
                            compression_level=6,
                            use_dictionary=False,
                            write_statistics=True,
                        )
                    writer.write_table(table, row_group_size=WRITE_ROW_GROUP_SIZE)

                    rows_written += table.num_rows
                    source_rows_consumed += table.num_rows

                source_files_used.append(
                    {
                        "filename": item.get("filename"),
                        "url": item.get("url"),
                        "declared_size_bytes": item.get("size"),
                        "downloaded_size_bytes": downloaded_bytes,
                        "rows_consumed": source_rows_consumed,
                    }
                )
                temp_path.unlink(missing_ok=True)
        finally:
            if writer is not None:
                writer.close()

    if rows_written != rows_per_dataset:
        partial_output.unlink(missing_ok=True)
        raise RuntimeError(f"Wrote {rows_written} rows for {spec.slug}, expected {rows_per_dataset}")

    os.replace(partial_output, output_path)
    result = verify_one_output(spec, output_path, rows_per_dataset)
    result.update(
        {
            "source": asdict(spec),
            "source_size": source_size,
            "text_char_limit": text_char_limit,
            "source_files_used": source_files_used,
            "write_time_text_stats": text_stats,
        }
    )
    return result


def scan_text_stats(path: Path, text_columns: tuple[str, ...]) -> dict[str, dict[str, int]]:
    parquet = pq.ParquetFile(path)
    stats: dict[str, dict[str, int]] = {}
    for batch in parquet.iter_batches(
        batch_size=WRITE_ROW_GROUP_SIZE,
        columns=list(text_columns),
    ):
        table = pa.Table.from_batches([batch])
        update_text_stats(stats, table, text_columns)
    return stats


def verify_one_output(spec: DatasetSpec, path: Path, rows_per_dataset: int) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing local dataset file: {path}")

    parquet = pq.ParquetFile(path)
    missing_columns = [column for column in spec.columns if column not in parquet.schema_arrow.names]
    if missing_columns:
        raise RuntimeError(f"{path} is missing columns: {missing_columns}")

    row_count = parquet.metadata.num_rows
    if row_count != rows_per_dataset:
        raise RuntimeError(f"{path} has {row_count} rows, expected {rows_per_dataset}")

    text_stats = scan_text_stats(path, spec.text_columns)
    has_long_text_field = any(
        stats.get("max_length", 0) > 100 and stats.get("rows_longer_than_100", 0) > 0
        for stats in text_stats.values()
    )
    return {
        "slug": spec.slug,
        "local_path": str(path),
        "local_size_bytes": path.stat().st_size,
        "row_count": row_count,
        "columns": list(parquet.schema_arrow.names),
        "text_columns": list(spec.text_columns),
        "text_stats": text_stats,
        "has_text_field_longer_than_100": has_long_text_field,
    }


def write_manifest(
    output_dir: Path,
    rows_per_dataset: int,
    text_char_limit: int,
    results: list[dict[str, Any]],
) -> Path:
    long_text_dataset_count = sum(
        1 for result in results if result.get("has_text_field_longer_than_100")
    )
    manifest = {
        "generated_at_utc": utc_now_iso(),
        "api_base": API_BASE,
        "rows_per_dataset": rows_per_dataset,
        "text_char_limit": text_char_limit,
        "dataset_count": len(results),
        "long_text_dataset_count": long_text_dataset_count,
        "meets_definition_of_done": (
            len(results) >= 5
            and all(result.get("row_count", 0) >= rows_per_dataset for result in results)
            and long_text_dataset_count >= 2
        ),
        "results": results,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def verify_all(output_dir: Path, rows_per_dataset: int) -> list[dict[str, Any]]:
    results = [
        verify_one_output(spec, output_dir / f"{spec.slug}.parquet", rows_per_dataset)
        for spec in DATASETS
    ]
    long_text_dataset_count = sum(
        1 for result in results if result.get("has_text_field_longer_than_100")
    )
    if len(results) < 5:
        raise RuntimeError(f"Only {len(results)} datasets verified; expected at least 5")
    if any(result["row_count"] < rows_per_dataset for result in results):
        raise RuntimeError(f"At least one dataset has fewer than {rows_per_dataset} rows")
    if long_text_dataset_count < 2:
        raise RuntimeError(
            f"Only {long_text_dataset_count} datasets have a text field longer than 100 chars"
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="datasets/text-large",
        help="Directory for local Parquet extracts and manifest.",
    )
    parser.add_argument(
        "--rows-per-dataset",
        type=int,
        default=DEFAULT_ROWS_PER_DATASET,
        help="Rows to keep from each source split.",
    )
    parser.add_argument(
        "--text-char-limit",
        type=int,
        default=DEFAULT_TEXT_CHAR_LIMIT,
        help="Maximum codepoint length retained in each text column.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate output Parquet files even when the expected row count already exists.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing outputs and rewrite the manifest without downloading.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.rows_per_dataset < DEFAULT_ROWS_PER_DATASET:
        raise RuntimeError(
            f"--rows-per-dataset must be at least {DEFAULT_ROWS_PER_DATASET} "
            "to satisfy the current definition of done"
        )

    if args.verify_only:
        results = verify_all(output_dir, args.rows_per_dataset)
        manifest_path = write_manifest(
            output_dir,
            args.rows_per_dataset,
            args.text_char_limit,
            results,
        )
        print(f"Verified large text datasets. Manifest: {manifest_path}")
        return 0

    session = requests.Session()
    session.headers.update({"User-Agent": "rata-large-text-dataset-downloader/1.0"})

    results: list[dict[str, Any]] = []
    try:
        for spec in DATASETS:
            result = write_dataset_extract(
                session=session,
                spec=spec,
                rows_per_dataset=args.rows_per_dataset,
                text_char_limit=args.text_char_limit,
                output_dir=output_dir,
                force=args.force,
            )
            results.append(result)

        results = verify_all(output_dir, args.rows_per_dataset)
        manifest_path = write_manifest(
            output_dir,
            args.rows_per_dataset,
            args.text_char_limit,
            results,
        )
        print(f"Prepared large text datasets. Manifest: {manifest_path}")
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
