from __future__ import annotations

import asyncio
import importlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from .models import NormalizedCandidate, RawRow

LEGACY_NORMALIZED_COLUMNS = {
    "candidate_id",
    "source_key",
    "nome",
    "data_inscricao",
    "idade",
    "faixa_etaria",
    "email",
    "contato",
    "regiao",
    "turma",
    "renda_familiar",
    "equipe_nau",
    "agendamento",
    "status",
    "motivo",
    "comentarios",
    "source_sheets_json",
    "valid",
    "missing_fields_json",
    "updated_at",
    "last_run_id",
}

SYSTEM_COLUMNS = [
    "candidate_id",
    "source_key",
    "source_sheets_json",
    "valid",
    "missing_fields_json",
    "updated_at",
    "last_run_id",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


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

        self._module = importlib.import_module("libsql_client")
        self._auth_token = auth_token
        self._url = url
        self._is_async = False
        self._fallback_used = False
        self.client = self._create_client(url)

    def _create_client(self, url: str) -> Any:
        self._is_async = False
        create_sync = getattr(self._module, "create_client_sync", None)
        if callable(create_sync):
            return create_sync(url=url, auth_token=self._auth_token)

        create_async = getattr(self._module, "create_client", None)
        if not callable(create_async):
            raise RuntimeError("Não foi possível criar cliente libsql")
        self._is_async = True
        return asyncio.run(create_async(url=url, auth_token=self._auth_token))

    def _close_client(self) -> None:
        close_method = getattr(self.client, "close", None)
        if close_method is None:
            return

        if self._is_async:
            asyncio.run(close_method())
        else:
            close_method()

    def _should_retry_with_https(self, exc: Exception) -> bool:
        if self._fallback_used:
            return False
        if not self._url.startswith("libsql://"):
            return False

        message = str(exc).lower()
        retry_markers = ("invalid response status", "wss", "handshake")
        return any(marker in message for marker in retry_markers)

    def _switch_to_https(self) -> None:
        https_url = "https://" + self._url[len("libsql://") :]
        self._close_client()
        self.client = self._create_client(https_url)
        self._url = https_url
        self._fallback_used = True

    def _execute_once(self, sql: str, params: tuple[Any, ...]) -> Any:
        if self._is_async:
            return asyncio.run(self.client.execute(sql, params))
        return self.client.execute(sql, params)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        try:
            return self._execute_once(sql, params)
        except Exception as exc:
            if not self._should_retry_with_https(exc):
                raise
            self._switch_to_https()
            return self._execute_once(sql, params)

    def _executemany_once(self, sql: str, rows: list[tuple[Any, ...]]) -> Any:
        if self._is_async:

            async def _run() -> None:
                for row in rows:
                    await self.client.execute(sql, row)

            return asyncio.run(_run())

        for row in rows:
            self.client.execute(sql, row)
        return None

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> Any:
        buffered_rows = list(rows)
        try:
            return self._executemany_once(sql, buffered_rows)
        except Exception as exc:
            if not self._should_retry_with_https(exc):
                raise
            self._switch_to_https()
            return self._executemany_once(sql, buffered_rows)

    def close(self) -> None:
        self._close_client()


class DatabaseStorage:
    def __init__(self, executor: SqlExecutor, output_headers: dict[str, str]):
        if not output_headers:
            raise ValueError("output_headers não pode ser vazio")

        self.executor = executor
        self.output_headers = dict(output_headers)
        self._canonical_order = list(self.output_headers.keys())
        self._header_order = list(self.output_headers.values())

    @classmethod
    def from_env(cls, *, output_headers: dict[str, str]) -> "DatabaseStorage":
        url = os.getenv("TURSO_DATABASE_URL")
        if not url:
            raise RuntimeError("TURSO_DATABASE_URL não definido")

        if url.startswith("file:"):
            db_path = Path(url.replace("file:", "", 1))
            return cls(SQLiteExecutor(db_path), output_headers)

        if "://" not in url:
            db_path = Path(url)
            return cls(SQLiteExecutor(db_path), output_headers)

        try:
            token = os.getenv("TURSO_AUTH_TOKEN", "")
            executor = LibsqlExecutor(url=url, auth_token=token)
            return cls(executor, output_headers)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "libsql_client não instalado. Instale com: pip install 'dashboard-reporter[turso]'"
            ) from exc

    def close(self) -> None:
        self.executor.close()

    def _query_rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        result = self.executor.execute(sql, params)

        if hasattr(result, "fetchall"):
            return [tuple(row) for row in result.fetchall()]

        rows = getattr(result, "rows", None)
        if rows is None:
            return []

        parsed_rows: list[tuple[Any, ...]] = []
        for row in rows:
            if isinstance(row, tuple):
                parsed_rows.append(row)
            elif isinstance(row, list):
                parsed_rows.append(tuple(row))
            else:
                try:
                    parsed_rows.append(tuple(row))
                except TypeError:
                    parsed_rows.append((row,))
        return parsed_rows

    def _table_exists(self, table_name: str) -> bool:
        rows = self._query_rows(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return bool(rows)

    def _table_columns(self, table_name: str) -> list[str]:
        rows = self._query_rows(f"PRAGMA table_info({_quote_identifier(table_name)})")
        return [str(row[1]) for row in rows]

    def _ensure_raw_rows_table(self) -> None:
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

    def _ensure_metrics_snapshots_table(self) -> None:
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

    def _normalized_expected_columns(self) -> list[str]:
        return [*SYSTEM_COLUMNS, *self._header_order]

    def _create_normalized_candidates_table(self) -> None:
        dynamic_columns = ",\n                ".join(
            f"{_quote_identifier(header)} TEXT" for header in self._header_order
        )

        create_sql = f"""
            CREATE TABLE IF NOT EXISTS normalized_candidates (
                {_quote_identifier('candidate_id')} TEXT PRIMARY KEY,
                {_quote_identifier('source_key')} TEXT NOT NULL,
                {_quote_identifier('source_sheets_json')} TEXT NOT NULL,
                {_quote_identifier('valid')} INTEGER NOT NULL,
                {_quote_identifier('missing_fields_json')} TEXT NOT NULL,
                {_quote_identifier('updated_at')} TEXT NOT NULL,
                {_quote_identifier('last_run_id')} TEXT NOT NULL,
                {dynamic_columns}
            )
        """
        self.executor.execute(create_sql)

    def _ensure_normalized_candidates_table(self) -> None:
        if not self._table_exists("normalized_candidates"):
            self._create_normalized_candidates_table()
            return

        existing_columns = self._table_columns("normalized_candidates")
        expected_columns = self._normalized_expected_columns()

        if set(existing_columns) == set(expected_columns):
            return

        legacy_detected = bool(LEGACY_NORMALIZED_COLUMNS.intersection(existing_columns))
        legacy_hint = " (schema legado detectado)" if legacy_detected else ""

        raise RuntimeError(
            "Schema de 'normalized_candidates' incompatível"
            f"{legacy_hint}. Execute: dashboard-reporter migrate-schema --config <arquivo> --drop-normalized-candidates"
        )

    def ensure_schema(self) -> None:
        self._ensure_raw_rows_table()
        self._ensure_metrics_snapshots_table()
        self._ensure_normalized_candidates_table()

    def migrate_schema(self, *, drop_normalized_candidates: bool) -> dict[str, Any]:
        if not drop_normalized_candidates:
            raise RuntimeError("Migração destrutiva requer --drop-normalized-candidates")

        self._ensure_raw_rows_table()
        self._ensure_metrics_snapshots_table()

        existed = self._table_exists("normalized_candidates")
        if existed:
            self.executor.execute("DROP TABLE normalized_candidates")

        self._create_normalized_candidates_table()
        return {
            "normalized_candidates_recreated": True,
            "normalized_candidates_previously_existed": existed,
            "normalized_candidates_columns": self._normalized_expected_columns(),
        }

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

        all_columns = [*SYSTEM_COLUMNS, *self._header_order]
        quoted_columns = ", ".join(_quote_identifier(column) for column in all_columns)
        placeholders = ", ".join("?" for _ in all_columns)

        update_columns = [column for column in all_columns if column != "candidate_id"]
        update_clause = ", ".join(
            f"{_quote_identifier(column)} = excluded.{_quote_identifier(column)}"
            for column in update_columns
        )

        payload: list[tuple[Any, ...]] = []
        for candidate in candidates:
            row_values: list[Any] = [
                candidate.candidate_id,
                candidate.source_key,
                json.dumps(candidate.source_sheets, ensure_ascii=False),
                int(candidate.valid),
                json.dumps(candidate.missing_fields, ensure_ascii=False),
                now,
                run_id,
            ]

            for canonical in self._canonical_order:
                row_values.append(getattr(candidate, canonical, None))

            payload.append(tuple(row_values))

        sql = f"""
            INSERT INTO normalized_candidates ({quoted_columns})
            VALUES ({placeholders})
            ON CONFLICT(candidate_id) DO UPDATE SET
                {update_clause}
        """
        self.executor.executemany(sql, payload)

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
