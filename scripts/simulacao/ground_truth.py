"""
Comparação com ground truth — extrai PDFs do ZIP de auditoria anterior
e calcula similaridade textual com os resumos da nova auditoria.
"""
from __future__ import annotations

import re
import tempfile
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber


def _normalizar_nome(s: str) -> str:
    """JOSE AILTON, jose-ailton, JOSE_AILTON -> joseailton"""
    s = s.upper().replace(" ", "").replace("_", "").replace("-", "")
    return re.sub(r"[^A-Z]", "", s)


def extrair_zip_temporario(zip_path: Path) -> Path:
    """Descompacta o ZIP em diretório temporário e retorna o caminho.
    Caller é responsável por limpar (ou usar TemporaryDirectory)."""
    tmp = Path(tempfile.mkdtemp(prefix="ground_truth_"))
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(tmp)
    return tmp


def listar_pdfs_gt(diretorio: Path) -> dict[str, Path]:
    """Mapeia nome_normalizado_produtor -> Path do PDF."""
    mapa: dict[str, Path] = {}
    for pdf in diretorio.rglob("*.pdf"):
        nome = pdf.stem.upper()
        # AUDITORIA_<PRODUTOR>_2026 -> <PRODUTOR>
        m = re.match(r"^AUDITORIA[_\s-]+(.+?)[_\s-]+\d{4}$", nome)
        if m:
            chave = _normalizar_nome(m.group(1))
        else:
            chave = _normalizar_nome(nome)
        mapa[chave] = pdf
    return mapa


def extrair_texto_pdf(pdf_path: Path) -> str:
    """Concatena texto de todas as páginas. Retorna string vazia em erro."""
    try:
        textos: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                textos.append(t)
        return "\n".join(textos)
    except Exception:
        return ""


def calcular_similaridade(texto_a: str, texto_b: str) -> float:
    """Razão SequenceMatcher entre 2 textos. 0..1."""
    if not texto_a or not texto_b:
        return 0.0
    # Limita para 50000 chars cada lado para não estourar
    a = texto_a[:50000].lower()
    b = texto_b[:50000].lower()
    return SequenceMatcher(None, a, b).ratio()


def comparar(
    consumo_consolidado: list[dict],
    zip_path: Path,
) -> dict[str, dict]:
    """Para cada produtor no consumo_consolidado, busca o PDF correspondente
    no ZIP e calcula similaridade entre o resumo gerado e o texto do GT.

    Retorna: {produtor: {tem_gt, similaridade, gt_pdf}}
    """
    if not zip_path.exists():
        return {item["produtor"]: {"tem_gt": False, "motivo": "zip_ausente"}
                for item in consumo_consolidado}

    tmp_dir = extrair_zip_temporario(zip_path)
    try:
        gt_map = listar_pdfs_gt(tmp_dir)
        resultado: dict[str, dict] = {}
        for item in consumo_consolidado:
            produtor = item["produtor"]
            chave = _normalizar_nome(produtor)
            gt_pdf = gt_map.get(chave)
            if gt_pdf is None:
                # tenta substring (HELIO JOSE -> HELIOJOSE pode bater com HELIO)
                for k, p in gt_map.items():
                    if chave in k or k in chave:
                        gt_pdf = p
                        break
            if gt_pdf is None:
                resultado[produtor] = {"tem_gt": False, "motivo": "produtor_ausente_no_gt"}
                continue

            texto_gt = extrair_texto_pdf(gt_pdf)

            # Compõe texto da nova auditoria a partir dos resultados dos agentes
            partes: list[str] = []
            for aid, agente_out in (item.get("resultados") or {}).items():
                if isinstance(agente_out, dict):
                    partes.append(str(agente_out.get("recomendacao_geral", "")))
                    partes.append(str(agente_out.get("resumo_executivo", "")))
            texto_novo = " ".join(p for p in partes if p)

            sim = calcular_similaridade(texto_gt, texto_novo)
            resultado[produtor] = {
                "tem_gt":        True,
                "gt_pdf":        gt_pdf.name,
                "similaridade":  round(sim, 3),
                "tamanho_gt":    len(texto_gt),
                "tamanho_novo":  len(texto_novo),
            }
        return resultado
    finally:
        # cleanup
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
