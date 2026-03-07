from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dashboard_reporter.cli import main


def test_cli_run_end_to_end(sample_workbook: Path, config_path: Path, tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    db_path = tmp_path / "reporting.db"

    monkeypatch.setenv("TURSO_DATABASE_URL", f"file:{db_path}")
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    exit_code = main(
        [
            "run",
            "--input",
            str(sample_workbook),
            "--config",
            str(config_path),
            "--out",
            str(output_dir),
            "--run-date",
            "2026-03-07",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "ingestion_log.json").exists()
    assert (output_dir / "metrics.json").exists()
    assert (output_dir / "report.html").exists()
    assert (output_dir / "report.pdf").exists()

    metrics_payload = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics_payload["run_date"] == "2026-03-07"

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM normalized_candidates")
        count = cursor.fetchone()[0]
        assert count >= 2
    finally:
        conn.close()


def test_cli_validate_config(config_path: Path) -> None:
    exit_code = main(["validate-config", "--config", str(config_path)])
    assert exit_code == 0


def test_cli_run_fails_without_turso_url(
    sample_workbook: Path,
    config_path: Path,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "missing-db"
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    exit_code = main(
        [
            "run",
            "--input",
            str(sample_workbook),
            "--config",
            str(config_path),
            "--out",
            str(output_dir),
            "--run-date",
            "2026-03-07",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "TURSO_DATABASE_URL não definido" in captured.err
