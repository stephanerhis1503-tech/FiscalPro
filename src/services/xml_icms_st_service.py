"""Importação de NF-e XML e cálculo assistido de ICMS-ST/MG por item.

Sprint 14.7
- Lê NF-e 3.10/4.00 sem depender de namespace fixo.
- Aproveita o enquadramento oficial de ICMS-ST/MG já sincronizado.
- Calcula item a item usando a calculadora aprovada na Sprint 14.4.
- Mantém itens sem MVA ou com enquadramento duvidoso claramente sinalizados.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

from src.services.calculadora_icms_st_mg_service import CalculadoraICMSSTMGService
from src.services.icms_st_mg_service import (
    APLICABILIDADE_7318_CONSTRUCAO,
    APLICABILIDADE_7318_EXCLUSIVO_AUTOMOTIVO,
    APLICABILIDADE_7318_PENDENTE,
    ICMSSTMGService,
)


ORIGENS_IMPORTADAS = {"1", "2", "6", "7", "8"}


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _filho(no: Optional[ET.Element], nome: str) -> Optional[ET.Element]:
    if no is None:
        return None
    for item in list(no):
        if _local(item.tag) == nome:
            return item
    return None


def _descendente(no: Optional[ET.Element], nome: str) -> Optional[ET.Element]:
    if no is None:
        return None
    for item in no.iter():
        if _local(item.tag) == nome:
            return item
    return None


def _texto(no: Optional[ET.Element], nome: str, padrao: str = "") -> str:
    alvo = _filho(no, nome)
    return (alvo.text or "").strip() if alvo is not None else padrao


def _decimal(valor: Any, padrao: str = "0") -> Decimal:
    texto = str(valor if valor not in (None, "") else padrao).strip().replace(".", "").replace(",", ".")
    # XML sempre usa ponto decimal. A troca acima atende também entrada manual brasileira,
    # mas preserva valores XML com um único ponto através do caminho abaixo.
    original = str(valor if valor not in (None, "") else padrao).strip()
    if "." in original and "," not in original:
        texto = original
    try:
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return Decimal(padrao)


def _float(valor: Any) -> float:
    return float(_decimal(valor))


@dataclass
class ItemNFe:
    numero_item: int
    codigo: str
    descricao: str
    ncm: str
    cest_xml: str
    cfop: str
    quantidade: Decimal
    unidade: str
    valor_unitario: Decimal
    valor_produtos: Decimal
    desconto: Decimal
    frete: Decimal
    seguro: Decimal
    outros: Decimal
    ipi: Decimal
    icms_proprio: Decimal
    aliquota_icms_xml: Decimal
    origem_mercadoria: str
    cst_icms: str
    csosn: str
    base_st_xml: Decimal
    icms_st_xml: Decimal
    base_st_retida_xml: Decimal
    icms_st_retido_xml: Decimal
    fcp_st_xml: Decimal
    fcp_st_retido_xml: Decimal
    base_icms_proprio: Decimal = Decimal("0")

    def para_dict(self) -> Dict[str, Any]:
        dados = asdict(self)
        for chave, valor in list(dados.items()):
            if isinstance(valor, Decimal):
                dados[chave] = float(valor)
        return dados


@dataclass
class NotaFiscalXML:
    arquivo: str
    chave: str
    numero: str
    serie: str
    data_emissao: str
    emitente_nome: str
    emitente_cnpj: str
    destinatario_nome: str
    destinatario_documento: str
    uf_origem: str
    uf_destino: str
    regime_emitente: str
    total_base_st_xml: Decimal
    total_icms_st_xml: Decimal
    total_fcp_st_xml: Decimal
    itens: List[ItemNFe] = field(default_factory=list)

    def para_dict(self) -> Dict[str, Any]:
        dados = asdict(self)
        for chave, valor in list(dados.items()):
            if isinstance(valor, Decimal):
                dados[chave] = float(valor)
        dados["itens"] = [item.para_dict() for item in self.itens]
        return dados


class XMLICMSSTService:
    """Serviço principal do módulo XML → cálculo → planilha."""

    @classmethod
    def ler_xml(cls, caminho: str) -> NotaFiscalXML:
        arquivo = Path(caminho)
        if not arquivo.is_file():
            raise ValueError("Selecione um arquivo XML válido.")

        try:
            raiz = ET.parse(arquivo).getroot()
        except ET.ParseError as erro:
            raise ValueError(f"O XML não pôde ser lido: {erro}") from erro

        inf_nfe = _descendente(raiz, "infNFe")
        if inf_nfe is None:
            raise ValueError("O arquivo não contém uma NF-e reconhecida (infNFe não encontrado).")

        ide = _filho(inf_nfe, "ide")
        emit = _filho(inf_nfe, "emit")
        dest = _filho(inf_nfe, "dest")
        ender_emit = _filho(emit, "enderEmit")
        ender_dest = _filho(dest, "enderDest")
        total = _filho(inf_nfe, "total")
        icms_tot = _descendente(total, "ICMSTot")

        chave = str(inf_nfe.attrib.get("Id") or "")
        if chave.startswith("NFe"):
            chave = chave[3:]

        crt = _texto(emit, "CRT")
        regime = {
            "1": "SIMPLES NACIONAL",
            "2": "SIMPLES NACIONAL — EXCESSO SUBLIMITE",
            "3": "REGIME NORMAL",
            "4": "MEI",
        }.get(crt, "NÃO INFORMADO")

        itens: List[ItemNFe] = []
        for det in list(inf_nfe):
            if _local(det.tag) != "det":
                continue
            prod = _filho(det, "prod")
            imposto = _filho(det, "imposto")
            if prod is None:
                continue

            ipi_no = _descendente(_filho(imposto, "IPI"), "vIPI")
            valor_ipi = _decimal((ipi_no.text or "0") if ipi_no is not None else "0")

            icms_grupo = _filho(imposto, "ICMS")
            icms_tipo: Optional[ET.Element] = None
            if icms_grupo is not None:
                for filho in list(icms_grupo):
                    if _local(filho.tag).startswith("ICMS"):
                        icms_tipo = filho
                        break

            v_icms = _decimal(_texto(icms_tipo, "vICMS"))
            v_bc = _decimal(_texto(icms_tipo, "vBC"))
            p_icms = _decimal(_texto(icms_tipo, "pICMS"))
            origem = _texto(icms_tipo, "orig")
            cst = _texto(icms_tipo, "CST")
            csosn = _texto(icms_tipo, "CSOSN")
            v_bc_st = _decimal(_texto(icms_tipo, "vBCST"))
            v_icms_st = _decimal(_texto(icms_tipo, "vICMSST"))
            v_bc_st_ret = _decimal(_texto(icms_tipo, "vBCSTRet"))
            v_icms_st_ret = _decimal(_texto(icms_tipo, "vICMSSTRet"))
            v_fcp_st = _decimal(_texto(icms_tipo, "vFCPST"))
            v_fcp_st_ret = _decimal(_texto(icms_tipo, "vFCPSTRet"))

            try:
                numero_item = int(det.attrib.get("nItem") or (len(itens) + 1))
            except ValueError:
                numero_item = len(itens) + 1

            itens.append(
                ItemNFe(
                    numero_item=numero_item,
                    codigo=_texto(prod, "cProd"),
                    descricao=_texto(prod, "xProd"),
                    ncm="".join(c for c in _texto(prod, "NCM") if c.isdigit()),
                    cest_xml="".join(c for c in _texto(prod, "CEST") if c.isdigit()),
                    cfop=_texto(prod, "CFOP"),
                    quantidade=_decimal(_texto(prod, "qCom")),
                    unidade=_texto(prod, "uCom"),
                    valor_unitario=_decimal(_texto(prod, "vUnCom")),
                    valor_produtos=_decimal(_texto(prod, "vProd")),
                    desconto=_decimal(_texto(prod, "vDesc")),
                    frete=_decimal(_texto(prod, "vFrete")),
                    seguro=_decimal(_texto(prod, "vSeg")),
                    outros=_decimal(_texto(prod, "vOutro")),
                    ipi=valor_ipi,
                    icms_proprio=v_icms,
                    base_icms_proprio=v_bc,
                    aliquota_icms_xml=p_icms,
                    origem_mercadoria=origem,
                    cst_icms=cst,
                    csosn=csosn,
                    base_st_xml=v_bc_st,
                    icms_st_xml=v_icms_st,
                    base_st_retida_xml=v_bc_st_ret,
                    icms_st_retido_xml=v_icms_st_ret,
                    fcp_st_xml=v_fcp_st,
                    fcp_st_retido_xml=v_fcp_st_ret,
                )
            )

        if not itens:
            raise ValueError("A NF-e não possui itens de produto reconhecidos.")

        documento_dest = _texto(dest, "CNPJ") or _texto(dest, "CPF")
        return NotaFiscalXML(
            arquivo=str(arquivo.resolve()),
            chave=chave,
            numero=_texto(ide, "nNF"),
            serie=_texto(ide, "serie"),
            data_emissao=_texto(ide, "dhEmi") or _texto(ide, "dEmi"),
            emitente_nome=_texto(emit, "xNome"),
            emitente_cnpj=_texto(emit, "CNPJ"),
            destinatario_nome=_texto(dest, "xNome"),
            destinatario_documento=documento_dest,
            uf_origem=_texto(ender_emit, "UF").upper(),
            uf_destino=_texto(ender_dest, "UF").upper(),
            regime_emitente=regime,
            total_base_st_xml=_decimal(_texto(icms_tot, "vBCST")),
            total_icms_st_xml=_decimal(_texto(icms_tot, "vST")),
            total_fcp_st_xml=_decimal(_texto(icms_tot, "vFCPST")),
            itens=itens,
        )

    @staticmethod
    def aliquota_interestadual_sugerida(item: ItemNFe, uf_origem: str, uf_destino: str, aliquota_interna: Any) -> Decimal:
        if uf_origem and uf_destino and uf_origem == uf_destino:
            return _decimal(aliquota_interna)
        if item.origem_mercadoria in ORIGENS_IMPORTADAS:
            return Decimal("4.00")
        return Decimal("12.00")

    @staticmethod
    def _base_operacao_propria_estimada(item: ItemNFe) -> Decimal:
        """Base conservadora para a memória da operação própria quando o XML não traz vBC.

        A prioridade é sempre a base ``vBC`` informada na NF-e. Na ausência dela,
        estima-se a base a partir dos componentes do item apenas para a memória de
        cálculo do ICMS-ST. Essa estimativa não cria crédito fiscal escritural.
        """
        if item.base_icms_proprio > 0:
            return item.base_icms_proprio
        base = item.valor_produtos + item.frete + item.seguro + item.outros - item.desconto
        return max(Decimal("0"), base)

    @classmethod
    def _deducao_icms_operacao_propria(
        cls,
        item: ItemNFe,
        *,
        uf_origem: str,
        uf_destino: str,
        aliquota_interestadual: Decimal,
        remetente_simples: bool,
        habilitada: bool,
    ) -> tuple[Decimal, str, str]:
        """Define a dedução usada somente na memória do ICMS-ST.

        Regra MG (RICMS/MG/2023, Anexo VII, Parte 1, art. 22, § 1º): quando o
        remetente é ME/EPP do Simples Nacional, a parcela da operação própria a
        deduzir do ICMS-ST é o resultado da aplicação da alíquota interna ou
        interestadual, conforme a operação, sobre o valor da respectiva operação.
        Essa parcela integra apenas a memória do ICMS-ST e não cria crédito
        escritural para o destinatário.

        Para fornecedor fora do Simples, preserva-se o comportamento anterior:
        prioriza-se o vICMS do XML e, se ausente, a estimativa automática fica
        restrita às operações interestaduais/CST 00 ou 10 quando habilitada.
        O valor manual continua tendo prioridade e é tratado pelo chamador.
        """
        mesma_uf = bool(uf_origem and uf_destino and uf_origem == uf_destino)
        interestadual = bool(uf_origem and uf_destino and uf_origem != uf_destino)

        # No Simples Nacional a dedução do art. 22, § 1º não depende de vICMS
        # destacado no XML. O módulo calcula a parcela legal pela alíquota da
        # própria operação; o campo manual do item continua podendo sobrescrevê-la.
        if remetente_simples and (mesma_uf or interestadual):
            base = cls._base_operacao_propria_estimada(item)
            aliquota = aliquota_interestadual
            if base <= 0 or aliquota <= 0:
                return (
                    Decimal("0"),
                    "REVISAR — SIMPLES NACIONAL",
                    "Não foi possível formar base/alíquota segura para a dedução obrigatória do art. 22, § 1º do Anexo VII do RICMS/MG.",
                )
            deducao = (base * aliquota / Decimal("100")).quantize(Decimal("0.01"))
            origem_base = "vBC do XML" if item.base_icms_proprio > 0 else "base estimada da operação"
            tipo_aliquota = "interna" if mesma_uf else "interestadual"
            observacao = (
                f"Simples Nacional: dedução da operação própria calculada por {origem_base} x alíquota {tipo_aliquota} "
                f"({aliquota:.2f}%), conforme RICMS/MG/2023, Anexo VII, Parte 1, art. 22, § 1º. "
                "Usada somente na memória do ICMS-ST; não representa crédito fiscal escritural nem altera a NF-e."
            )
            return deducao, f"ALÍQUOTA {tipo_aliquota.upper()} — SIMPLES NACIONAL", observacao

        if item.icms_proprio > 0:
            return item.icms_proprio, "XML", "ICMS da operação própria lido do vICMS da NF-e."

        cst = str(item.cst_icms or "").zfill(2)[-2:] if str(item.cst_icms or "").strip() else ""
        if not habilitada or not interestadual or cst not in {"00", "10"}:
            return Decimal("0"), "NÃO INFORMADA", "O XML não trouxe vICMS; não houve dedução automática para este contexto/CST."

        base = cls._base_operacao_propria_estimada(item)
        if base <= 0 or aliquota_interestadual <= 0:
            return Decimal("0"), "REVISAR", "Não foi possível formar base/alíquota segura para a dedução da operação própria."
        deducao = (base * aliquota_interestadual / Decimal("100")).quantize(Decimal("0.01"))
        origem_base = "vBC do XML" if item.base_icms_proprio > 0 else "base estimada do item"
        observacao = (
            f"Dedução da operação própria calculada por {origem_base} x alíquota interestadual. "
            "Usada somente na memória do ICMS-ST; não representa crédito fiscal escritural nem altera a NF-e."
        )
        return deducao, "ALÍQUOTA INTERESTADUAL", observacao

    TOLERANCIA_CONFERENCIA = Decimal("0.05")

    @classmethod
    def conferir_icms_st(
        cls,
        item: ItemNFe,
        resultado_calculo: Dict[str, Any],
        tolerancia: Any = None,
    ) -> Dict[str, Any]:
        """Compara o ICMS-ST do XML com o cálculo do FiscalPro.

        A diferença é apresentada como ``calculado - XML``: valor positivo
        indica possível falta de destaque; valor negativo indica que o XML
        trouxe valor superior ao cálculo assistido.
        """
        limite = _decimal(
            cls.TOLERANCIA_CONFERENCIA if tolerancia in (None, "") else tolerancia
        )
        if limite < 0:
            limite = abs(limite)

        informado = item.icms_st_xml
        retido_anterior = item.icms_st_retido_xml
        calculado = _decimal(resultado_calculo.get("icms_st"))
        diferenca = (calculado - informado).quantize(Decimal("0.01"))
        diferenca_abs = abs(diferenca)
        calculo_disponivel = bool(resultado_calculo.get("calculado"))
        status_calculo = str(resultado_calculo.get("status") or "").upper()

        observacoes: List[str] = []
        aplicabilidade_7318 = str(resultado_calculo.get("aplicabilidade_7318") or "")
        if resultado_calculo.get("nao_aplicavel"):
            conferencia = "NÃO APLICÁVEL — USO EXCLUSIVO AUTOMOTIVO"
            if informado > limite:
                observacoes.append(
                    "O item foi classificado como de uso exclusivamente automotivo, mas o XML contém ICMS-ST. "
                    "Revise a classificação e o destaque do fornecedor."
                )
            else:
                observacoes.append(
                    "O ICMS-ST do segmento 10 não foi calculado porque o item foi informado como de uso "
                    "exclusivamente automotivo."
                )
        elif aplicabilidade_7318 == APLICABILIDADE_7318_PENDENTE:
            conferencia = "REVISAR USO DO NCM 7318"
            observacoes.append(
                "Informe se o produto é passível de uso como material de construção/congênere ou se possui "
                "uso exclusivamente automotivo."
            )
        elif not calculo_disponivel:
            conferencia = "REVISAR NCM / CEST / MVA"
            observacoes.append("O FiscalPro ainda não possui cálculo suficiente para comparar o ICMS-ST.")
        elif informado <= limite and retido_anterior > limite:
            conferencia = "ST RETIDO ANTERIORMENTE — REVISAR"
            observacoes.append(
                "O XML não traz vICMSST da operação, mas informa vICMSSTRet. "
                "Esse valor representa retenção anterior e não foi tratado como ST destacado nesta operação."
            )
        elif diferenca_abs <= limite:
            conferencia = "CORRETO"
            observacoes.append(f"Diferença dentro da tolerância de R$ {float(limite):.2f}.")
        elif informado <= limite and calculado > limite:
            conferencia = "ST NÃO DESTACADO"
            observacoes.append("O XML não informou ICMS-ST da operação, mas o cálculo assistido encontrou valor devido.")
        elif diferenca > limite:
            conferencia = "VALOR MENOR QUE O CALCULADO"
            observacoes.append("O ICMS-ST informado no XML é inferior ao cálculo do FiscalPro.")
        else:
            conferencia = "VALOR MAIOR QUE O CALCULADO"
            observacoes.append("O ICMS-ST informado no XML é superior ao cálculo do FiscalPro.")

        if conferencia not in {
            "NÃO APLICÁVEL — USO EXCLUSIVO AUTOMOTIVO",
            "REVISAR USO DO NCM 7318",
        } and (
            "MVA MANUAL" in status_calculo
            or not (resultado_calculo.get("st_oficial") or {}).get("encontrado")
        ):
            conferencia = "REVISAR NCM / CEST / MVA"
            observacoes.append("O enquadramento ou a MVA não foi confirmado automaticamente na base oficial sincronizada.")
        elif "REVISAR" in status_calculo and conferencia == "CORRETO":
            observacoes.append("Os valores coincidem, mas o enquadramento tributário ainda exige conferência.")

        return {
            "base_st_xml": float(item.base_st_xml),
            "icms_st_xml": float(informado),
            "base_st_retida_xml": float(item.base_st_retida_xml),
            "icms_st_retido_xml": float(retido_anterior),
            "fcp_st_xml": float(item.fcp_st_xml),
            "fcp_st_retido_xml": float(item.fcp_st_retido_xml),
            "diferenca_st": float(diferenca),
            "diferenca_st_absoluta": float(diferenca_abs),
            "tolerancia_conferencia": float(limite),
            "conferencia_status": conferencia,
            "conferencia_ok": conferencia == "CORRETO",
            "conferencia_observacao": " ".join(observacoes),
        }

    @classmethod
    def calcular_item(
        cls,
        item: ItemNFe,
        *,
        uf_origem: str,
        uf_destino: str,
        aliquota_interna: Any,
        aliquota_interestadual: Optional[Any] = None,
        aliquota_fcp: Any = 0,
        remetente_simples: bool = False,
        aplicar_mva_ajustada: bool = True,
        deduzir_icms_inter_sem_destaque: bool = True,
        mva_manual: Optional[Any] = None,
        icms_proprio_manual: Optional[Any] = None,
        aplicabilidade_7318: str = "",
        finalidade_automotiva: str = "",
        tolerancia_conferencia: Any = None,
    ) -> Dict[str, Any]:
        finalidade_inferida = ICMSSTMGService.inferir_finalidade_automotiva(
            item.descricao, item.cest_xml
        )
        finalidade_usada = finalidade_automotiva or finalidade_inferida
        contexto = {
            "uf_origem": uf_origem,
            "uf_destino": uf_destino,
            "aplicabilidade_7318": aplicabilidade_7318,
            "finalidade_automotiva": finalidade_usada,
        }
        try:
            st = ICMSSTMGService.analisar(item.ncm, contexto=contexto, descricao=item.descricao)
        except ValueError as erro:
            st = {
                "encontrado": False,
                "confirmado": False,
                "exige_revisao": True,
                "status": "NCM INVÁLIDO",
                "observacao": str(erro),
                "mva_original": None,
                "cest": item.cest_xml,
            }

        mva = _decimal(mva_manual) if mva_manual not in (None, "") else (
            _decimal(st.get("mva_original")) if st.get("mva_original") is not None else None
        )
        aliq_inter = _decimal(aliquota_interestadual) if aliquota_interestadual not in (None, "") else cls.aliquota_interestadual_sugerida(
            item, uf_origem, uf_destino, aliquota_interna
        )
        if icms_proprio_manual not in (None, ""):
            icms_proprio = _decimal(icms_proprio_manual)
            origem_deducao = "AJUSTE MANUAL"
            observacao_deducao = "Dedução da operação própria informada manualmente para este item."
        else:
            icms_proprio, origem_deducao, observacao_deducao = cls._deducao_icms_operacao_propria(
                item,
                uf_origem=uf_origem,
                uf_destino=uf_destino,
                aliquota_interestadual=aliq_inter,
                remetente_simples=remetente_simples,
                habilitada=deduzir_icms_inter_sem_destaque,
            )
        interestadual = bool(uf_origem and uf_destino and uf_origem != uf_destino)

        base: Dict[str, Any] = {
            "item": item.para_dict(),
            "st_oficial": st,
            "cest": st.get("cest") or item.cest_xml,
            "mva_original": float(mva) if mva is not None else None,
            "aliquota_interestadual": float(aliq_inter),
            "aliquota_interna": float(_decimal(aliquota_interna)),
            "aliquota_fcp": float(_decimal(aliquota_fcp)),
            "icms_proprio": float(icms_proprio),
            "icms_proprio_deduzir": float(icms_proprio),
            "deducao_icms_origem": origem_deducao,
            "deducao_icms_observacao": observacao_deducao,
            "base_icms_proprio_xml": float(item.base_icms_proprio),
            "valor_total_com_ipi": float(item.valor_produtos + item.ipi),
            "base_st_xml": float(item.base_st_xml),
            "icms_st_xml": float(item.icms_st_xml),
            "base_st_retida_xml": float(item.base_st_retida_xml),
            "icms_st_retido_xml": float(item.icms_st_retido_xml),
            "fcp_st_xml": float(item.fcp_st_xml),
            "fcp_st_retido_xml": float(item.fcp_st_retido_xml),
            "status": "",
            "observacao": str(st.get("observacao") or ""),
            "aplicabilidade_7318": str(st.get("aplicabilidade_segmento") or ""),
            "finalidade_automotiva": str(st.get("finalidade_automotiva") or ""),
            "finalidade_automotiva_origem": (
                "AJUSTE DO USUÁRIO" if finalidade_automotiva else
                "DESCRIÇÃO/CEST DO XML" if finalidade_inferida else
                "NÃO INFORMADA"
            ),
            "nao_aplicavel": bool(st.get("nao_aplicavel")),
            "calculado": False,
        }

        if st.get("nao_aplicavel"):
            base["status"] = "NÃO CALCULADO — USO EXCLUSIVAMENTE AUTOMOTIVO"
            base.update(cls.conferir_icms_st(item, base, tolerancia_conferencia))
            return base

        if str(st.get("aplicabilidade_segmento") or "") == APLICABILIDADE_7318_PENDENTE:
            base["status"] = "REVISAR USO DO NCM 7318"
            base.update(cls.conferir_icms_st(item, base, tolerancia_conferencia))
            return base

        if mva is None:
            base["status"] = "PREENCHER MVA"
            base["observacao"] = (
                (base["observacao"] + " ") if base["observacao"] else ""
            ) + "A MVA não foi encontrada automaticamente. Informe a MVA do item para calcular."
            base.update(cls.conferir_icms_st(item, base, tolerancia_conferencia))
            return base

        try:
            calculo = CalculadoraICMSSTMGService.calcular(
                valor_mercadoria=item.valor_produtos,
                frete=item.frete,
                seguro=item.seguro,
                ipi=item.ipi,
                outros_encargos=item.outros,
                mva_original=mva,
                aliquota_interestadual=aliq_inter,
                aliquota_interna=aliquota_interna,
                icms_proprio_deduzir=icms_proprio,
                aliquota_fcp_st=aliquota_fcp,
                operacao_interestadual=interestadual,
                aplicar_mva_ajustada=aplicar_mva_ajustada,
                remetente_simples=remetente_simples,
            )
        except ValueError as erro:
            base["status"] = "ERRO NO CÁLCULO"
            base["observacao"] = str(erro)
            base.update(cls.conferir_icms_st(item, base, tolerancia_conferencia))
            return base

        base.update(calculo)
        base["deducao_icms_origem"] = origem_deducao
        base["deducao_icms_observacao"] = observacao_deducao
        if observacao_deducao:
            obs = list(base.get("observacoes") or [])
            obs.insert(0, observacao_deducao)
            base["observacoes"] = obs
        base["calculado"] = True
        responsabilidade = str(st.get("responsabilidade") or "").strip().upper()
        if responsabilidade.startswith("DESTINATÁRIO MINEIRO"):
            if st.get("exige_revisao"):
                base["status"] = "CALCULADO — DESTINATÁRIO MG; REVISAR DETALHES"
            else:
                base["status"] = "CALCULADO — ST DEVIDA PELO DESTINATÁRIO MG"
        elif st.get("confirmado") and not st.get("exige_revisao"):
            base["status"] = "CALCULADO — ST CONFIRMADA"
        elif st.get("encontrado"):
            base["status"] = "CALCULADO — REVISAR ENQUADRAMENTO"
        else:
            base["status"] = "CALCULADO COM MVA MANUAL — REVISAR"
        base.update(cls.conferir_icms_st(item, base, tolerancia_conferencia))
        return base

    @classmethod
    def calcular_nota(
        cls,
        nota: NotaFiscalXML,
        *,
        uf_origem: Optional[str] = None,
        uf_destino: Optional[str] = None,
        aliquota_interna: Any = 18,
        aliquota_interestadual: Optional[Any] = None,
        aliquota_fcp: Any = 0,
        remetente_simples: bool = False,
        aplicar_mva_ajustada: bool = True,
        deduzir_icms_inter_sem_destaque: bool = True,
        ajustes: Optional[Dict[int, Dict[str, Any]]] = None,
        tolerancia_conferencia: Any = None,
    ) -> Dict[str, Any]:
        origem = str(uf_origem or nota.uf_origem or "").upper()
        destino = str(uf_destino or nota.uf_destino or "MG").upper()
        ajustes = ajustes or {}
        resultados = []

        for item in nota.itens:
            ajuste = ajustes.get(item.numero_item, {})
            resultados.append(
                cls.calcular_item(
                    item,
                    uf_origem=origem,
                    uf_destino=destino,
                    aliquota_interna=ajuste.get("aliquota_interna", aliquota_interna),
                    aliquota_interestadual=ajuste.get("aliquota_interestadual", aliquota_interestadual),
                    aliquota_fcp=ajuste.get("aliquota_fcp", aliquota_fcp),
                    remetente_simples=remetente_simples,
                    aplicar_mva_ajustada=aplicar_mva_ajustada,
                    deduzir_icms_inter_sem_destaque=deduzir_icms_inter_sem_destaque,
                    mva_manual=ajuste.get("mva_original"),
                    icms_proprio_manual=ajuste.get("icms_proprio"),
                    aplicabilidade_7318=ajuste.get("aplicabilidade_7318", ""),
                    finalidade_automotiva=ajuste.get("finalidade_automotiva", ""),
                    tolerancia_conferencia=tolerancia_conferencia,
                )
            )

        total_produtos = sum((_decimal(r["item"].get("valor_produtos")) for r in resultados), Decimal("0"))
        total_ipi = sum((_decimal(r["item"].get("ipi")) for r in resultados), Decimal("0"))
        total_base = sum((_decimal(r.get("base_calculo_st")) for r in resultados if r.get("calculado")), Decimal("0"))
        total_st = sum((_decimal(r.get("icms_st")) for r in resultados if r.get("calculado")), Decimal("0"))
        total_fcp = sum((_decimal(r.get("fcp_st")) for r in resultados if r.get("calculado")), Decimal("0"))
        total_st_xml_itens = sum((_decimal(r.get("icms_st_xml")) for r in resultados), Decimal("0"))
        total_st_xml_nota = nota.total_icms_st_xml
        total_st_xml = total_st_xml_nota if total_st_xml_nota > 0 else total_st_xml_itens
        diferenca_total = (total_st - total_st_xml).quantize(Decimal("0.01"))
        divergencia_xml = (total_st_xml_nota - total_st_xml_itens).quantize(Decimal("0.01"))

        contagens = {
            "CORRETO": 0,
            "ST NÃO DESTACADO": 0,
            "VALOR MENOR QUE O CALCULADO": 0,
            "VALOR MAIOR QUE O CALCULADO": 0,
            "REVISAR": 0,
        }
        for item_resultado in resultados:
            conferencia = str(item_resultado.get("conferencia_status") or "")
            if conferencia in contagens:
                contagens[conferencia] += 1
            else:
                contagens["REVISAR"] += 1

        pendentes = sum(
            1 for r in resultados
            if not r.get("calculado") or "REVISAR" in str(r.get("status"))
        )
        deducoes_automaticas = sum(
            1 for r in resultados
            if str(r.get("deducao_icms_origem") or "").startswith("ALÍQUOTA ")
        )
        deducoes_interestadual = sum(
            1 for r in resultados
            if str(r.get("deducao_icms_origem") or "").startswith("ALÍQUOTA INTERESTADUAL")
        )

        return {
            "nota": nota.para_dict(),
            "uf_origem": origem,
            "uf_destino": destino,
            "itens": resultados,
            "resumo": {
                "quantidade_itens": len(resultados),
                "itens_pendentes": pendentes,
                "itens_corretos": contagens["CORRETO"],
                "itens_st_nao_destacado": contagens["ST NÃO DESTACADO"],
                "itens_valor_menor": contagens["VALOR MENOR QUE O CALCULADO"],
                "itens_valor_maior": contagens["VALOR MAIOR QUE O CALCULADO"],
                "itens_revisar": contagens["REVISAR"],
                "itens_deducao_interestadual": deducoes_interestadual,
                "itens_deducao_automatica": deducoes_automaticas,
                "total_produtos": float(total_produtos),
                "total_ipi": float(total_ipi),
                "total_produtos_com_ipi": float(total_produtos + total_ipi),
                "total_base_st": float(total_base),
                "total_icms_st": float(total_st),
                "total_icms_st_xml": float(total_st_xml),
                "total_icms_st_xml_itens": float(total_st_xml_itens),
                "total_icms_st_xml_nota": float(total_st_xml_nota),
                "diferenca_total_st": float(diferenca_total),
                "divergencia_total_xml_itens": float(divergencia_xml),
                "total_fcp_st": float(total_fcp),
                "total_st_fcp": float(total_st + total_fcp),
                "tolerancia_conferencia": float(_decimal(
                    cls.TOLERANCIA_CONFERENCIA if tolerancia_conferencia in (None, "") else tolerancia_conferencia
                )),
            },
        }
