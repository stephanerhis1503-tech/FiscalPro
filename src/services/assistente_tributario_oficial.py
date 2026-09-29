from __future__ import annotations

import json
from datetime import datetime

from src.inteligencia.base_oficial.repositorio import BaseOficialRepository


class AssistenteTributarioOficial:
    """Gera uma análise explicável usando apenas a ficha local e evidências oficiais cadastradas."""

    @staticmethod
    def analisar(ficha) -> str:
        ncm = "".join(c for c in str(ficha.ncm) if c.isdigit())
        evidencias = BaseOficialRepository.listar_evidencias(ncm)
        fontes = BaseOficialRepository.listar_fontes()

        linhas = [
            "==============================",
            "FISCALPRO IA TRIBUTÁRIA",
            "==============================",
            f"NCM analisado: {ncm}",
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            "",
            "DIAGNÓSTICO",
        ]
        if getattr(ficha, "quantidade_variacoes", 0) > 1:
            linhas.append(f"⚠ Existem {ficha.quantidade_variacoes} perfis tributários diferentes na base interna.")
            linhas.append("A tributação deve ser confirmada pela descrição, CEST, operação e regime.")
        else:
            linhas.append("✓ A base interna apresentou um perfil tributário predominante.")

        linhas += [
            "",
            "TRIBUTAÇÃO ENCONTRADA NA BASE OPERACIONAL",
            f"ICMS: {getattr(ficha, 'icms', 0):.2f}% | CST: {getattr(ficha, 'cst_icms', '-')}",
            f"ICMS-ST: {getattr(ficha, 'icms_st', '-') } | CEST: {getattr(ficha, 'cest', '-')}",
            f"PIS: {getattr(ficha, 'aliquota_pis', 0):.2f}% | CST: {getattr(ficha, 'pis_cst', '-')}",
            f"COFINS: {getattr(ficha, 'aliquota_cofins', 0):.2f}% | CST: {getattr(ficha, 'cofins_cst', '-')}",
            "",
            "REFORMA TRIBUTÁRIA",
            f"CST IBS: {getattr(ficha, 'cst_ibs', '-')} | CST CBS: {getattr(ficha, 'cst_cbs', '-')}",
            f"cClassTrib: {getattr(ficha, 'cclasstrib', '-')}",
            f"IBS: {getattr(ficha, 'aliquota_ibs', 0):.2f}% | CBS: {getattr(ficha, 'aliquota_cbs', 0):.2f}%",
            "",
            "EVIDÊNCIAS OFICIAIS REGISTRADAS",
        ]
        if not evidencias:
            linhas.append("Nenhuma evidência específica para este NCM foi coletada ainda.")
        else:
            for ev in evidencias[:10]:
                try:
                    valor = json.loads(ev.get("valor_json") or "{}")
                except Exception:
                    valor = ev.get("valor_json")
                linhas.append(f"• {ev.get('tema')} — {ev.get('orgao') or ev.get('fonte_codigo')} — {ev.get('status')} — {valor}")

        linhas += ["", "FONTES OFICIAIS MONITORADAS"]
        for fonte in fontes:
            linhas.append(f"• {fonte['orgao']}: {fonte['nome']} [{fonte.get('ultimo_status') or 'não verificada'}]")

        confianca = float(getattr(ficha, "confiabilidade", 0) or 0)
        linhas += [
            "",
            f"NÍVEL DE CONFIANÇA DA BASE LOCAL: {confianca:.0f}%",
            "",
            "IMPORTANTE",
            "A análise é assistiva. Ela não transforma dados sem base legal em tributação validada.",
            "Resultados com variações ou sem evidência específica permanecem pendentes de revisão fiscal.",
        ]
        return "\n".join(linhas)
