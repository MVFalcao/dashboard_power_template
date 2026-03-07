from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from dashboard_reporter.models import NormalizedCandidate
from dashboard_reporter.storage import DatabaseStorage, LibsqlExecutor, SQLiteExecutor


class _FakeClient:
    def __init__(self, url: str):
        self.url = url
        self.closed = False

    def execute(self, sql: str, params=()):
        if self.url.startswith("libsql://"):
            raise RuntimeError("505 Invalid response status at wss endpoint")
        return {"sql": sql, "params": params, "url": self.url}

    def close(self) -> None:
        self.closed = True


def _sample_candidate() -> NormalizedCandidate:
    return NormalizedCandidate(
        candidate_id="cand-1",
        source_key="email:one@example.com|data:2026-01-10",
        nome="Candidato Um",
        data_inscricao="2026-01-10",
        idade="Entre 16 a 24 anos",
        faixa_etaria="Entre 16 a 24 anos",
        email="one@example.com",
        contato="5511999990001",
        regiao="SP",
        turma="Online T",
        renda_familiar="1-2 SM",
        equipe_nau="pessoa1",
        agendamento="2026-01-15",
        status="APROVADO",
        motivo="Perfil aderente",
        comentarios="Teste",
        source_sheets=["Candidatos"],
        valid=True,
        missing_fields=[],
    )


def test_libsql_executor_falls_back_to_https_on_handshake_error(monkeypatch) -> None:
    created_urls: list[str] = []

    def fake_create_client_sync(*, url: str, auth_token: str):
        created_urls.append(url)
        return _FakeClient(url)

    fake_module = SimpleNamespace(create_client_sync=fake_create_client_sync)
    monkeypatch.setattr("dashboard_reporter.storage.importlib.import_module", lambda _: fake_module)

    executor = LibsqlExecutor(url="libsql://db.example.turso.io", auth_token="token")
    try:
        result = executor.execute("select 1", ())
    finally:
        executor.close()

    assert result["url"] == "https://db.example.turso.io"
    assert created_urls == ["libsql://db.example.turso.io", "https://db.example.turso.io"]


def test_storage_creates_template_header_columns_and_upserts(tmp_path: Path) -> None:
    db_path = tmp_path / "storage.db"
    output_headers = {
        "nome": "Nome do inscrito(a)",
        "data_inscricao": "Data de inscrição",
        "status": "Status",
    }

    storage = DatabaseStorage(SQLiteExecutor(db_path), output_headers=output_headers)
    try:
        storage.persist_run(
            run_id="run-1",
            source_file="input.xlsx",
            file_hash="hash",
            raw_rows=[],
            candidates=[_sample_candidate()],
            metrics={
                "resumo": {},
                "funil": {},
                "demografia": {},
                "qualidade_dados": {"campos_faltantes": {}, "grupos_duplicados_mesclados": 0},
            },
        )
    finally:
        storage.close()

    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(normalized_candidates)").fetchall()]
        assert "Nome do inscrito(a)" in cols
        assert "Data de inscrição" in cols
        assert "Status" in cols

        row = conn.execute(
            'SELECT "Nome do inscrito(a)", "Data de inscrição", "Status" FROM normalized_candidates WHERE candidate_id = ?',
            ("cand-1",),
        ).fetchone()
        assert row == ("Candidato Um", "2026-01-10", "APROVADO")
    finally:
        conn.close()


def test_storage_detects_legacy_schema_and_requires_migration(tmp_path: Path) -> None:
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

    output_headers = {
        "nome": "Nome do inscrito(a)",
        "status": "Status",
    }

    storage = DatabaseStorage(SQLiteExecutor(db_path), output_headers=output_headers)
    try:
        with pytest.raises(RuntimeError, match="migrate-schema"):
            storage.ensure_schema()

        with pytest.raises(RuntimeError, match="--drop-normalized-candidates"):
            storage.migrate_schema(drop_normalized_candidates=False)

        migration_result = storage.migrate_schema(drop_normalized_candidates=True)
        assert migration_result["normalized_candidates_recreated"] is True

        storage.ensure_schema()
    finally:
        storage.close()

    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(normalized_candidates)").fetchall()]
        assert "Nome do inscrito(a)" in cols
        assert "Status" in cols
        assert "nome" not in cols
    finally:
        conn.close()
