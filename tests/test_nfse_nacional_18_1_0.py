import base64
import gzip
from pathlib import Path

from src.nfse.parser import analisar_nfse, decodificar_xml
from src.nfse.repositorio import RepositorioNFSe
from src.nfse.exportador import exportar_excel

XML = '''<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
  <infNFSe Id="NFS123">
    <nNFSe>456</nNFSe><dhEmi>2026-09-20T10:20:00-03:00</dhEmi>
    <emit><CNPJ>12345678000199</CNPJ><xNome>Prestador Teste</xNome></emit>
    <DPS><infDPS><dCompet>2026-09-20</dCompet>
      <prest><CNPJ>12345678000199</CNPJ><xNome>Prestador Teste</xNome></prest>
      <toma><CNPJ>99887766000155</CNPJ><xNome>Cliente Teste</xNome></toma>
      <valores><vServPrest><vServ>150.75</vServ></vServPrest></valores>
    </infDPS></DPS>
  </infNFSe>
</NFSe>'''


def test_decodifica_gzip_base64():
    payload = base64.b64encode(gzip.compress(XML.encode())).decode()
    assert decodificar_xml(payload).startswith('<?xml')


def test_classifica_emitida_e_extrai_valores():
    dados = analisar_nfse(XML, '12345678000199')
    assert dados['direcao'] == 'EMITIDA'
    assert dados['numero_nfse'] == '456'
    assert dados['tomador_nome'] == 'Cliente Teste'
    assert dados['valor_servico'] == 150.75


def test_repositorio_e_excel(tmp_path: Path):
    repo = RepositorioNFSe(tmp_path / 'nfse.db')
    eid = repo.salvar_empresa('Empresa Teste', '12345678000199', 'C:/cert.pfx')
    item = {'NSU': 1, 'ChaveAcesso': 'ABC', 'TipoDocumento': 'NFSE'}
    repo.salvar_documento(eid, item, analisar_nfse(XML, '12345678000199'), XML)
    rows = repo.listar_documentos([eid], direcao='EMITIDA')
    assert len(rows) == 1
    destino = exportar_excel(rows, tmp_path / 'relatorio.xlsx')
    assert destino.exists() and destino.stat().st_size > 0
