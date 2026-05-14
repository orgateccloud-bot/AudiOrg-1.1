#!/bin/bash
# archive_agents.sh — P2-A: Script para arquivar 26 agentes em standby
# Execução: bash scripts/archive_agents.sh

set -e

ARCHIVE_DIR="horizon_blue_one/agents/_archived"
SOURCE_DIR="horizon_blue_one/agents"

echo "📦 P2-A: Arquivando 26 agentes em standby..."

# Criar diretório de arquivo
mkdir -p "$ARCHIVE_DIR"
touch "$ARCHIVE_DIR/.gitkeep"

# Lista de agentes a arquivar (a00-a06 e a09-a27)
AGENTS=(
  "a00_ceo_agent.py"
    "a01_junior_agent.py"
      "a02_protetor_agent.py"
        "a03_zero_trust_agent.py"
          "a04_vigilante_agent.py"
            "a05_engenheiro_erp_agent.py"
              "a06_extrator_agent.py"
                "a09_auditor_ti_agent.py"
                  "a10_auditor_patrimonio_agent.py"
                    "a11_planejador_tributario_agent.py"
                      "a12_descobridor_deducoes_agent.py"
                        "a13_monitor_conformidade_agent.py"
                          "a14_avaliador_risco_agent.py"
                            "a15_juridico_ext_agent.py"
                              "a16_lgpd_agent.py"
                                "a17_previsor_caixa_agent.py"
                                  "a18_analista_c_suite_agent.py"
                                    "a19_contabilista_ia_agent.py"
                                      "a20_esocial_ia_agent.py"
                                        "a21_auditor_icms_agent.py"
                                          "a22_auditor_itr_agent.py"
                                            "a23_analista_anomalias_agent.py"
                                              "a24_classificador_cfop_agent.py"
                                                "a25_auditor_lcdpr_agent.py"
                                                  "a26_auditor_biologicos_agent.py"
                                                    "a27_epsilon_forensic_agent.py"
                                                    )

                                                    # Mover cada arquivo
                                                    for agent in "${AGENTS[@]}"; do
                                                      if [ -f "$SOURCE_DIR/$agent" ]; then
                                                          git mv "$SOURCE_DIR/$agent" "$ARCHIVE_DIR/" || echo "⚠️  Já arquivado ou não encontrado: $agent"
                                                            else
                                                                echo "⏭️  Não encontrado: $agent"
                                                                  fi
                                                                  done

                                                                  echo "✅ Arquivamento concluído!"
                                                                  echo "📋 Próximo passo: git commit -m 'chore(agents): P2-A arquivar 26 agentes em standby'"
