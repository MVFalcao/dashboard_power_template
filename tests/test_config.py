from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_reporter.config import load_config


def test_load_default_config(config_path: Path) -> None:
    config = load_config(config_path)
    assert "Database" in config.source.input_sheets
    assert "status" in config.columns
    assert "nome" in config.required_fields
    assert config.storage.output_headers["nome"] == "Nome do inscrito(a)"


def test_invalid_config_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("required_fields: [campo_inexistente]\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(invalid)


def test_invalid_output_header_field_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid_storage.yaml"
    invalid.write_text(
        """
storage:
  output_headers:
    campo_nao_suportado: Campo X
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="canônico inválido"):
        load_config(invalid)


def test_duplicate_output_header_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid_dup.yaml"
    invalid.write_text(
        """
storage:
  output_headers:
    nome: Coluna A
    email: Coluna A
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="headers duplicados"):
        load_config(invalid)
