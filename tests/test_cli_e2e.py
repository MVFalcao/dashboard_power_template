from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dashboard_reporter.cli import main


@pytest.fixture()
def stub_pdf_renderer(monkeypatch):
    def _fake_write_pdf(html_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"%PDF-1.4\n%stub\n")

    monkeypatch.setattr("dashboard_reporter.reporting._write_pdf_from_html", _fake_write_pdf)


def test_cli_run_end_to_end(
    sample_workbook: Path,
    config_path: Path,
    tmp_path: Path,
    monkeypatch,
    stub_pdf_renderer,
) -> None:
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
    assert (output_dir / "charts" / "mapa_brasil_regioes.png").exists()

    metrics_payload = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics_payload["run_date"] == "2026-03-07"

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute('SELECT "Nome do inscrito(a)", "Data de inscrição" FROM normalized_candidates LIMIT 1')
        row = cursor.fetchone()
        assert row is not None
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
    stub_pdf_renderer,
) -> None:
    output_dir = tmp_path / "missing-db"
    config_abs = (Path(__file__).resolve().parents[1] / config_path).resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    exit_code = main(
        [
            "run",
            "--input",
            str(sample_workbook),
            "--config",
            str(config_abs),
            "--out",
            str(output_dir),
            "--run-date",
            "2026-03-07",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "TURSO_DATABASE_URL não definido" in captured.err


def test_cli_run_loads_turso_url_from_dotenv(
    sample_workbook: Path,
    config_path: Path,
    tmp_path: Path,
    monkeypatch,
    stub_pdf_renderer,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    db_path = workspace / "dotenv.db"
    output_dir = workspace / "output"
    config_abs = (Path(__file__).resolve().parents[1] / config_path).resolve()

    dotenv_path = workspace / ".env"
    dotenv_path.write_text(f"TURSO_DATABASE_URL=file:{db_path}\n", encoding="utf-8")

    monkeypatch.chdir(workspace)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    exit_code = main(
        [
            "run",
            "--input",
            str(sample_workbook),
            "--config",
            str(config_abs),
            "--out",
            str(output_dir),
            "--run-date",
            "2026-03-07",
        ]
    )

    assert exit_code == 0
    assert db_path.exists()


def test_cli_run_fails_when_forced_playwright_is_missing(
    sample_workbook: Path,
    config_path: Path,
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output_dir = tmp_path / "pdf-engine-missing"
    db_path = tmp_path / "run.db"

    monkeypatch.setenv("TURSO_DATABASE_URL", f"file:{db_path}")
    monkeypatch.setenv("DASHBOARD_REPORTER_PDF_ENGINE", "playwright")
    monkeypatch.setattr(
        "dashboard_reporter.reporting._get_sync_playwright",
        lambda: (_ for _ in ()).throw(
            RuntimeError("Playwright não instalado. Instale com: pip install playwright && playwright install chromium")
        ),
    )

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
    assert "Playwright não instalado" in captured.err


def test_cli_quick_run_works_with_single_command(sample_workbook: Path, tmp_path: Path, monkeypatch, stub_pdf_renderer) -> None:
    output_dir = tmp_path / "quick-output"
    config_abs = (Path(__file__).resolve().parents[1] / "configs" / "dashboard_template.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    exit_code = main(
        [
            "quick-run",
            "--input",
            str(sample_workbook),
            "--config",
            str(config_abs),
            "--out",
            str(output_dir),
            "--run-date",
            "2026-03-07",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "report.html").exists()
    assert (output_dir / "report.pdf").exists()
    assert (output_dir / "quick-run.db").exists()


def test_cli_migrate_schema_recreates_legacy_table(config_path: Path, tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE normalized_candidates (
                candidate_id TEXT PRIMARY KEY,
                nome TEXT,
                status TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("TURSO_DATABASE_URL", f"file:{db_path}")

    exit_code = main(
        [
            "migrate-schema",
            "--config",
            str(config_path),
            "--drop-normalized-candidates",
        ]
    )

    assert exit_code == 0

    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(normalized_candidates)").fetchall()]
        assert "Nome do inscrito(a)" in cols
        assert "Data de inscrição" in cols
    finally:
        conn.close()


def test_cli_migrate_schema_requires_explicit_drop(config_path: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "migration-required.db"
    monkeypatch.setenv("TURSO_DATABASE_URL", f"file:{db_path}")

    exit_code = main(["migrate-schema", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--drop-normalized-candidates" in captured.err
