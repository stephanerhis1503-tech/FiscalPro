"""
=========================================
FiscalPro
Versão: 0.6.0
Sprint 6

Responsável pela montagem do relatório
de auditoria.
=========================================
"""


class FormatadorAuditoria:

    @staticmethod
    def montar_resumo(empresa, periodo, leitor, resultado):

        registros = resultado.get("registros", {})
        auditoria = resultado.get("auditoria_0200", {})
        auditoria_c170 = resultado.get("auditoria_c170", {})

        produtos = auditoria.get("produtos", 0)
        sem_descricao = auditoria.get("sem_descricao", [])
        sem_unidade = auditoria.get("sem_unidade", [])
        sem_ncm = auditoria.get("sem_ncm", [])
        ncm_invalido = auditoria.get("ncm_invalido", [])

        relatorio = []

        relatorio.append("=" * 65)
        relatorio.append("                     FISCALPRO")
        relatorio.append("             Assistente Fiscal Inteligente")
        relatorio.append("=" * 65)
        relatorio.append("")

        relatorio.append("EMPRESA")
        relatorio.append("-" * 65)
        relatorio.append(empresa)
        relatorio.append("")

        relatorio.append("PERÍODO")
        relatorio.append("-" * 65)
        relatorio.append(periodo)
        relatorio.append("")

        relatorio.append("ESTATÍSTICAS GERAIS")
        relatorio.append("-" * 65)

        relatorio.append(f"Total de linhas.............: {leitor.total_linhas():,}")
        relatorio.append(f"Participantes (0150)........: {registros.get('0150', 0):,}")
        relatorio.append(f"Produtos (0200).............: {produtos:,}")
        relatorio.append(f"NF-e (C100).................: {registros.get('C100', 0):,}")
        relatorio.append(f"Itens NF-e (C170)...........: {registros.get('C170', 0):,}")
        relatorio.append(f"Totalizadores (C190)........: {registros.get('C190', 0):,}")
        relatorio.append(f"CT-e (D100).................: {registros.get('D100', 0):,}")

        relatorio.append("")
        relatorio.append("AUDITORIA DO REGISTRO 0200")
        relatorio.append("-" * 65)

        relatorio.append(f"Produtos cadastrados........: {produtos:,}")
        relatorio.append(f"Sem descrição...............: {len(sem_descricao)}")
        relatorio.append(f"Sem unidade.................: {len(sem_unidade)}")
        relatorio.append(f"Sem NCM.....................: {len(sem_ncm)}")
        relatorio.append(f"NCM inválido.................: {len(ncm_invalido)}")

        relatorio.append("")
        relatorio.append("AUDITORIA DO REGISTRO C170")
        relatorio.append("-" * 65)

        relatorio.append(
            f"Itens analisados............: {auditoria_c170.get('itens', 0)}"
        )

        erros = auditoria_c170.get("erros", [])

        relatorio.append(
            f"Inconsistências encontradas.: {len(erros)}"
        )

        if erros:

            relatorio.append("")
            relatorio.append("Primeiras inconsistências:")

            for erro in erros[:10]:

                relatorio.append(
                    f"Linha {erro['linha']} | Produto {erro['produto']} | {erro['erro']}"
                )

        relatorio.append("")
        relatorio.append("=" * 65)
        relatorio.append("Fim da Auditoria")
        relatorio.append("=" * 65)

        return "\n".join(relatorio)