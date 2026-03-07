from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

import pandas as pd

from .config import AppConfig
from .models import NormalizationResult, NormalizedCandidate, RawRow
from .utils import is_empty, normalize_token, normalize_whitespace, sha256_text, strip_accents


@dataclass(slots=True)
class _IntermediateCandidate:
    source_key: str
    sheet_name: str
    values: dict[str, Any]


def _build_column_lookup(config: AppConfig) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in config.columns.items():
        for alias in [canonical, *aliases]:
            lookup[normalize_token(alias, lowercase=True, remove_accents=True)] = canonical
    return lookup


def _clean_string(field: str, value: Any, config: AppConfig) -> str | None:
    if is_empty(value):
        return None

    text = normalize_whitespace(str(value))
    rules = config.cleaning_rules

    if rules.get("normalize_accents", True) and field in rules.get("accent_normalize_fields", ["status"]):
        text = strip_accents(text)

    if is_empty(text):
        return None
    return text


def _parse_date(value: Any, dayfirst: bool) -> str | None:
    if is_empty(value):
        return None

    dt = pd.to_datetime(value, errors="coerce", dayfirst=dayfirst)
    if pd.isna(dt):
        return None
    return dt.date().isoformat()


def _normalize_phone(value: str | None, digits_only: bool) -> str | None:
    if value is None:
        return None
    if not digits_only:
        return value
    digits = re.sub(r"\D", "", value)
    return digits or None


def _derive_faixa_etaria(idade: str | None) -> str | None:
    if idade is None:
        return None

    token = normalize_token(idade, lowercase=True, remove_accents=True)
    if not token:
        return None

    if "menos de 16" in token:
        return "Menos de 16 anos"
    if "16" in token and "24" in token:
        return "Entre 16 a 24 anos"
    if "mais de 24" in token:
        return "Mais de 24 anos"

    found_number = re.search(r"\d+", token)
    if found_number:
        age = int(found_number.group(0))
        if age < 16:
            return "Menos de 16 anos"
        if age <= 24:
            return "Entre 16 a 24 anos"
        return "Mais de 24 anos"

    return idade


def _map_status(raw_status: str | None, sheet_name: str, config: AppConfig) -> str:
    if raw_status:
        status_token = normalize_token(raw_status, lowercase=True, remove_accents=True)
        mapped = config.status_rules.get(status_token)
        if mapped:
            return mapped

    by_sheet = config.source.status_by_sheet.get(sheet_name)
    if by_sheet:
        return by_sheet
    return "SEM_STATUS"


def _compute_source_key(mapped: dict[str, Any], fallback_hash: str) -> str:
    email = mapped.get("email")
    data = mapped.get("data_inscricao")
    nome = mapped.get("nome")
    contato = mapped.get("contato")

    if email and data:
        return f"email:{normalize_token(email)}|data:{data}"
    if email and nome:
        return f"email:{normalize_token(email)}|nome:{normalize_token(nome)}"
    if nome and contato:
        return f"nome:{normalize_token(nome)}|contato:{normalize_token(contato)}"
    return fallback_hash


def _priority_index(sheet_name: str, order: list[str]) -> int:
    try:
        return order.index(sheet_name)
    except ValueError:
        return len(order) + 100


def normalize_rows(raw_rows: list[RawRow], config: AppConfig) -> NormalizationResult:
    column_lookup = _build_column_lookup(config)
    rules = config.cleaning_rules
    dayfirst = bool(rules.get("dayfirst_dates", True))
    digits_only = bool(rules.get("phone_digits_only", True))

    staged: list[_IntermediateCandidate] = []

    for row in raw_rows:
        mapped: dict[str, Any] = {key: None for key in config.columns.keys()}

        for source_column, raw_value in row.values.items():
            canonical = column_lookup.get(normalize_token(source_column, lowercase=True, remove_accents=True))
            if not canonical:
                continue
            if mapped.get(canonical) is None and not is_empty(raw_value):
                mapped[canonical] = raw_value

        for field in list(mapped.keys()):
            if field == "data_inscricao":
                mapped[field] = _parse_date(mapped.get(field), dayfirst=dayfirst)
            elif field == "contato":
                mapped[field] = _normalize_phone(_clean_string(field, mapped.get(field), config), digits_only=digits_only)
            else:
                mapped[field] = _clean_string(field, mapped.get(field), config)

        mapped["status"] = _map_status(mapped.get("status"), row.sheet_name, config)
        mapped["faixa_etaria"] = _derive_faixa_etaria(mapped.get("idade"))

        source_key = _compute_source_key(mapped, row.row_hash)
        staged.append(_IntermediateCandidate(source_key=source_key, sheet_name=row.sheet_name, values=mapped))

    grouped: dict[str, list[_IntermediateCandidate]] = defaultdict(list)
    for item in staged:
        grouped[item.source_key].append(item)

    merged_candidates: list[NormalizedCandidate] = []
    missing_counter: Counter[str] = Counter()
    duplicate_groups_merged = 0

    for source_key, group in grouped.items():
        if len(group) > 1:
            duplicate_groups_merged += 1

        base_sorted = sorted(group, key=lambda item: _priority_index(item.sheet_name, config.source.base_sheet_priority))
        status_sorted = sorted(group, key=lambda item: _priority_index(item.sheet_name, config.source.status_sheet_priority))

        merged = dict(base_sorted[0].values)

        for item in base_sorted[1:]:
            for key, value in item.values.items():
                if is_empty(merged.get(key)) and not is_empty(value):
                    merged[key] = value

        chosen_status = "SEM_STATUS"
        for item in status_sorted:
            candidate_status = item.values.get("status")
            if candidate_status and candidate_status != "SEM_STATUS":
                chosen_status = candidate_status
                break
        if chosen_status == "SEM_STATUS" and merged.get("status"):
            chosen_status = merged.get("status")
        merged["status"] = chosen_status or "SEM_STATUS"

        candidate_seed = merged.get("email") and merged.get("data_inscricao")
        if candidate_seed:
            candidate_id = sha256_text(f"{normalize_token(merged['email'])}|{merged['data_inscricao']}")
        else:
            candidate_id = sha256_text(source_key)

        missing_fields = [field for field in config.required_fields if is_empty(merged.get(field))]
        for field in missing_fields:
            missing_counter[field] += 1

        candidate = NormalizedCandidate(
            candidate_id=candidate_id,
            source_key=source_key,
            nome=merged.get("nome"),
            data_inscricao=merged.get("data_inscricao"),
            idade=merged.get("idade"),
            faixa_etaria=merged.get("faixa_etaria"),
            email=merged.get("email"),
            contato=merged.get("contato"),
            regiao=merged.get("regiao"),
            turma=merged.get("turma"),
            renda_familiar=merged.get("renda_familiar"),
            equipe_nau=merged.get("equipe_nau"),
            agendamento=merged.get("agendamento"),
            status=merged.get("status") or "SEM_STATUS",
            motivo=merged.get("motivo"),
            comentarios=merged.get("comentarios"),
            source_sheets=sorted({item.sheet_name for item in group}),
            valid=not missing_fields,
            missing_fields=missing_fields,
        )
        merged_candidates.append(candidate)

    invalid_count = sum(1 for candidate in merged_candidates if not candidate.valid)
    return NormalizationResult(
        candidates=merged_candidates,
        invalid_count=invalid_count,
        duplicate_groups_merged=duplicate_groups_merged,
        missing_fields_counter=dict(missing_counter),
    )
