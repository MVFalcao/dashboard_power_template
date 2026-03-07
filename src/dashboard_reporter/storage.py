from __future__ import annotations

import asyncio
import importlib
import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from .models import NormalizedCandidate, RawRow


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SqlExecutor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        ...

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> Any:
        ...

    def close(self) -> None:
        ...


class SQLiteExecutor:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(db_path))

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        self.connection.commit()
        return cursor

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> Any:
        cursor = self.connection.cursor()
        cursor.executemany(sql, list(rows))
        self.connection.commit()
        return cursor

    def close(self) -> None:
        self.connection.close()


class LibsqlExecutor:
    def __init__(self, url: str, auth_token: str):
        if not auth_token:
            raise ValueError("TURSO_AUTH_TOKEN é obrigatório para conexão remota")

        module = importlib.import_module("libsql_client")
        self._is_async = False

        create_sync = getattr(module, "create_client_sync", None)
        if callable(create_sync):
            self.client = create_sync(url=url, auth_token=auth_token)
            return

        create_async = getattr(module, "create_client", None)
        if not callable(create_async):
            raise RuntimeError("Não foi possível criar cliente libsql")

        self.client = asyncio.run(create_async(url=url, auth_token=auth_token))
        self._is_async = True

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        if self._is_async:
            return asyncio.run(self.client.execute(sql, params))
        return self.client.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> Any:
        if self._is_async:
            async def _run() -> None:
                for row in rows:
                    await self.client.execute(sql, row)
            return asyncio.run(_run())

        for row in rows:
            self.client.execute(sql, row)
        return None

    def close(self) -> None:
        close_method = getattr(self.client, "close", None)
        if close_method is None:
            return

        if self._is_async:
            asyncio.run(close_method())
        else:
            close_method()


class DatabaseStorage:
    def __init__(self, executor: SqlExecutor):
        self.executor = executor

    @classmethod
    def from_env(cls) -> "DatabaseStorage":
        url = os.getenv("TURSO_DATABASE_URL")
        if not url:
            raise RuntimeError("TURSO_DATABASE_URL não definido")

        if url.startswith("file:"):
            db_path = Path(url.replace("file:", "", 1))
            return cls(SQLiteExecutor(db_path))

        if "://" not in url:
            db_path = Path(url)
            return cls(SQLiteExecutor(db_path))

        try:
            token = os.getenv("TURSO_AUTH_TOKEN", "")
            executor = LibsqlExecutor(url=url, auth_token=token)
            return cls(executor)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "libsql_client não instalado. Instale com: pip install 'dashboard-reporter[turso]'"
            ) from exc

    def close(self) -> None:
        self.executor.close()

    def ensure_schema(self) -> None:
        self.executor.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_rows (
                row_hash TEXT PRIMARY KEY,
                source_file TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                row_number INTEGER NOT NULL,
                row_data_json TEXT NOT NULL,
                formula_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                last_run_id TEXT NOT NULL
            )
            """
        )

        self.executor.execute(
            """
            CREATE TABLE IF NOT EXISTS normalized_candidates (
                candidate_id TEXT PRIMARY KEY,
                source_key TEXT NOT NULL,
                nome TEXT,
                data_inscricao TEXT,
                idade TEXT,
                faixa_etaria TEXT,
                email TEXT,
                contato TEXT,
                regiao TEXT,
                turma TEXT,
                renda_familiar TEXT,
                equipe_nau TEXT,
                agendamento TEXT,
                status TEXT NOT NULL,
                motivo TEXT,
                comentarios TEXT,
                source_sheets_json TEXT NOT NULL,
                valid INTEGER NOT NULL,
                missing_fields_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run_id TEXT NOT NULL
            )
            """
        )

        self.executor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                run_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                dimension TEXT NOT NULL,
                dimension_value TEXT NOT NULL,
                metric_value REAL NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (run_id, metric_name, dimension, dimension_value)
            )
            """
        )

    def upsert_raw_rows(
        self,
        *,
        run_id: str,
        source_file: str,
        file_hash: str,
        rows: list[RawRow],
    ) -> None:
        now = _utc_now()
        payload = [
            (
                row.row_hash,
                source_file,
                file_hash,
                row.sheet_name,
                row.row_number,
                json.dumps(row.values, ensure_ascii=False, default=str),
                json.dumps(row.formulas, ensure_ascii=False),
                now,
                run_id,
            )
            for row in rows
        ]

        self.executor.executemany(
            """
            INSERT INTO raw_rows (
                row_hash, source_file, file_hash, sheet_name, row_number,
                row_data_json, formula_json, ingested_at, last_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_hash) DO UPDATE SET
                source_file = excluded.source_file,
                file_hash = excluded.file_hash,
                sheet_name = excluded.sheet_name,
                row_number = excluded.row_number,
                row_data_json = excluded.row_data_json,
                formula_json = excluded.formula_json,
                ingested_at = excluded.ingested_at,
                last_run_id = excluded.last_run_id
            """,
            payload,
        )

    def upsert_candidates(self, *, run_id: str, candidates: list[NormalizedCandidate]) -> None:
        now = _utc_now()
        payload = [
            (
                candidate.candidate_id,
                candidate.source_key,
                candidate.nome,
                candidate.data_inscricao,
                candidate.idade,
                candidate.faixa_etaria,
                candidate.email,
                candidate.contato,
                candidate.regiao,
                candidate.turma,
                candidate.renda_familiar,
                candidate.equipe_nau,
                candidate.agendamento,
                candidate.status,
                candidate.motivo,
                candidate.comentarios,
                json.dumps(candidate.source_sheets, ensure_ascii=False),
                int(candidate.valid),
                json.dumps(candidate.missing_fields, ensure_ascii=False),
                now,
                run_id,
            )
            for candidate in candidates
        ]

        self.executor.executemany(
            """
            INSERT INTO normalized_candidates (
                candidate_id, source_key, nome, data_inscricao, idade, faixa_etaria,
                email, contato, regiao, turma, renda_familiar, equipe_nau, agendamento,
                status, motivo, comentarios, source_sheets_json, valid, missing_fields_json,
                updated_at, last_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                source_key = excluded.source_key,
                nome = excluded.nome,
                data_inscricao = excluded.data_inscricao,
                idade = excluded.idade,
                faixa_etaria = excluded.faixa_etaria,
                email = excluded.email,
                contato = excluded.contato,
                regiao = excluded.regiao,
                turma = excluded.turma,
                renda_familiar = excluded.renda_familiar,
                equipe_nau = excluded.equipe_nau,
                agendamento = excluded.agendamento,
                status = excluded.status,
                motivo = excluded.motivo,
                comentarios = excluded.comentarios,
                source_sheets_json = excluded.source_sheets_json,
                valid = excluded.valid,
                missing_fields_json = excluded.missing_fields_json,
                updated_at = excluded.updated_at,
                last_run_id = excluded.last_run_id
            """,
            payload,
        )

    def upsert_metrics(self, *, run_id: str, metrics: dict[str, Any]) -> None:
        now = _utc_now()
        payload: list[tuple[Any, ...]] = []

        for key, value in metrics.get("resumo", {}).items():
            payload.append((run_id, "resumo", key, "", float(value), now))

        for status, value in metrics.get("funil", {}).items():
            payload.append((run_id, "funil", "status", status, float(value), now))

        for dimension, rows in metrics.get("demografia", {}).items():
            for row in rows:
                payload.append(
                    (
                        run_id,
                        "demografia",
                        dimension,
                        str(row.get("valor", "")),
                        float(row.get("quantidade", 0)),
                        now,
                    )
                )

        missing_fields = metrics.get("qualidade_dados", {}).get("campos_faltantes", {})
        for field_name, value in missing_fields.items():
            payload.append((run_id, "qualidade_dados", "campo_faltante", field_name, float(value), now))

        duplicate_groups = metrics.get("qualidade_dados", {}).get("grupos_duplicados_mesclados", 0)
        payload.append((run_id, "qualidade_dados", "grupos_duplicados_mesclados", "", float(duplicate_groups), now))

        self.executor.executemany(
            """
            INSERT INTO metrics_snapshots (
                run_id, metric_name, dimension, dimension_value, metric_value, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, metric_name, dimension, dimension_value) DO UPDATE SET
                metric_value = excluded.metric_value,
                recorded_at = excluded.recorded_at
            """,
            payload,
        )

    def persist_run(
        self,
        *,
        run_id: str,
        source_file: str,
        file_hash: str,
        raw_rows: list[RawRow],
        candidates: list[NormalizedCandidate],
        metrics: dict[str, Any],
    ) -> None:
        self.ensure_schema()
        self.upsert_raw_rows(run_id=run_id, source_file=source_file, file_hash=file_hash, rows=raw_rows)
        self.upsert_candidates(run_id=run_id, candidates=candidates)
        self.upsert_metrics(run_id=run_id, metrics=metrics)
