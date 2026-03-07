from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RawRow:
    sheet_name: str
    row_number: int
    values: dict[str, Any]
    formulas: dict[str, str]
    source_file: str
    row_hash: str


@dataclass(slots=True)
class IngestionResult:
    source_file: str
    file_hash: str
    raw_rows: list[RawRow]
    sheet_stats: dict[str, dict[str, int]]

    def to_log(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "file_hash": self.file_hash,
            "raw_row_count": len(self.raw_rows),
            "sheet_stats": self.sheet_stats,
        }


@dataclass(slots=True)
class NormalizedCandidate:
    candidate_id: str
    source_key: str
    nome: str | None
    data_inscricao: str | None
    idade: str | None
    faixa_etaria: str | None
    email: str | None
    contato: str | None
    regiao: str | None
    turma: str | None
    renda_familiar: str | None
    equipe_nau: str | None
    agendamento: str | None
    status: str
    motivo: str | None
    comentarios: str | None
    source_sheets: list[str]
    valid: bool
    missing_fields: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NormalizationResult:
    candidates: list[NormalizedCandidate]
    invalid_count: int
    duplicate_groups_merged: int
    missing_fields_counter: dict[str, int]

    def to_log(self) -> dict[str, Any]:
        return {
            "candidate_count": len(self.candidates),
            "invalid_count": self.invalid_count,
            "duplicate_groups_merged": self.duplicate_groups_merged,
            "missing_fields_counter": self.missing_fields_counter,
        }


@dataclass(slots=True)
class RunContext:
    run_id: str
    run_date: str
    input_path: Path
    output_dir: Path


@dataclass(slots=True)
class ReportArtifacts:
    html_path: Path
    pdf_path: Path
    chart_paths: dict[str, Path]

    def to_dict(self) -> dict[str, Any]:
        return {
            "html_path": str(self.html_path),
            "pdf_path": str(self.pdf_path),
            "chart_paths": {key: str(value) for key, value in self.chart_paths.items()},
        }


@dataclass(slots=True)
class PipelineOutput:
    context: RunContext
    ingestion: IngestionResult
    normalization: NormalizationResult
    metrics: dict[str, Any]
    report: ReportArtifacts | None = None
    artifacts: dict[str, Path] = field(default_factory=dict)
