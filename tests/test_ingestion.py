from __future__ import annotations

from pathlib import Path

from dashboard_reporter.config import load_config
from dashboard_reporter.ingestion import ingest_workbook


def test_ingestion_reads_rows_and_formulas(sample_workbook: Path, config_path: Path) -> None:
    config = load_config(config_path)
    result = ingest_workbook(sample_workbook, config)

    assert result.raw_rows
    assert result.sheet_stats["Candidatos"]["rows_kept"] >= 2

    formula_rows = [row for row in result.raw_rows if row.formulas]
    assert formula_rows, "expected at least one row with captured formulas"
