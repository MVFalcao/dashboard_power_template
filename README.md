# dashboard_power_template

Motor genérico em Python para ingestão de dashboards XLSX, normalização canônica, geração de relatório estatístico (HTML + PDF) e persistência idempotente em Turso/SQLite.

## Recursos

- CLI one-shot com comandos:
  - `dashboard-reporter run --input <xlsx> --config <yaml> --out <dir> --run-date <YYYY-MM-DD>`
  - `dashboard-reporter dry-run --input <xlsx> --config <yaml>`
  - `dashboard-reporter validate-config --config <yaml>`
  - `dashboard-reporter migrate-schema --config <yaml> --drop-normalized-candidates`
- Ingestão por mapeamento configurável (`YAML`) e suporte a abas formula-driven.
- PDF com paridade de renderização com HTML usando Playwright/Chromium (obrigatório).
- Camadas de persistência:
  - `raw_rows`
  - `normalized_candidates` (colunas físicas iguais aos headers do template)
  - `metrics_snapshots`
- Métricas de funil, demografia e qualidade de dados.

## Instalação

```bash
python -m pip install -e .
python -m pip install -e .[turso]
python -m pip install -e .[dev]
```

Dependência obrigatória de PDF (paridade HTML/PDF):

```bash
python -m pip install playwright
playwright install chromium
```

## Configuração base

Arquivo-base de mapeamento:

- `configs/dashboard_template.yaml`

Seções principais:

- `source`: abas de entrada e prioridade.
- `columns`: aliases da planilha para cada campo canônico.
- `storage.output_headers`: define os nomes físicos das colunas no banco para `normalized_candidates`.
- `status_rules`: tradução de status.
- `cleaning_rules`: limpeza/parsing.
- `required_fields`: campos obrigatórios.
- `dimensions`: dimensões de agregação.

## Como customizar para outro dashboard

### 1) Ajustar colunas da planilha

Edite `columns` no YAML. Exemplo:

```yaml
columns:
  nome:
    - Nome completo
  email:
    - E-mail principal
```

### 2) Definir nomes de colunas no banco

Edite `storage.output_headers` para controlar o schema físico de `normalized_candidates`:

```yaml
storage:
  output_headers:
    nome: Nome completo
    email: E-mail principal
```

Regra padrão: quando não informado, o sistema usa o primeiro alias de `columns`.

### 3) Validar configuração

```bash
dashboard-reporter validate-config --config configs/dashboard_template.yaml
```

### 4) Migrar schema do banco (obrigatório quando layout de colunas muda)

O comando é destrutivo para `normalized_candidates`.

```bash
dashboard-reporter migrate-schema --config configs/dashboard_template.yaml --drop-normalized-candidates
```

Sem migração, uma execução com schema antigo falha com mensagem orientativa.

## Uso

### Dataset de teste (50 registros)

```bash
python scripts/generate_test_workbook.py
```

Arquivo gerado:

- `template/Dashboard_50.xlsx`

### 1) Dry-run (sem banco)

```bash
dashboard-reporter dry-run --input template/Dashboard.xlsx --config configs/dashboard_template.yaml --out artifacts/dry-run
```

### 2) Execução completa com persistência

Defina ambiente:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN` (obrigatório para URL remota)

O CLI carrega `.env` automaticamente (procura da pasta atual até a raiz) sem sobrescrever variáveis já exportadas no ambiente.

Exemplo local SQLite:

```bash
set TURSO_DATABASE_URL=file:artifacts/local.db
dashboard-reporter run --input template/Dashboard_50.xlsx --config configs/dashboard_template.yaml --out artifacts/run
```

## Build Windows `.exe`

```powershell
./scripts/build_windows_exe.ps1
```

## Testes

```bash
pytest
```
