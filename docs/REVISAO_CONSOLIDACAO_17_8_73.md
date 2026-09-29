# FiscalPro 17.8.73 — Revisão de Consolidação

## Problema encontrado

O projeto recebido continha duas linhas diferentes usando os mesmos números 17.8.71 e 17.8.72. O `src/` ativo estava em 17.8.70, enquanto README/testes já apontavam para 17.8.72. A correção visual 17.8.71 e a finalidade automotiva do XML 17.8.72 existiam em pacotes paralelos, mas não estavam integralmente incorporadas à fonte executada.

## Estratégia aplicada

1. Preservação integral dos bancos e backups do projeto recebido.
2. `src/` mantido como fonte única operacional.
3. Motor condicional da base ativa preservado.
4. Layout compacto 17.8.71 incorporado.
5. Regra do Simples Nacional 17.8.66 preservada no XML.
6. Finalidade automotiva do XML incorporada por cherry-pick, sem copiar a regressão do hotfix paralelo.
7. AC/AM recuperados do ramo `work_17_8_70`.
8. AP/RO reintegrados com escopo conservador e testes de regressão.
9. Pacotes conflitantes retirados da raiz operacional e seus LEIA-ME arquivados em `docs/historico_conflitos_17_8_71_72/`.

## Regra de manutenção a partir desta versão

Nunca reutilizar número de versão. Toda nova alteração deve partir desta pasta 17.8.73 e atualizar `src/core/app_info.py`, README, CHANGELOG e testes na mesma entrega.
