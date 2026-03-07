from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_reporter.config import load_config


def test_load_default_config(config_path: Path) -> None:
    config = load_config(config_path)
    assert "Database" in config.source.input_sheets
    assert "status" in config.columns
    assert "nome" in config.required_fields


def test_invalid_config_raises(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("required_fields: [campo_inexistente]\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(invalid)
