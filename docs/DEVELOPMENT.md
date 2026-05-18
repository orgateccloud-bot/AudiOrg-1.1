# Development Guide — OrgAudi Sovereign

Guia completo de Developer Experience (DevX) para contribuidores.

## Setup inicial

```bash
# 1. Clone e ambiente virtual
git clone https://github.com/orgateccloud-bot/AudiOrg-1.1.git
cd AudiOrg-1.1
python -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate           # Windows

# 2. Instalar dependências de runtime + dev
pip install -r requirements.txt
pip install -r requirements-dev.txt
# Ou via pyproject:  pip install -e ".[dev]"

# 3. Configurar pre-commit hooks
pre-commit install
pre-commit run --all-files         # valida estado atual
```

## Estrutura de dependências

- `requirements.txt` — deps de runtime (deploy/produção)
- `requirements-dev.txt` — deps de desenvolvimento (linting, tests, debugging)
- `pyproject.toml` — configuração das ferramentas (ruff, mypy, pytest, bandit, coverage)

## Comandos comuns

### Linting & formatação

```bash
ruff check .                       # lint
ruff check . --fix                 # lint com auto-fix
ruff format .                      # format (substitui black)
mypy api/ horizon_blue_one/        # type check
bandit -c pyproject.toml -r .      # security scan
```

### Testes

```bash
pytest                             # todos os testes
pytest -m unit                     # apenas unit
pytest -m "not slow"               # excluir lentos
pytest --cov=. --cov-report=html   # com cobertura HTML
pytest -n auto                     # paralelo (pytest-xdist)
```

### Pre-commit

```bash
pre-commit run --all-files         # rodar em todos os arquivos
pre-commit run ruff                # rodar hook específico
pre-commit autoupdate              # atualizar versões dos hooks
SKIP=mypy git commit -m "..."      # pular hook específico (emergência)
```

## CI/CD

O pipeline em `.github/workflows/ci.yml` executa 4 jobs em paralelo:

1. **Lint (pre-commit)** — roda `pre-commit run --all-files` (atualmente non-blocking)
2. **Python Tests** — pytest em Python 3.10, 3.11, 3.12
3. **Frontend Build** — `npm run build` em `frontend/frontend/`
4. **Security Scan** — TruffleHog para detectar secrets verificados

Após estabilizar o lint, remover `continue-on-error: true` no job `lint` para torná-lo bloqueante.

## Dependabot

Configurado em `.github/dependabot.yml` para abrir PRs semanais (segunda-feira 09:00 BRT) agrupando updates minor+patch para:

- pip (raiz)
- npm (frontend/)
- github-actions

## Branch strategy

- `main` — produção
- `develop` — integração
- `feat/<n>-<slug>` — features (ex: `feat/25-sentry-prometheus-v2`)
- `fix/<slug>` — bugfixes
- `chore/<slug>` — manutenção

Pull Requests para `main` exigem revisão. Use Conventional Commits no título e body.

## Troubleshooting

| Problema | Solução |
|----------|---------|
| `pre-commit` não encontra ruff | `pre-commit clean && pre-commit install --install-hooks` |
| Testes pedem `pytest-asyncio` | `pip install -r requirements-dev.txt` |
| Mypy reclama de `datetime.UTC` | Use `from datetime import timezone` (compatível 3.10) |
| Coverage abaixo de 30% | Adicionar testes; CI falha em `--cov-fail-under=30` |
| Conflito de migrations Alembic | `alembic merge heads -m "merge"` |

## Recursos

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Ruff docs](https://docs.astral.sh/ruff/)
- [Pytest docs](https://docs.pytest.org/)
- [Pre-commit docs](https://pre-commit.com/)
