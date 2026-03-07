# dashboard_power_template

Motor genérico em Python para ingestão de dashboards XLSX, normalização canônica, geração de relatório estatístico (HTML + PDF) e persistência idempotente em Turso/SQLite.

Guia interativo em PT-BR:

- `docs/guia_interativo_ptbr.html`

## Recursos

- CLI one-shot com comandos:
  - `dashboard-reporter quick-run --input <xlsx>`
  - `dashboard-reporter run --input <xlsx> --config <yaml> --out <dir> --run-date <YYYY-MM-DD>`
  - `dashboard-reporter dry-run --input <xlsx> --config <yaml>`
  - `dashboard-reporter validate-config --config <yaml>`
  - `dashboard-reporter migrate-schema --config <yaml> --drop-normalized-candidates`
- Ingestão por mapeamento configurável (`YAML`) e suporte a abas formula-driven.
- PDF gerado sem Chromium por padrão via `xhtml2pdf`, com fallback opcional para Playwright.
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

Backend PDF padrão (sem Chromium):

```bash
python -m pip install xhtml2pdf
```

Backend alternativo (Playwright):

```bash
python -m pip install -e .[pdf-playwright]
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

### 2) Execução simplificada (1 comando)

Sem precisar passar config/banco manualmente:

```bash
dashboard-reporter quick-run --input template/Dashboard_50.xlsx
```

O que esse comando faz:

- usa `configs/dashboard_template.yaml` se existir (senão usa a config padrão embutida);
- cria `TURSO_DATABASE_URL=file:artifacts/quick-run/quick-run.db` se não houver variável de ambiente;
- migra automaticamente `normalized_candidates` quando detectar schema incompatível;
- gera `report.html`, `report.pdf`, `metrics.json` e `ingestion_log.json`.

#### Passo a passo (quick-run)

1. Abra o PowerShell.
2. Entre na pasta do projeto:

```powershell
cd "C:\caminho\para\dashboard_power_template"
```

No Linux/macOS, use:

```bash
cd /caminho/para/dashboard_power_template
```

3. Rode o comando simplificado:

```powershell
dashboard-reporter quick-run --input template/Dashboard_50.xlsx
```

4. Confira os artefatos:

```powershell
dir artifacts\quick-run
```

### 3) Execução completa com persistência (modo avançado)

Defina ambiente:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN` (obrigatório para URL remota)

O CLI carrega `.env` automaticamente (procura da pasta atual até a raiz) sem sobrescrever variáveis já exportadas no ambiente.

Exemplo local SQLite:

```bash
set TURSO_DATABASE_URL=file:artifacts/local.db
dashboard-reporter run --input template/Dashboard_50.xlsx --config configs/dashboard_template.yaml --out artifacts/run
```

#### Passo a passo (modo avançado)

1. Abra o PowerShell e entre na pasta do projeto:

```powershell
cd "C:\caminho\para\dashboard_power_template"
```

No Linux/macOS, use:

```bash
cd /caminho/para/dashboard_power_template
```

2. Configure variáveis de ambiente:

```powershell
set TURSO_DATABASE_URL=file:artifacts/local.db
```

3. (Se necessário) migre o schema:

```powershell
dashboard-reporter migrate-schema --config configs/dashboard_template.yaml --drop-normalized-candidates
```

4. Execute o `run`:

```powershell
dashboard-reporter run --input template/Dashboard_50.xlsx --config configs/dashboard_template.yaml --out artifacts/run --run-date 2026-03-07
```

### Seleção do motor de PDF

Variável opcional:

- `DASHBOARD_REPORTER_PDF_ENGINE=auto` (default: tenta `xhtml2pdf`, depois Playwright)
- `DASHBOARD_REPORTER_PDF_ENGINE=xhtml2pdf`
- `DASHBOARD_REPORTER_PDF_ENGINE=playwright`

## Build Windows `.exe`

```powershell
./scripts/build_windows_exe.ps1
```

## Testes

```bash
pytest
```
