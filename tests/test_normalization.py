from __future__ import annotations

from pathlib import Path

from dashboard_reporter.config import load_config
from dashboard_reporter.ingestion import ingest_workbook
from dashboard_reporter.normalization import normalize_rows


def test_normalization_merges_and_validates(sample_workbook: Path, config_path: Path) -> None:
    config = load_config(config_path)
    ingestion = ingest_workbook(sample_workbook, config)
    normalized = normalize_rows(ingestion.raw_rows, config)

    assert len(normalized.candidates) >= 2
    assert normalized.duplicate_groups_merged >= 1

    statuses = {candidate.status for candidate in normalized.candidates}
    assert "APROVADO" in statuses
    assert "SEM_STATUS" in statuses or "NEGADO" in statuses

    invalid = [candidate for candidate in normalized.candidates if not candidate.valid]
    assert invalid, "expected at least one invalid candidate due required field checks"
