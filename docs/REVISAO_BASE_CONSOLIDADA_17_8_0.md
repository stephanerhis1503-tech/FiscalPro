# Revisão técnica — FiscalPro 17.8.0

## Ajustes realizados

- Aplicado o Hotfix 17.7.7 sobre a cópia integral enviada para revisão.
- Unificada a versão Python: `src/core/config.py` agora reutiliza `src/core/app_info.py`.
- Atualizados `app_info.py`, Inno Setup, `version_info.txt` e script de build para 17.8.0.
- Corrigido `INSTALAR_ROBO_EMAIL.bat` com a criação de `requirements_robo_email.txt`.
- Criados `requirements.txt` e `requirements-dev.txt`.
- Atualizados os testes do Controle de Entregas para a regra vigente de prazo no mês seguinte, mantendo teste explícito para prazo no mesmo mês.
- Removidos da base de código caches, ambiente virtual, builds, executáveis antigos, dados de execução e credenciais.
- Removidos stubs vazios sem importação (`src/corretores`) e scripts manuais antigos sem referência.
- Removido `src/banco/fiscalpro.db`, que era um banco residual não utilizado; o acesso atual usa `src.core.caminhos.BANCO_FISCAL`.
- Documentação histórica avulsa compactada em um único arquivo.

## Dados deliberadamente não incluídos

A base consolidada não contém os bancos de trabalho nem credenciais pessoais. Isso evita sobrescrever dados mais novos ao instalar uma atualização e impede que tokens/segredos OAuth sejam distribuídos junto com o código.

## Critério de remoção

Só foram removidos automaticamente itens gerados, caches, arquivos de execução, dados pessoais e arquivos sem referência confirmada. Módulos funcionais, bases-modelo, bases oficiais, recursos visuais, testes automatizados e fallback PDF foram mantidos.

## Verificações executadas após a limpeza

- `python -m compileall -q main.py src tests`: aprovado.
- suíte automatizada: **120 testes aprovados / 0 falhas**.
- imports das telas/motores principais: aprovado.
- round-trip real com `SPED CONT 07-2026(2).txt`: **0 alterações**, **0 novos erros**, saída com o mesmo tamanho e o mesmo SHA-256 do TXT original.
- planilha real `SPED CONT 07-2026_ORGANIZADO3.xlsx`: validação aprovada, **3.496 alterações**, **0 novos erros**; o TXT manteve a ordem `M100 -> M105` e `M500 -> M505`.

## Observação sobre representação decimal

Em células realmente alteradas no Excel, a versão 17.7.7/17.8.0 normaliza campos técnicos de alíquota para a precisão definida pelo leiaute (por exemplo, zero percentual pode sair como `0,0000`). Em células não alteradas, o texto original do SPED é preservado byte a byte no round-trip.

## Limpeza da instalação-fonte existente

Foi incluído `LIMPAR_ARTEFATOS_ANTIGOS.bat`. Ele pode ser executado depois de extrair a base por cima da pasta atual. O script remove apenas caches, builds e arquivos técnicos antigos; não remove `fiscalpro.db`, `dados`, `backups` ou `logs`.
