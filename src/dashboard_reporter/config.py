from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .utils import normalize_token

CANONICAL_FIELDS = {
    "nome",
    "data_inscricao",
    "idade",
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
    "faixa_etaria",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "source": {
        "input_sheets": ["Database", "Candidatos", "Aprovados", "Em análise", "Negado"],
        "header_row": 1,
        "base_sheet_priority": ["Database", "Candidatos", "Aprovados", "Em análise", "Negado"],
        "status_sheet_priority": ["Candidatos", "Aprovados", "Em análise", "Negado", "Database"],
        "status_by_sheet": {
            "Aprovados": "APROVADO",
            "Negado": "NEGADO",
            "Em análise": "EM_ANALISE",
        },
    },
    "columns": {
        "data_inscricao": ["Data de inscrição", "Data de inscricao"],
        "nome": ["Nome do inscrito(a)", "Nome"],
        "idade": ["Idade"],
        "email": ["e-mail", "email"],
        "contato": ["Contato", "Celular/WhatsApp", "Celular", "WhatsApp"],
        "regiao": ["Região", "Regiao"],
        "turma": ["Turma"],
        "renda_familiar": ["Renda Familiar"],
        "equipe_nau": ["Equipe NAU", "Equipe"],
        "agendamento": ["Agendamento"],
        "status": ["Status"],
        "motivo": ["Motivo"],
        "comentarios": ["Comentarios", "Comentários"],
    },
    "status_rules": {
        "aprovado": "APROVADO",
        "negado": "NEGADO",
        "em analise": "EM_ANALISE",
        "em análise": "EM_ANALISE",
    },
    "cleaning_rules": {
        "trim_strings": True,
        "normalize_accents": True,
        "accent_normalize_fields": ["status"],
        "phone_digits_only": True,
        "dayfirst_dates": True,
    },
    "required_fields": ["nome", "data_inscricao"],
    "dimensions": ["status", "regiao", "turma", "faixa_etaria", "renda_familiar"],
}


@dataclass(slots=True)
class SourceConfig:
    input_sheets: list[str]
    header_row: int
    base_sheet_priority: list[str]
    status_sheet_priority: list[str]
    status_by_sheet: dict[str, str]


@dataclass(slots=True)
class AppConfig:
    source: SourceConfig
    columns: dict[str, list[str]]
    status_rules: dict[str, str]
    cleaning_rules: dict[str, Any]
    required_fields: list[str]
    dimensions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "input_sheets": self.source.input_sheets,
                "header_row": self.source.header_row,
                "base_sheet_priority": self.source.base_sheet_priority,
                "status_sheet_priority": self.source.status_sheet_priority,
                "status_by_sheet": self.source.status_by_sheet,
            },
            "columns": self.columns,
            "status_rules": self.status_rules,
            "cleaning_rules": self.cleaning_rules,
            "required_fields": self.required_fields,
            "dimensions": self.dimensions,
        }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de config não encontrado: {path}")

    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}

    merged = _deep_merge(DEFAULT_CONFIG, loaded)
    return _validate_config(merged)


def _validate_config(data: dict[str, Any]) -> AppConfig:
    source_raw = data.get("source", {})
    input_sheets = source_raw.get("input_sheets", [])
    if not isinstance(input_sheets, list) or not input_sheets:
        raise ValueError("source.input_sheets deve conter ao menos uma aba")

    header_row = int(source_raw.get("header_row", 1))
    if header_row < 1:
        raise ValueError("source.header_row deve ser >= 1")

    columns = data.get("columns", {})
    if not isinstance(columns, dict) or not columns:
        raise ValueError("columns deve ser um mapeamento campo -> aliases")

    normalized_columns: dict[str, list[str]] = {}
    for canonical, aliases in columns.items():
        if canonical not in CANONICAL_FIELDS:
            raise ValueError(f"Campo canônico inválido em columns: {canonical}")
        if isinstance(aliases, str):
            alias_list = [aliases]
        elif isinstance(aliases, list):
            alias_list = [str(item) for item in aliases if str(item).strip()]
        else:
            raise ValueError(f"Aliases inválidos para {canonical}")
        if not alias_list:
            raise ValueError(f"Ao menos um alias é obrigatório para {canonical}")
        normalized_columns[canonical] = alias_list

    required_fields = [str(item) for item in data.get("required_fields", [])]
    for field in required_fields:
        if field not in normalized_columns:
            raise ValueError(f"required_fields contém campo ausente em columns: {field}")

    status_rules_input = data.get("status_rules", {})
    if not isinstance(status_rules_input, dict):
        raise ValueError("status_rules deve ser um mapeamento")
    status_rules = {
        normalize_token(key, lowercase=True, remove_accents=True): str(value).strip().upper()
        for key, value in status_rules_input.items()
        if str(key).strip() and str(value).strip()
    }

    source = SourceConfig(
        input_sheets=[str(item) for item in input_sheets],
        header_row=header_row,
        base_sheet_priority=[str(item) for item in source_raw.get("base_sheet_priority", input_sheets)],
        status_sheet_priority=[str(item) for item in source_raw.get("status_sheet_priority", input_sheets)],
        status_by_sheet={str(k): str(v).upper() for k, v in source_raw.get("status_by_sheet", {}).items()},
    )

    dimensions = [str(item) for item in data.get("dimensions", [])]
    if not dimensions:
        raise ValueError("dimensions deve conter ao menos um campo")

    return AppConfig(
        source=source,
        columns=normalized_columns,
        status_rules=status_rules,
        cleaning_rules=dict(data.get("cleaning_rules", {})),
        required_fields=required_fields,
        dimensions=dimensions,
    )


def default_config_dict() -> dict[str, Any]:
    return DEFAULT_CONFIG
