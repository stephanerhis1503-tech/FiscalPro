"""Enquadramento oficial de PIS/Cofins monofásico para autopeças.

A regra abaixo deriva da Lei nº 10.485/2002, especialmente do art. 3º,
§ 2º e dos Anexos I e II. O serviço é deliberadamente conservador:

* confirma automaticamente somente os códigos do Anexo I que não dependem
  de EX TIPI nem de descrição complementar;
* exige revisão quando o enquadramento depende de EX TIPI ou de destinação
  específica descrita no Anexo II;
* aplica CST 04 e alíquota zero apenas em saída/venda de produto novo por
  comerciante atacadista ou varejista;
* não substitui a análise da entrada, do Simples Nacional ou de fatos geradores
  a partir de 2027, quando a transição da Reforma Tributária exige nova regra.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from src.services.empresas_regimes_service import EmpresasRegimesService


URL_LEI_10485 = "https://www.planalto.gov.br/ccivil_03/leis/2002/L10485compilado.htm"
URL_TABELA_4310 = "https://sped.rfb.gov.br/item/show/1638"


@dataclass(frozen=True)
class ResultadoPISCOFINSMonofasico:
    ncm: str
    status: str
    confirmado: bool
    enquadramento: str
    descricao_legal: str
    cst_pis: str = ""
    aliquota_pis: float = 0.0
    cst_cofins: str = ""
    aliquota_cofins: float = 0.0
    fundamento: str = ""
    artigo: str = ""
    fonte_url: str = URL_LEI_10485
    tabela_sped_url: str = URL_TABELA_4310
    observacao: str = ""
    exige_revisao: bool = True
    codigo_legal: str = ""
    exclusao_confirmada: bool = False
    destinacao_identificada: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PISCOFINSMonofasicoService:
    """Reconhece o regime monofásico de autopeças com base legal rastreável."""

    # Anexo I da Lei nº 10.485/2002. Os padrões sem EX podem ser confirmados
    # diretamente pelo NCM. O tamanho do padrão indica posição/subposição.
    _ANEXO_I_SEM_EX: Tuple[Tuple[str, str], ...] = (
        ("40161010", "Obras de borracha celular"),
        ("6813", "Guarnições de fricção"),
        ("70071100", "Vidros temperados"),
        ("70072100", "Vidros laminados"),
        ("70091000", "Espelhos retrovisores"),
        ("83012000", "Fechaduras para veículos automóveis"),
        ("83023000", "Guarnições, ferragens e artigos semelhantes para veículos"),
        ("84073390", "Motores de pistão alternativo"),
        ("84073490", "Motores de pistão alternativo"),
        ("840820", "Motores para propulsão de veículos"),
        ("840991", "Partes reconhecíveis como destinadas aos motores de ignição por centelha"),
        ("840999", "Outras partes de motores"),
        ("841330", "Bombas para combustíveis, lubrificantes ou líquidos de arrefecimento"),
        ("84148021", "Turboalimentadores de ar para motores de ignição por compressão"),
        ("84148022", "Outros compressores de ar para veículos automóveis"),
        ("841520", "Máquinas e aparelhos de ar-condicionado para veículos"),
        ("84212300", "Filtros de óleo ou combustível para motores"),
        ("84213100", "Filtros de entrada de ar para motores"),
        ("84314100", "Caçambas, pás e garras"),
        ("84314200", "Lâminas de bulldozers ou angledozers"),
        ("84339090", "Partes de máquinas agrícolas"),
        ("848310", "Árvores de transmissão e manivelas"),
        ("84832000", "Mancais com rolamentos incorporados"),
        ("848330", "Mancais sem rolamentos; bronzes"),
        ("848340", "Engrenagens e rodas de fricção"),
        ("848350", "Volantes e polias"),
        ("850520", "Acoplamentos, embreagens, freios e aparelhos eletromagnéticos"),
        ("85071000", "Acumuladores de chumbo para arranque"),
        ("8511", "Aparelhos e dispositivos elétricos de ignição ou arranque"),
        ("851220", "Aparelhos elétricos de iluminação ou sinalização visual"),
        ("85123000", "Aparelhos de sinalização acústica"),
        ("851240", "Limpadores, degeladores e desembaçadores"),
        ("85129000", "Partes dos aparelhos da posição 85.12"),
        ("85272", "Aparelhos receptores de radiodifusão para veículos"),
        ("853910", "Faróis e unidades seladas"),
        ("85443000", "Jogos de fios para veículos"),
        ("870600", "Chassis com motor"),
        ("8707", "Carroçarias"),
        ("8708", "Partes e acessórios dos veículos das posições 87.01 a 87.05"),
        ("90292010", "Velocímetros e tacômetros"),
        ("90299010", "Partes de velocímetros e tacômetros"),
        ("90303921", "Instrumentos para medição de grandezas elétricas"),
        ("90318040", "Aparelhos para análise de gases de escapamento"),
        ("9032892", "Instrumentos automáticos para controle em veículos"),
        ("91040000", "Relógios para painéis de instrumentos"),
        ("94012000", "Assentos para veículos automóveis"),
    )

    # Pneus novos e câmaras-de-ar possuem regime monofásico próprio no art. 5º
    # da Lei nº 10.485/2002 e alíquota zero na revenda atacadista/varejista.
    _PNEUS_CAMARAS: Tuple[Tuple[str, str], ...] = (
        ("4011", "Pneus novos de borracha"),
        ("4013", "Câmaras-de-ar de borracha"),
    )

    # Anexo I com EX TIPI. Sem o EX informado, o enquadramento não é confirmado.
    _ANEXO_I_COM_EX: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
        ("40169990", ("03", "05"), "Outras obras de borracha — somente EX 03 e 05"),
        ("73201000", ("01",), "Molas de folhas — somente EX 01"),
        ("84139100", ("01",), "Partes de bombas — somente EX 01"),
        ("84818099", ("01", "02"), "Outros dispositivos para canalizações — somente EX 01 e 02"),
        ("85365090", ("01",), "Outros interruptores — somente EX 01"),
    )

    # Itens do Anexo II dependem da descrição e da destinação do produto.
    _ANEXO_II_CONDICIONAL: Tuple[Tuple[str, str], ...] = (
        ("4009", "Tubos de borracha com acessórios próprios para máquinas e veículos específicos"),
        ("8431", "Partes reconhecíveis como destinadas a máquinas específicas"),
        ("84089090", "Motores próprios para máquinas específicas"),
        ("84122110", "Cilindros hidráulicos próprios para máquinas específicas"),
        ("84122190", "Outros cilindros hidráulicos próprios para máquinas específicas"),
        ("84123110", "Cilindros pneumáticos próprios para veículos específicos"),
        ("84136019", "Bombas volumétricas rotativas próprias para máquinas e veículos específicos"),
        ("84148019", "Compressores de ar próprios para veículos específicos"),
        ("84149039", "Caixas de ventilação para veículos autopropulsados"),
        ("84329000", "Partes de máquinas agrícolas específicas"),
        ("84811000", "Válvulas redutoras próprias para máquinas e veículos específicos"),
        ("84812090", "Válvulas para transmissões óleo-hidráulicas ou pneumáticas"),
        ("84818092", "Válvulas solenoides próprias para máquinas e veículos específicos"),
        ("8483601", "Embreagens de fricção próprias para máquinas específicas"),
        ("85011019", "Motores elétricos próprios para acionamento de vidros de veículos"),
    )

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        texto = str(valor or "").strip().upper()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return " ".join(texto.split())

    @staticmethod
    def _normalizar_ncm(valor: Any) -> str:
        codigo = "".join(c for c in str(valor or "") if c.isdigit())
        if len(codigo) != 8:
            raise ValueError("O NCM deve possuir 8 dígitos.")
        return codigo

    @staticmethod
    def _normalizar_ex(valor: Any) -> str:
        digitos = "".join(c for c in str(valor or "") if c.isdigit())
        return digitos.zfill(2) if digitos and len(digitos) <= 2 else digitos

    @classmethod
    def _corresponde(cls, ncm: str, padrao: str) -> bool:
        return ncm.startswith(padrao)

    @classmethod
    def _indica_motocicleta(cls, contexto: Dict[str, Any], descricao_normalizada: str) -> bool:
        """Reconhece apenas sinais fortes de aplicação em motocicleta (posição 87.11).

        A finalidade informada pelo usuário prevalece. A descrição só é usada como
        apoio quando contém a palavra moto/motocicleta ou um modelo acompanhado de
        cilindrada/número, evitando transformar nomes genéricos em conclusão fiscal.
        """
        finalidade_auto = cls._normalizar_texto(contexto.get("finalidade_automotiva"))
        if finalidade_auto and "NAO E PECA AUTOMOTIVA" not in finalidade_auto:
            if "MOTOCICLETA" in finalidade_auto or "MOTO" in finalidade_auto:
                return True

        if re.search(r"\bMOTOCICLET(?:A|AS)?\b|\bMOTO(?:S)?\b", descricao_normalizada):
            return True

        # Modelos muito usuais de motocicletas. Exigimos número/cilindrada para
        # reduzir falsos positivos (ex.: FAN isolado pode ser outra descrição).
        padrao_modelo = re.compile(
            r"\b(?:XRE|NXR|BROS|TITAN|FAN|BIZ|PCX|CBR|CB|CG|CRF|POP|SAHARA|TWISTER|"
            r"FAZER|LANDER|XTZ|YBR|NMAX|XMAX|MT|NINJA|VERSYS)\s*[- ]?\s*\d{2,4}\b"
        )
        return bool(padrao_modelo.search(descricao_normalizada))

    @classmethod
    def _localizar_enquadramento(cls, ncm: str, ex_tipi: str = "") -> Dict[str, Any]:
        ex = cls._normalizar_ex(ex_tipi)

        for padrao, descricao in cls._PNEUS_CAMARAS:
            if cls._corresponde(ncm, padrao):
                return {
                    "tipo": "PNEUS E CÂMARAS — ART. 5º",
                    "codigo_legal": padrao,
                    "descricao": descricao,
                    "confirmavel": True,
                    "motivo": "Produto abrangido diretamente pelo art. 5º da Lei nº 10.485/2002.",
                }

        for padrao, descricao in cls._ANEXO_I_SEM_EX:
            if cls._corresponde(ncm, padrao):
                return {
                    "tipo": "ANEXO I",
                    "codigo_legal": padrao,
                    "descricao": descricao,
                    "confirmavel": True,
                    "motivo": "Código abrangido diretamente pelo Anexo I da Lei nº 10.485/2002.",
                }

        for padrao, ex_validos, descricao in cls._ANEXO_I_COM_EX:
            if not cls._corresponde(ncm, padrao):
                continue
            if ex and ex in ex_validos:
                return {
                    "tipo": "ANEXO I — EX TIPI",
                    "codigo_legal": f"{padrao} EX {ex}",
                    "descricao": descricao,
                    "confirmavel": True,
                    "motivo": f"NCM e EX TIPI {ex} abrangidos pelo Anexo I.",
                }
            return {
                "tipo": "ANEXO I — EX TIPI",
                "codigo_legal": padrao,
                "descricao": descricao,
                "confirmavel": False,
                "motivo": "O enquadramento depende do EX TIPI. Informe o EX para confirmar.",
            }

        for padrao, descricao in cls._ANEXO_II_CONDICIONAL:
            if cls._corresponde(ncm, padrao):
                return {
                    "tipo": "ANEXO II",
                    "codigo_legal": padrao,
                    "descricao": descricao,
                    "confirmavel": False,
                    "motivo": (
                        "O Anexo II exige conferir a descrição e a destinação específica do produto; "
                        "o NCM isolado não basta."
                    ),
                }

        return {
            "tipo": "NÃO LOCALIZADO",
            "codigo_legal": "",
            "descricao": "",
            "confirmavel": False,
            "motivo": (
                "O código não consta dos Anexos I e II da Lei nº 10.485/2002. "
                "Isso não significa que o NCM seja inválido; significa apenas que não houve "
                "enquadramento automático neste regime monofásico específico."
            ),
        }

    @staticmethod
    def _data_operacao(contexto: Dict[str, Any]) -> date:
        texto = str(contexto.get("data_operacao") or "").strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato).date()
            except ValueError:
                continue
        return date.today()

    @classmethod
    def analisar(
        cls,
        ncm: Any,
        contexto: Optional[Dict[str, Any]] = None,
        descricao: str = "",
        ex_tipi: str = "",
    ) -> Dict[str, Any]:
        codigo = cls._normalizar_ncm(ncm)
        contexto = EmpresasRegimesService.aplicar_contexto(contexto)
        operacao = cls._normalizar_texto(contexto.get("operacao"))
        regime = cls._normalizar_texto(contexto.get("regime"))
        finalidade = cls._normalizar_texto(contexto.get("finalidade"))
        descricao_normalizada = cls._normalizar_texto(descricao)
        enquadramento = cls._localizar_enquadramento(codigo, ex_tipi)

        fundamento = "Lei nº 10.485/2002"
        if enquadramento["tipo"].startswith("PNEUS E CÂMARAS"):
            artigo = "art. 5º, caput e parágrafo único"
        elif enquadramento["tipo"].startswith("ANEXO I"):
            artigo = "art. 3º, § 2º, inciso I, combinado com o caput e o Anexo I"
        else:
            artigo = "art. 3º, § 2º, inciso I, combinado com o caput e o Anexo II"

        if enquadramento["tipo"] == "NÃO LOCALIZADO":
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="NÃO ENQUADRADO",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao=enquadramento["motivo"],
                exige_revisao=True,
            ).para_dict()

        if cls._data_operacao(contexto) >= date(2027, 1, 1):
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="REVISAR REFORMA TRIBUTÁRIA",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao=(
                    "A regra de PIS/Cofins foi identificada, mas a operação está em período posterior a 2026. "
                    "Revisar a substituição pela CBS conforme a legislação vigente na data."
                ),
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        if any(palavra in descricao_normalizada for palavra in ("USADO", "USADA", "RECONDICIONADO", "RECONDICIONADA")):
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="REVISAR PRODUTO USADO",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo="art. 6º",
                observacao="A Lei nº 10.485/2002 não se aplica a produtos usados.",
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        # 17.8.83 — o item 11 do Anexo II não abrange qualquer válvula 84811000.
        # A própria descrição legal exige que a válvula seja própria para as máquinas/
        # veículos ali enumerados (84.29, 8433... e 87.01 a 87.06). Motocicletas da
        # posição 87.11 não constam desse item. Quando a aplicação em moto estiver
        # explicitamente informada (ou fortemente identificada na descrição), podemos
        # confirmar a EXCLUSÃO deste enquadramento monofásico e seguir para a regra
        # normal do regime, sem aplicar CST 04/alíquota zero por engano.
        if (
            codigo == "84811000"
            and enquadramento["tipo"] == "ANEXO II"
            and cls._indica_motocicleta(contexto, descricao_normalizada)
        ):
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="NÃO ENQUADRADO",
                confirmado=False,
                enquadramento="ANEXO II — FORA DA DESCRIÇÃO LEGAL",
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo="Anexo II, item 11",
                observacao=(
                    "Aplicação identificada em motocicleta (posição 87.11). O item 11 do Anexo II "
                    "da Lei nº 10.485/2002 restringe o NCM 8481.10.00 às válvulas próprias para "
                    "as máquinas e veículos expressamente listados, incluindo 87.01 a 87.06, mas "
                    "não a posição 87.11. Portanto, este produto não deve receber alíquota zero "
                    "monofásica apenas pelo NCM; o FiscalPro deve continuar para a tributação "
                    "normal do regime e demais exceções aplicáveis."
                ),
                exige_revisao=False,
                codigo_legal=enquadramento["codigo_legal"],
                exclusao_confirmada=True,
                destinacao_identificada="MOTOCICLETA (87.11)",
            ).para_dict()

        if not enquadramento["confirmavel"]:
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="REVISÃO NECESSÁRIA",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao=enquadramento["motivo"],
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        eh_saida = any(token in operacao for token in ("SAIDA", "VENDA", "REVENDA"))
        if not eh_saida:
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="REVISAR OPERAÇÃO",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao=(
                    "O produto está na relação monofásica, mas CST 04 e alíquota zero são conclusão para a "
                    "receita de venda do comerciante. Entrada, devolução, transferência e industrialização "
                    "exigem análise própria."
                ),
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        if finalidade and "REVENDA" not in finalidade:
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="REVISAR FINALIDADE",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao="A conclusão automática foi preparada para mercadoria nova destinada à revenda.",
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        if "SIMPLES" in regime or regime == "MEI":
            return ResultadoPISCOFINSMonofasico(
                ncm=codigo,
                status="MONOFÁSICO — REVISAR CST DO SIMPLES",
                confirmado=False,
                enquadramento=enquadramento["tipo"],
                descricao_legal=enquadramento["descricao"],
                fundamento=fundamento,
                artigo=artigo,
                observacao=(
                    "O produto é monofásico, porém a empresa está no Simples Nacional/MEI. Segregar a receita "
                    "corretamente no PGDAS-D e revisar o CST utilizado no documento fiscal conforme o sistema."
                ),
                exige_revisao=True,
                codigo_legal=enquadramento["codigo_legal"],
            ).para_dict()

        return ResultadoPISCOFINSMonofasico(
            ncm=codigo,
            status="CONFIRMADO — MONOFÁSICO",
            confirmado=True,
            enquadramento=enquadramento["tipo"],
            descricao_legal=enquadramento["descricao"],
            cst_pis="04",
            aliquota_pis=0.0,
            cst_cofins="04",
            aliquota_cofins=0.0,
            fundamento=fundamento,
            artigo=artigo,
            observacao=(
                "Revenda de produto novo por comerciante atacadista ou varejista: alíquotas de PIS/Pasep e "
                "Cofins reduzidas a zero."
            ),
            exige_revisao=False,
            codigo_legal=enquadramento["codigo_legal"],
        ).para_dict()

    @staticmethod
    def aplicar_ao_parecer(parecer: Any, resultado: Dict[str, Any]) -> Any:
        """Aplica a conclusão oficial ao parecer em memória, sem alterar o cadastro local."""
        if parecer is None or not resultado.get("confirmado"):
            return parecer

        tributacao = parecer.tributacao_atual
        revisao_manual = bool(tributacao.get("Revisão manual"))
        if not revisao_manual:
            tributacao["CST PIS"] = resultado.get("cst_pis") or "04"
            tributacao["PIS"] = float(resultado.get("aliquota_pis") or 0.0)
            tributacao["CST COFINS"] = resultado.get("cst_cofins") or "04"
            tributacao["COFINS"] = float(resultado.get("aliquota_cofins") or 0.0)
            tributacao["Fonte PIS/COFINS"] = (
                f"{resultado.get('fundamento')} — {resultado.get('artigo')}"
            )
        else:
            tributacao["PIS/COFINS oficial — comparação"] = (
                f"CST {resultado.get('cst_pis') or '04'} / {float(resultado.get('aliquota_pis') or 0.0):.2f}% | "
                f"COFINS CST {resultado.get('cst_cofins') or '04'} / {float(resultado.get('aliquota_cofins') or 0.0):.2f}%"
            )
            aviso = "Existe regra manual salva; o enquadramento monofásico oficial foi mantido apenas para comparação e não sobrescreveu os valores manuais."
            if aviso not in parecer.alertas:
                parecer.alertas.append(aviso)

        base = f"{resultado.get('fundamento')}, {resultado.get('artigo')}"
        if base not in parecer.base_legal:
            parecer.base_legal.append(base)
        conclusao = (
            "PIS e COFINS confirmados como monofásicos na revenda: CST 04 e alíquota zero, "
            "conforme o enquadramento oficial da Lei nº 10.485/2002."
        )
        if conclusao not in parecer.conclusoes:
            parecer.conclusoes.insert(0, conclusao)
        fundamento = (
            f"NCM {resultado.get('ncm')} abrangido pelo {resultado.get('enquadramento')} "
            f"({resultado.get('codigo_legal')})."
        )
        if fundamento not in parecer.fundamentos:
            parecer.fundamentos.append(fundamento)
        if resultado.get("fonte_url") not in parecer.fontes:
            parecer.fontes.append(resultado.get("fonte_url"))

        # O motor anterior emitia um alerta genérico de ausência total de base
        # legal. Com PIS/Cofins confirmados, a pendência remanescente deve ficar
        # restrita aos tributos ainda não fundamentados, especialmente ICMS/ST.
        parecer.alertas = [
            item for item in parecer.alertas
            if "NENHUMA BASE LEGAL VIGENTE" not in PISCOFINSMonofasicoService._normalizar_texto(item)
        ]
        parecer.pendencias = [
            item for item in parecer.pendencias
            if "VINCULAR A LEGISLACAO OFICIAL" not in PISCOFINSMonofasicoService._normalizar_texto(item)
        ]
        pendencia_icms = "Vincular a legislação oficial de ICMS e ICMS-ST aplicável à operação."
        if pendencia_icms not in parecer.pendencias:
            parecer.pendencias.append(pendencia_icms)

        parecer.regras_aplicadas["piscofins_monofasico_oficial"] = dict(resultado)
        parecer.versao_motor = "14.2.1"
        return parecer
