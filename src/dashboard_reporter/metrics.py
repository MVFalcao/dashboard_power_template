from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from .models import NormalizationResult


def _as_records(normalization: NormalizationResult) -> list[dict[str, Any]]:
    return [candidate.to_dict() for candidate in normalization.candidates]


def _value_counts(df: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    if column not in df.columns:
        return []

    normalized = df[column].fillna("NAO_INFORMADO").astype(str)
    counts = normalized.value_counts(dropna=False)
    return [
        {"valor": value, "quantidade": int(count)}
        for value, count in counts.items()
    ]


def compute_metrics(normalization: NormalizationResult, dimensions: list[str]) -> dict[str, Any]:
    records = _as_records(normalization)
    df = pd.DataFrame(records)

    total = int(len(df.index))
    status_counts = defaultdict(int)

    if total > 0 and "status" in df.columns:
        for status_value, amount in df["status"].fillna("SEM_STATUS").value_counts().items():
            status_counts[str(status_value)] = int(amount)

    aprovados = int(status_counts.get("APROVADO", 0))
    negados = int(status_counts.get("NEGADO", 0))
    em_analise = int(status_counts.get("EM_ANALISE", 0))
    sem_status = int(status_counts.get("SEM_STATUS", 0))

    valid_records = total - normalization.invalid_count
    success_rate = round((valid_records / total) * 100, 2) if total else 0.0
    approval_rate = round((aprovados / total) * 100, 2) if total else 0.0

    demographics = {
        dim: _value_counts(df, dim) for dim in dimensions
    }

    return {
        "resumo": {
            "total_candidatos": total,
            "total_validos": valid_records,
            "total_invalidos": normalization.invalid_count,
            "taxa_normalizacao_sucesso": success_rate,
            "taxa_aprovacao": approval_rate,
        },
        "funil": {
            "APROVADO": aprovados,
            "NEGADO": negados,
            "EM_ANALISE": em_analise,
            "SEM_STATUS": sem_status,
            "TOTAL": total,
        },
        "demografia": demographics,
        "qualidade_dados": {
            "campos_faltantes": normalization.missing_fields_counter,
            "grupos_duplicados_mesclados": normalization.duplicate_groups_merged,
        },
    }
