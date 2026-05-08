# Contribuindo com o OrgAudi

Obrigado pelo interesse em contribuir! Este documento descreve o fluxo padrão.

## Setup local

```bash
# 1. Clone
git clone https://github.com/orgateccloud-bot/AudiOrg-1.1.git
cd AudiOrg-1.1

# 2. Variáveis de ambiente
cp .env.example .env
# edite .env com suas chaves reais

# 3. Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# 4. Banco de dados
alembic upgrade head

# 5. Frontend
cd frontend
npm install
npm run dev
```

## Fluxo de branches

- `main` — produção (protegido, só recebe merge via PR)
- `develop` — integração (próxima release)
- `feat/<nome>` — novas features (a partir de `develop`)
- `fix/<nome>` — correções
- `chore/<nome>` — manutenção, refactor, infra

## Convenção de commits

```
<tipo>: <descrição curta em pt-BR>

<corpo opcional explicando o porquê>
```

Tipos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`.

## Antes de abrir PR

- [ ] `pytest tests/ -v` passa
- [ ] Sem secrets no diff (`git diff --cached | grep -iE "key|token|password|secret"`)
- [ ] `.env.example` atualizado se adicionou novas variáveis
- [ ] PR aponta para `develop` (não `main` direto)

## Segurança

- **NUNCA** commite arquivos `.env`, `config.env`, chaves privadas, ou credenciais
- Se vazou algo, reporte imediatamente em `orgatec.cloud@gmail.com` e rotacione a chave
- Use `python -c "import secrets; print(secrets.token_urlsafe(64))"` para gerar segredos
