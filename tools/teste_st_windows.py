"""Executavel isolado para validar o motor ICMS-ST com uma base exportada.

Este modulo nao inicia o FiscalPro completo e nao usa o banco persistente do usuario.
Ele carrega somente a tabela ST/MG do JSON criado pelo exportador de base fiscal e
abre a tela XML -> ICMS-ST -> Excel com os mesmos servicos da branch em teste.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

FORMATO_ESPERADO = "FISCALPRO_BASE_FISCAL_SOMENTE_LEITURA_V1"

# Quando executado como "python tools/teste_st_windows.py", o Python inclui
# "tools" no sys.path, não a raiz do projeto. Acrescentamos a raiz somente
# na execução por código-fonte; no executável PyInstaller os módulos já ficam
# no ambiente empacotado.
if not getattr(sys, "frozen", False):
    _raiz_projeto = Path(__file__).resolve().parents[1]
    if str(_raiz_projeto) not in sys.path:
        sys.path.insert(0, str(_raiz_projeto))


def _pasta_execucao() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _carregar_base(caminho: Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    with caminho.open("r", encoding="utf-8-sig") as arquivo:
        dados = json.load(arquivo)
    if str(dados.get("formato") or "") != FORMATO_ESPERADO:
        raise ValueError("O arquivo selecionado nao e uma exportacao de base fiscal do FiscalPro.")
    tabelas = dados.get("tabelas") or {}
    regras = tabelas.get("st_mg_oficial") or []
    if not isinstance(regras, list) or not regras:
        raise ValueError("A exportacao nao contem a tabela ST/MG.")
    status_lista = tabelas.get("st_mg_base_status") or []
    status = dict(status_lista[0]) if status_lista else {}
    return [dict(item) for item in regras], status, dict(dados.get("contagens") or {})


def _adaptar_repositorio(regras: list[dict[str, Any]], status: dict[str, Any]) -> None:
    # Protecao adicional: mesmo que algum modulo tente usar caminhos persistentes,
    # a execucao de teste aponta para uma pasta temporaria separada.
    pasta_isolada = Path(tempfile.gettempdir()) / "FiscalPro_Teste_ST_PR13"
    pasta_isolada.mkdir(parents=True, exist_ok=True)
    os.environ["FISCALPRO_DATA_DIR"] = str(pasta_isolada)

    from src.inteligencia.base_oficial.repositorio import BaseOficialRepository

    regras_memoria = [dict(item) for item in regras]
    segmentos = sorted({str(item.get("segmento") or "") for item in regras_memoria if item.get("segmento")})
    atualizado = max((str(item.get("atualizado_em") or "") for item in regras_memoria), default="")

    def buscar_st_mg_por_ncm(ncm: str, segmento: str | None = None):
        codigo = "".join(c for c in str(ncm or "") if c.isdigit())
        seg = str(segmento or "").strip().upper()
        encontrados = []
        for item in regras_memoria:
            prefixo = str(item.get("ncm_digitos") or "").strip()
            if not prefixo or not codigo.startswith(prefixo):
                continue
            if seg and str(item.get("segmento") or "").strip().upper() != seg:
                continue
            encontrados.append(dict(item))
        if seg:
            encontrados.sort(
                key=lambda item: (
                    -len(str(item.get("ncm_digitos") or "")),
                    str(item.get("item") or ""),
                    str(item.get("cest") or ""),
                )
            )
        else:
            encontrados.sort(
                key=lambda item: (
                    -len(str(item.get("ncm_digitos") or "")),
                    str(item.get("segmento") or ""),
                    str(item.get("item") or ""),
                    str(item.get("cest") or ""),
                )
            )
        return encontrados

    def resumo_st_mg():
        return {
            "registros": len(regras_memoria),
            "segmentos": len(segmentos),
            "segmentos_lista": segmentos,
            "atualizado_em": atualizado,
            "base_completa": bool(status.get("base_completa")),
            "versao_schema": int(status.get("versao_schema") or 0),
            "paginas": int(status.get("paginas") or 0),
            "referencia": str(status.get("referencia") or ""),
            "fonte_url": str(status.get("fonte_url") or ""),
            "sincronizado_em": str(status.get("sincronizado_em") or ""),
        }

    BaseOficialRepository.buscar_st_mg_por_ncm = staticmethod(buscar_st_mg_por_ncm)
    BaseOficialRepository.resumo_st_mg = staticmethod(resumo_st_mg)


def _localizar_base_sem_interface() -> Path | None:
    informada = os.environ.get("FISCALPRO_BASE_FISCAL_TESTE", "").strip()
    if informada:
        caminho = Path(informada).expanduser().resolve()
        if caminho.is_file():
            return caminho
    candidatas = sorted(
        _pasta_execucao().glob("BASE_FISCAL_PARA_TESTE_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidatas[0] if candidatas else None


def _selecionar_base() -> Path | None:
    encontrada = _localizar_base_sem_interface()
    if encontrada is not None:
        return encontrada

    import tkinter as tk
    from tkinter import filedialog

    raiz = tk.Tk()
    raiz.withdraw()
    try:
        escolhido = filedialog.askopenfilename(
            title="Selecione BASE_FISCAL_PARA_TESTE_*.json",
            filetypes=(("Base fiscal FiscalPro", "*.json"), ("Todos os arquivos", "*.*")),
        )
    finally:
        raiz.destroy()
    return Path(escolhido).resolve() if escolhido else None


def _validar_linha_comando(caminho: Path) -> int:
    regras, status, contagens = _carregar_base(caminho)
    _adaptar_repositorio(regras, status)
    from src.inteligencia.base_oficial.repositorio import BaseOficialRepository

    candidatos = BaseOficialRepository.buscar_st_mg_por_ncm("85365090")
    cests = sorted({str(item.get("cest") or "") for item in candidatos})
    print(
        json.dumps(
            {
                "arquivo": caminho.name,
                "regras_st_mg": len(regras),
                "contagens": contagens,
                "base_completa": bool(status.get("base_completa")),
                "versao_schema": int(status.get("versao_schema") or 0),
                "cests_85365090": cests,
            },
            ensure_ascii=False,
        )
    )
    return 0 if "01.065.00" in cests and "09.004.00" in cests else 2


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--validar-base":
        return _validar_linha_comando(Path(sys.argv[2]).expanduser().resolve())

    caminho = _selecionar_base()
    if caminho is None:
        return 1

    import tkinter as tk
    from tkinter import messagebox

    try:
        regras, status, _ = _carregar_base(caminho)
        _adaptar_repositorio(regras, status)
    except Exception as erro:
        raiz_erro = tk.Tk()
        raiz_erro.withdraw()
        try:
            messagebox.showerror("FiscalPro - Teste ST", str(erro), parent=raiz_erro)
        finally:
            raiz_erro.destroy()
        return 2

    from src.ui.janela_xml_icms_st import JanelaXMLICMSST

    raiz = tk.Tk()
    raiz.withdraw()
    janela = JanelaXMLICMSST(raiz)
    janela.title("FiscalPro - TESTE ICMS-ST (base fiscal exportada)")
    janela.status_var.set(
        f"TESTE ISOLADO - base: {caminho.name} - {len(regras)} regras ST/MG."
    )

    def encerrar() -> None:
        try:
            janela.destroy()
        finally:
            raiz.destroy()

    janela.protocol("WM_DELETE_WINDOW", encerrar)

    def ao_destruir(evento) -> None:
        if evento.widget is janela and raiz.winfo_exists():
            raiz.after_idle(raiz.destroy)

    janela.bind("<Destroy>", ao_destruir, add="+")
    raiz.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
