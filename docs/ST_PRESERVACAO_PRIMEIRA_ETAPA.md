# ST: primeira etapa de preservacao e desempenho

## Limite desta proposta

Branch de teste: `melhoria/st-preservacao-e-desempenho`.
Ponto de partida: `27f67c15f3428be8012b92c74c253fb761cb3cf9` (main).
Nao integrar automaticamente nem gerar instalador para uso real nesta etapa.

Unica alteracao em codigo existente: a comparacao matematica entre dois textos
no validador NCM passa a usar uma funcao pura com cache limitado. O algoritmo,
a ordem dos textos, as pontuacoes, candidatos, limites de confianca e mensagens
continuam iguais. O cache nao contem decisoes fiscais, NCM, CEST ou MVA; nao
precisa reutilizar resultados de operacoes diferentes. Mudar qualquer texto
muda a chave. Textos longos nao sao retidos e o numero de entradas e limitado.

Nenhuma alteracao nas regras de ICMS-ST, bancos, cadastros, arquivos de dados,
XMLs, calculadoras, Contas a Pagar, Agenda, interface ou instalador. Nao houve
mudanca em main. O catalogo usado nos testes e o pacote ja versionado; estes
testes nao representam uma nova validacao juridica da base.

## Evidencia local (Python 3.13.5, Linux, diretorios descartaveis)

- Sintaxe: `python -m compileall -q src tests main.py`, aprovada.
- Antes: 594 testes passaram, 162 falharam (756 testes existentes).
- Depois: 632 passaram, as MESMAS 162 falharam; 38 testes novos passaram.
- Comparacao por identificador: zero testes existentes removidos ou com status
  diferente. Nao foram apagadas, ignoradas ou reclassificadas falhas antigas.
- Grupo focado: 55 testes aprovados, incluindo os 38 novos.

As falhas ja ocorreram no commit de referencia, inclusive no GitHub Actions
run `39030366500`. Ha falhas ligadas a tabelas/sementes ausentes no ambiente
limpo, datas e expectativas antigas. Ainda precisam ser triadas; nao demonstram
por si so que a instalacao do usuario apresenta os mesmos problemas.
A suite completa permanece vermelha: NAO considerar a proposta liberada.

## Medicao delimitada

`python -m tests.benchmark_similaridade_textual`

Foram 280 consultas por rodada, com 14 descricoes repetidas 20 vezes, em sete
rodadas por modo, alternando a ordem antes/depois, limpando o cache a cada rodada
e usando os 10.520 registros do catalogo versionado. Todas as listas de
candidatos e pontuacoes comparadas foram identicas.

Medianas locais: antes 1,0198 s; depois 0,3379 s (66,86% menos tempo).
Isso mede SOMENTE busca/pontuacao NCM em memoria com repeticoes. Nao mede a
abertura do programa, consultas ao banco, a auditoria inteira nem desempenho
no Windows do usuario. Nao e garantia de ganho igual em outros lotes.

## Antes de publicar

1. Triar as falhas preexistentes sem modificar regras corretas para satisfazer
   testes obsoletos; preparar dados de teste reproduziveis.
2. Validar Windows, abertura do programa e os casos aprovados pelo usuario em
   copia de dados autorizada, sem substituir sua instalacao atual.
3. Mostrar resultados e alteracoes ao usuario antes de integrar em main.
