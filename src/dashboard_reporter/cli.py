from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .pipeline import dry_run_pipeline, run_pipeline


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

    validate_parser = subparsers.add_parser("validate-config", help="Valida e imprime a configuração resolvida")
    validate_parser.add_argument("--config", required=True, type=Path, help="Caminho da config YAML")

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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate-config":
            return _command_validate_config(args.config)
        if args.command == "dry-run":
            return _command_dry_run(args)
        if args.command == "run":
            return _command_run(args)
    except Exception as exc:  # pragma: no cover - bounded by CLI integration tests
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
