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
