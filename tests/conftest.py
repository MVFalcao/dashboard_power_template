from __future__ import annotations

from pathlib import Path
import sys

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def sample_workbook(tmp_path: Path) -> Path:
    workbook = Workbook()

    ws_candidatos = workbook.active
    ws_candidatos.title = "Candidatos"

    for sheet_name in ["Aprovados", "Em análise", "Negado", "Database", "legenda"]:
        workbook.create_sheet(sheet_name)

    candidatos_headers = [
        "Nome do inscrito(a)",
        "Data de inscrição",
        "e-mail",
        "Contato",
        "Região",
        "Turma",
        "Idade",
        "Renda Familiar",
        "Equipe NAU",
        "Agendamento",
        "Status",
        "Motivo",
        "Comentarios",
    ]

    database_headers = [
        "Data de inscrição",
        "Nome do inscrito(a)",
        "Idade",
        "e-mail",
        "Celular/WhatsApp",
        "Região",
        "Turma",
        "Renda Familiar",
    ]

    ws_database = workbook["Database"]
    ws_database.append(database_headers)
    ws_database.append(["2026-01-10", "Lion El'Jonson", "Mais de 24 anos", "lion@nau.org", "+55 11 99999-0001", "SP", "Online T", "2-4 SM"])
    ws_database.append(["2026-01-11", "Azrael", "Entre 16 a 24 anos", "azrael@nau.org", "+55 11 99999-0002", "BA", "Presencial", "1-2 SM"])

    ws_candidatos.append(candidatos_headers)
    ws_candidatos.append([
        "Lion El'Jonson",
        "2026-01-10",
        "lion@nau.org",
        "+55 11 99999-0001",
        "SP",
        "Online T",
        "Mais de 24 anos",
        "2-4 SM",
        "pessoa1",
        "2026-01-15",
        "Aprovado",
        "Perfil aderente",
        "Candidato recomendado",
    ])

    ws_candidatos.append([
        "=Database!B3",
        "=Database!A3",
        "=Database!D3",
        "=Database!E3",
        "=Database!F3",
        "=Database!G3",
        "=Database!C3",
        "=Database!H3",
        "pessoa2",
        "",
        "Negado",
        "Conflito de agenda",
        "",
    ])

    for status_sheet in ["Aprovados", "Em análise", "Negado"]:
        workbook[status_sheet].append(candidatos_headers[:-1])

    ws_legenda = workbook["legenda"]
    ws_legenda.append(["Região", "Status", "Equipe ", "Turma", "Idade", "Motivo", "Renda Familiar"])
    ws_legenda.append(["SP", "Aprovado", "pessoa1", "Online T", "Mais de 24 anos", "Perfil aderente", "2-4 SM"])
    ws_legenda.append(["BA", "Negado", "pessoa2", "Presencial", "Entre 16 a 24 anos", "Conflito de agenda", "1-2 SM"])

    output = tmp_path / "Dashboard.xlsx"
    workbook.save(output)
    return output


@pytest.fixture()
def config_path() -> Path:
    return Path("configs/dashboard_template.yaml")
