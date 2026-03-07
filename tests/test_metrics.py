from __future__ import annotations

from pathlib import Path

from dashboard_reporter.config import load_config
from dashboard_reporter.ingestion import ingest_workbook
from dashboard_reporter.metrics import compute_metrics
from dashboard_reporter.normalization import normalize_rows


def test_metrics_contains_required_sections(sample_workbook: Path, config_path: Path) -> None:
    config = load_config(config_path)
    ingestion = ingest_workbook(sample_workbook, config)
    normalized = normalize_rows(ingestion.raw_rows, config)

    metrics = compute_metrics(normalized, config.dimensions)

    assert "resumo" in metrics
    assert "funil" in metrics
    assert "demografia" in metrics
    assert "qualidade_dados" in metrics
    assert metrics["resumo"]["total_candidatos"] == len(normalized.candidates)
