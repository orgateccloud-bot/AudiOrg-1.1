#!/bin/bash
# ============================================================================
# OrgAudi PR #3 — Governança do repositório
# Rode no Codespace (com $GITHUB_TOKEN setado) em /workspaces/AudiOrg-1.1
# ============================================================================
set -e

echo "→ Sincronizando com main"
git fetch origin
git checkout main
git pull origin main

echo "→ Criando branch chore/governanca-repo"
git checkout -B chore/governanca-repo

echo "→ Gerando LICENSE (Proprietary)"
cat > LICENSE <<'LICEOF'
PROPRIETARY LICENSE — ALL RIGHTS RESERVED

Copyright (c) 2026 ORGATEC. All rights reserved.

Este software e seus arquivos associados ("Software") são propriedade
exclusiva da ORGATEC. O acesso ao código-fonte neste repositório é
disponibilizado para fins de transparência, auditoria e revisão técnica.

PROIBIDO sem autorização prévia, expressa e por escrito da ORGATEC:
  1. Copiar, redistribuir ou sublicenciar o Software, no todo ou em parte;
  2. Modificar, criar trabalhos derivados ou compilar o Software;
  3. Usar o Software em ambientes de produção, comerciais ou não;
  4. Remover ou alterar avisos de copyright, marca ou autoria.

PERMITIDO sem autorização prévia:
  1. Visualizar o código para fins educacionais e de auditoria de segurança;
  2. Reportar vulnerabilidades de segurança via SECURITY.md;
  3. Submeter pull requests com correções e melhorias — ao fazer isso,
     o contribuidor concorda que sua contribuição passa a ser propriedade
     da ORGATEC sob esta mesma licença.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
ORGATEC BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Para licenciamento comercial, parcerias ou uso autorizado, contate:
orgatec.cloud@gmail.com
LICEOF

echo "→ Gerando SECURITY.md"
cat > SECURITY.md <<'SECEOF'
# Política de Segurança — OrgAudi

## Reportando uma Vulnerabilidade

A ORGATEC leva segurança a sério. Se você descobriu uma vulnerabilidade no OrgAudi, **não abra uma issue pública**.

### Como reportar

Envie um e-mail para **orgatec.cloud@gmail.com** com:

- Descrição clara da vulnerabilidade
- Passos para reproduzir (PoC se possível)
- Versão/commit afetado
- Impacto estimado (qual dado pode vazar / qual ação maliciosa permite)
- Sua sugestão de correção (opcional)

Você receberá confirmação em **até 48 horas úteis**.

### O que esperar

| Severidade | Tempo de resposta inicial | Tempo até correção |
|------------|---------------------------|--------------------|
| 🔴 Crítica | 24h                       | 7 dias             |
| 🟠 Alta    | 48h                       | 14 dias            |
| 🟡 Média   | 72h                       | 30 dias            |
| 🟢 Baixa   | 5 dias úteis              | Próxima release    |

### Reconhecimento

Pesquisadores que reportam vulnerabilidades de forma responsável serão
creditados no [Hall of Fame](https://github.com/orgateccloud-bot/AudiOrg-1.1/security/advisories)
após a correção (a menos que prefiram permanecer anônimos).

## Versões Suportadas

| Versão  | Suporte de Segurança |
|---------|----------------------|
| `main`  | ✅ Sim                |
| < 1.0   | ❌ Não                |

## Práticas de Segurança Internas

- ✅ CI com scan de secrets (TruffleHog) em todo PR
- ✅ Dependabot habilitado para Python, npm e GitHub Actions
- ✅ Branch `main` protegida (apenas via PR aprovada)
- ✅ Secrets em variáveis de ambiente (nunca em código)
- ✅ Auditoria de logs sem credenciais (LGPD-compliant)
SECEOF

echo "→ Gerando .github/CODEOWNERS"
mkdir -p .github
cat > .github/CODEOWNERS <<'COEOF'
# Code owners do OrgAudi
# Sintaxe: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-security/customizing-your-repository/about-code-owners

# Owner padrão (todos os arquivos)
* @orgateccloud-bot

# Áreas críticas — revisão obrigatória
/api/                    @orgateccloud-bot
/horizon_blue_one/       @orgateccloud-bot
/nfa_extractor/          @orgateccloud-bot
/alembic/                @orgateccloud-bot

# Infra e CI/CD
/.github/                @orgateccloud-bot
/.github/workflows/      @orgateccloud-bot

# Segurança e licença — extra cuidado
/SECURITY.md             @orgateccloud-bot
/LICENSE                 @orgateccloud-bot
/.env.example            @orgateccloud-bot
/.gitignore              @orgateccloud-bot
COEOF

echo "→ Gerando .github/dependabot.yml"
cat > .github/dependabot.yml <<'DEPEOF'
version: 2

updates:
  # Python (backend)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "America/Sao_Paulo"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "python"
    reviewers:
      - "orgateccloud-bot"
    commit-message:
      prefix: "chore(deps)"
      include: "scope"
    groups:
      python-minor:
        update-types:
          - "minor"
          - "patch"

  # Frontend (npm)
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "America/Sao_Paulo"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "frontend"
    reviewers:
      - "orgateccloud-bot"
    commit-message:
      prefix: "chore(deps)"
      include: "scope"
    groups:
      npm-minor:
        update-types:
          - "minor"
          - "patch"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
    labels:
      - "dependencies"
      - "ci"
    reviewers:
      - "orgateccloud-bot"
    commit-message:
      prefix: "ci(deps)"
DEPEOF

echo "→ Gerando .github/ISSUE_TEMPLATE/bug_report.md"
mkdir -p .github/ISSUE_TEMPLATE
cat > .github/ISSUE_TEMPLATE/bug_report.md <<'BUGEOF'
---
name: 🐛 Bug Report
about: Reportar um comportamento incorreto do sistema
title: "[BUG] "
labels: ["bug", "triage"]
assignees: ["orgateccloud-bot"]
---

## Descrição do bug

<!-- Descreva o que está acontecendo de forma clara e objetiva -->

## Como reproduzir

Passos para reproduzir o comportamento:

1. Vá em '...'
2. Execute '...'
3. Veja o erro

## Comportamento esperado

<!-- O que deveria acontecer? -->

## Comportamento observado

<!-- O que está acontecendo de fato? Cole logs, stacktraces, prints -->

```
[cole logs aqui — REMOVA qualquer credencial/token/dado pessoal]
```

## Ambiente

- OS: <!-- Windows 11 / Ubuntu 22.04 / macOS 14 -->
- Python: <!-- 3.12.x -->
- Browser (se frontend): <!-- Chrome 120 -->
- Versão / commit: <!-- git rev-parse HEAD -->

## Contexto adicional

<!-- Screenshots, configurações específicas, dados de tenant (anonimizados) -->

## Impacto

- [ ] 🔴 Bloqueia operação em produção
- [ ] 🟠 Degrada performance ou confiabilidade
- [ ] 🟡 Inconveniente, mas há workaround
- [ ] 🟢 Cosmético / qualidade
BUGEOF

echo "→ Gerando .github/ISSUE_TEMPLATE/feature_request.md"
cat > .github/ISSUE_TEMPLATE/feature_request.md <<'FEATEOF'
---
name: ✨ Feature Request
about: Sugerir uma nova funcionalidade ou melhoria
title: "[FEAT] "
labels: ["enhancement", "triage"]
assignees: ["orgateccloud-bot"]
---

## Problema / Necessidade

<!-- Que problema essa feature resolve? Quem é afetado? -->

## Solução proposta

<!-- Descreva como você imagina a feature funcionando -->

## Alternativas consideradas

<!-- Que outras abordagens poderiam resolver o mesmo problema? -->

## Critérios de aceitação

- [ ] <!-- O que precisa funcionar para a feature ser considerada pronta? -->
- [ ]
- [ ]

## Impacto esperado

- Quem se beneficia: <!-- usuários internos, clientes específicos, todos -->
- Frequência de uso: <!-- diária / semanal / pontual -->
- Métrica afetada: <!-- tempo de auditoria, custo de tokens, NPS, etc. -->

## Contexto adicional

<!-- Screenshots, mockups, links para discussões, regulamentação aplicável -->
FEATEOF

echo "→ Gerando .github/ISSUE_TEMPLATE/config.yml"
cat > .github/ISSUE_TEMPLATE/config.yml <<'CFGEOF'
blank_issues_enabled: false
contact_links:
  - name: 🔒 Vulnerabilidade de Segurança
    url: https://github.com/orgateccloud-bot/AudiOrg-1.1/security/advisories/new
    about: NÃO abra issue pública para vulnerabilidades. Use o canal privado de Security Advisories.
  - name: 💬 Dúvida ou Suporte
    url: mailto:orgatec.cloud@gmail.com
    about: Para dúvidas comerciais, suporte ou licenciamento, envie e-mail.
CFGEOF

echo "→ Gerando body do PR em /tmp/pr3-body.md"
cat > /tmp/pr3-body.md <<'PRBEOF'
## Resumo

Adiciona infraestrutura de governança para o repositório público:

- **LICENSE** — Proprietary / All Rights Reserved (ORGATEC) protegendo o IP do motor de auditoria fiscal, mantendo o código visível para transparência e auditoria
- **SECURITY.md** — política de reporte de vulnerabilidades com SLA por severidade (24h–5d) e canal de Security Advisories
- **.github/CODEOWNERS** — `@orgateccloud-bot` como owner padrão + áreas críticas (api, horizon_blue_one, nfa_extractor, alembic, infra)
- **.github/dependabot.yml** — atualização semanal de pip + npm (frontend/) e mensal de github-actions, agrupando minor/patch
- **.github/ISSUE_TEMPLATE/bug_report.md** — template de bug com classificação de impacto
- **.github/ISSUE_TEMPLATE/feature_request.md** — template de feature com critérios de aceitação
- **.github/ISSUE_TEMPLATE/config.yml** — desabilita blank issues e direciona segurança ao canal privado

## Test plan

- [ ] Dependabot detecta dependências e abre PRs após o merge
- [ ] CODEOWNERS aplica revisor automático em novos PRs
- [ ] Issue templates aparecem ao clicar em "New issue"
- [ ] Link para Security Advisories funciona
- [ ] CI continua verde

## Pós-merge

Ativar **Branch Protection** em `main` via UI:
`Settings → Branches → Add rule → main`
- Require pull request before merging
- Require status checks to pass: `Python Tests`, `Frontend Build`, `Security Scan`
- Require review from Code Owners
- Block force pushes
PRBEOF

echo "→ Commit"
git add LICENSE SECURITY.md .github/
git commit -m "chore: governanca do repo (LICENSE, SECURITY, CODEOWNERS, Dependabot, issue templates)"

echo "→ Push para origin"
git push -u origin chore/governanca-repo

echo "→ Criando PR #3"
GH_TOKEN=$GITHUB_TOKEN gh pr create \
  --base main \
  --head chore/governanca-repo \
  --title "chore: governanca do repo (LICENSE, SECURITY, CODEOWNERS, Dependabot, issue templates)" \
  --body-file /tmp/pr3-body.md

echo "✅ Pronto. PR #3 criado."
