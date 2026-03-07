from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .ingestion import ingest_workbook
from .metrics import compute_metrics
from .models import PipelineOutput, RunContext
from .normalization import normalize_rows
from .reporting import generate_report
from .storage import DatabaseStorage
from .utils import ensure_dir, file_sha256


def build_run_context(input_path: Path, output_dir: Path, run_date: str | None) -> RunContext:
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    file_hash = file_sha256(input_path)
    resolved_run_date = run_date or now.date().isoformat()
    run_id = f"{file_hash[:12]}-{timestamp}"
    return RunContext(run_id=run_id, run_date=resolved_run_date, input_path=input_path, output_dir=output_dir)


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run_pipeline(
    *,
    input_path: Path,
    output_dir: Path,
    config: AppConfig,
    run_date: str | None,
) -> PipelineOutput:
    ensure_dir(output_dir)
    context = build_run_context(input_path=input_path, output_dir=output_dir, run_date=run_date)

    ingestion = ingest_workbook(input_path, config)
    normalization = normalize_rows(ingestion.raw_rows, config)
    metrics = compute_metrics(normalization, dimensions=config.dimensions)

    ingestion_log_payload = {
        "run_id": context.run_id,
        "run_date": context.run_date,
        **ingestion.to_log(),
        "normalization": normalization.to_log(),
    }

    metrics_payload = {
        "run_id": context.run_id,
        "run_date": context.run_date,
        "metrics": metrics,
    }

    ingestion_log_path = _write_json(output_dir / "ingestion_log.json", ingestion_log_payload)
    metrics_path = _write_json(output_dir / "metrics.json", metrics_payload)

    report = generate_report(metrics=metrics, normalization=normalization, context=context)

    storage = DatabaseStorage.from_env(output_headers=config.storage.output_headers)
    try:
        storage.persist_run(
            run_id=context.run_id,
            source_file=str(input_path),
            file_hash=ingestion.file_hash,
            raw_rows=ingestion.raw_rows,
            candidates=normalization.candidates,
            metrics=metrics,
        )
    finally:
        storage.close()

    artifacts = {
        "ingestion_log": ingestion_log_path,
        "metrics": metrics_path,
        "report_html": report.html_path,
        "report_pdf": report.pdf_path,
    }

    return PipelineOutput(
        context=context,
        ingestion=ingestion,
        normalization=normalization,
        metrics=metrics,
        report=report,
        artifacts=artifacts,
    )


def dry_run_pipeline(
    *,
    input_path: Path,
    output_dir: Path,
    config: AppConfig,
    run_date: str | None,
) -> PipelineOutput:
    ensure_dir(output_dir)
    context = build_run_context(input_path=input_path, output_dir=output_dir, run_date=run_date)

    ingestion = ingest_workbook(input_path, config)
    normalization = normalize_rows(ingestion.raw_rows, config)
    metrics = compute_metrics(normalization, dimensions=config.dimensions)

    ingestion_log_payload = {
        "run_id": context.run_id,
        "run_date": context.run_date,
        **ingestion.to_log(),
        "normalization": normalization.to_log(),
    }

    metrics_payload = {
        "run_id": context.run_id,
        "run_date": context.run_date,
        "metrics": metrics,
    }

    ingestion_log_path = _write_json(output_dir / "ingestion_log.json", ingestion_log_payload)
    metrics_path = _write_json(output_dir / "metrics.json", metrics_payload)

    artifacts = {
        "ingestion_log": ingestion_log_path,
        "metrics": metrics_path,
    }

    return PipelineOutput(
        context=context,
        ingestion=ingestion,
        normalization=normalization,
        metrics=metrics,
        report=None,
        artifacts=artifacts,
    )
