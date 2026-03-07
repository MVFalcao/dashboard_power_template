# dashboard_power_template

Motor genérico em Python para ingestão de dashboards XLSX, normalização canônica, geração de relatório estatístico (HTML + PDF) e persistência idempotente em Turso/SQLite.

## Recursos

- CLI one-shot com comandos:
  - `dashboard-reporter run --input <xlsx> --config <yaml> --out <dir> --run-date <YYYY-MM-DD>`
  - `dashboard-reporter dry-run --input <xlsx> --config <yaml>`
  - `dashboard-reporter validate-config --config <yaml>`
- Ingestão por mapeamento configurável (`YAML`) e suporte a abas formula-driven.
- Camadas de persistência:
  - `raw_rows`
  - `normalized_candidates`
  - `metrics_snapshots`
- Métricas de funil, demografia e qualidade de dados.
- Relatório em português com artefatos:
  - `report.html`
  - `report.pdf`
  - `metrics.json`
  - `ingestion_log.json`

## Instalação

```bash
python -m pip install -e .
```

Para conexão remota Turso com libsql:

```bash
python -m pip install -e .[turso]
```

Para desenvolvimento/testes:

```bash
python -m pip install -e .[dev]
```

## Configuração

Arquivo-base de mapeamento:

- `configs/dashboard_template.yaml`

Esse contrato define:

- abas de entrada e prioridades (`source`)
- aliases de colunas -> campos canônicos (`columns`)
- regras de status (`status_rules`)
- regras de limpeza (`cleaning_rules`)
- campos obrigatórios (`required_fields`)
- dimensões de análise (`dimensions`)

## Uso

### 1) Dry-run (sem banco)

```bash
dashboard-reporter dry-run --input template/Dashboard.xlsx --config configs/dashboard_template.yaml --out artifacts/dry-run
```

### 2) Execução completa com persistência

Defina ambiente:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN` (obrigatório para URL remota)

Exemplo local SQLite (para testes):

```bash
set TURSO_DATABASE_URL=file:artifacts/local.db
dashboard-reporter run --input template/Dashboard.xlsx --config configs/dashboard_template.yaml --out artifacts/run
```

## Build Windows `.exe`

```powershell
./scripts/build_windows_exe.ps1
```

## Testes

```bash
pytest
```
