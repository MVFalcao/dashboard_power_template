from __future__ import annotations

import argparse
import importlib.resources as resources
import json
import os
import sys
from pathlib import Path

from .config import AppConfig, load_config
from .env_loader import load_env_from_dotenv
from .pipeline import dry_run_pipeline, run_pipeline
from .storage import DatabaseStorage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard-reporter",
        description="Motor de relatórios XLSX -> Turso com saída HTML/PDF",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Executa ingestão, normalização, relatório e persistência")
    run_parser.add_argument("--input", required=True, type=Path, help="Caminho do arquivo XLSX")
    run_parser.add_argument("--config", required=True, type=Path, help="Caminho da config YAML")
    run_parser.add_argument("--out", required=True, type=Path, help="Diretório de saída")
    run_parser.add_argument("--run-date", default=None, help="Data de referência (YYYY-MM-DD)")

    dry_parser = subparsers.add_parser("dry-run", help="Executa pipeline sem persistência em banco")
    dry_parser.add_argument("--input", required=True, type=Path, help="Caminho do arquivo XLSX")
    dry_parser.add_argument("--config", required=True, type=Path, help="Caminho da config YAML")
    dry_parser.add_argument("--out", type=Path, default=Path("artifacts") / "dry-run", help="Diretório de saída")
    dry_parser.add_argument("--run-date", default=None, help="Data de referência (YYYY-MM-DD)")

    quick_parser = subparsers.add_parser(
        "quick-run",
        help="Execução simplificada (1 comando): config padrão + DB local automático + migração automática",
    )
    quick_parser.add_argument("--input", required=True, type=Path, help="Caminho do arquivo XLSX")
    quick_parser.add_argument("--config", type=Path, default=None, help="Config YAML opcional")
    quick_parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts") / "quick-run",
        help="Diretório de saída (default: artifacts/quick-run)",
    )
    quick_parser.add_argument("--run-date", default=None, help="Data de referência (YYYY-MM-DD)")

    validate_parser = subparsers.add_parser("validate-config", help="Valida e imprime a configuração resolvida")
    validate_parser.add_argument("--config", required=True, type=Path, help="Caminho da config YAML")

    migrate_parser = subparsers.add_parser(
        "migrate-schema",
        help="Migra schema do banco para o layout atual (destrutivo para normalized_candidates)",
    )
    migrate_parser.add_argument("--config", required=True, type=Path, help="Caminho da config YAML")
    migrate_parser.add_argument(
        "--drop-normalized-candidates",
        action="store_true",
        help="Confirma recriação destrutiva da tabela normalized_candidates",
    )

    return parser


def _command_validate_config(config_path: Path) -> int:
    config = load_config(config_path)
    print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _command_dry_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = dry_run_pipeline(
        input_path=args.input,
        output_dir=args.out,
        config=config,
        run_date=args.run_date,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "dry-run",
                "run_id": result.context.run_id,
                "raw_rows": len(result.ingestion.raw_rows),
                "candidates": len(result.normalization.candidates),
                "artifacts": {key: str(path) for key, path in result.artifacts.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = run_pipeline(
        input_path=args.input,
        output_dir=args.out,
        config=config,
        run_date=args.run_date,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "run",
                "run_id": result.context.run_id,
                "raw_rows": len(result.ingestion.raw_rows),
                "candidates": len(result.normalization.candidates),
                "invalid_candidates": result.normalization.invalid_count,
                "artifacts": {key: str(path) for key, path in result.artifacts.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _load_config_with_optional_default(config_path: Path | None) -> tuple[AppConfig, str]:
    if config_path is not None:
        return load_config(config_path), str(config_path)

    workspace_default = Path("configs") / "dashboard_template.yaml"
    if workspace_default.exists():
        return load_config(workspace_default), str(workspace_default)

    default_resource = resources.files("dashboard_reporter").joinpath("configs/default_dashboard.yaml")
    with resources.as_file(default_resource) as default_path:
        return load_config(default_path), "dashboard_reporter/configs/default_dashboard.yaml"


def _ensure_database_env_for_quick_run(output_dir: Path) -> str:
    database_url = os.getenv("TURSO_DATABASE_URL")
    if database_url:
        return database_url

    local_db = output_dir / "quick-run.db"
    database_url = f"file:{local_db}"
    os.environ["TURSO_DATABASE_URL"] = database_url
    return database_url


def _auto_migrate_if_needed(config: AppConfig) -> bool:
    storage = DatabaseStorage.from_env(output_headers=config.storage.output_headers)
    migrated = False
    try:
        try:
            storage.ensure_schema()
        except RuntimeError as exc:
            if "Schema de 'normalized_candidates' incompatível" not in str(exc):
                raise
            storage.migrate_schema(drop_normalized_candidates=True)
            migrated = True
    finally:
        storage.close()

    return migrated


def _command_quick_run(args: argparse.Namespace) -> int:
    config, resolved_config = _load_config_with_optional_default(args.config)
    database_url = _ensure_database_env_for_quick_run(args.out)
    migrated = _auto_migrate_if_needed(config)

    result = run_pipeline(
        input_path=args.input,
        output_dir=args.out,
        config=config,
        run_date=args.run_date,
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "quick-run",
                "run_id": result.context.run_id,
                "raw_rows": len(result.ingestion.raw_rows),
                "candidates": len(result.normalization.candidates),
                "invalid_candidates": result.normalization.invalid_count,
                "config_source": resolved_config,
                "database_url": database_url,
                "auto_migrated_schema": migrated,
                "artifacts": {key: str(path) for key, path in result.artifacts.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _command_migrate_schema(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    storage = DatabaseStorage.from_env(output_headers=config.storage.output_headers)
    try:
        result = storage.migrate_schema(drop_normalized_candidates=args.drop_normalized_candidates)
    finally:
        storage.close()

    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "migrate-schema",
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    load_env_from_dotenv()
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate-config":
            return _command_validate_config(args.config)
        if args.command == "dry-run":
            return _command_dry_run(args)
        if args.command == "run":
            return _command_run(args)
        if args.command == "quick-run":
            return _command_quick_run(args)
        if args.command == "migrate-schema":
            return _command_migrate_schema(args)
    except Exception as exc:  # pragma: no cover - bounded by CLI integration tests
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
