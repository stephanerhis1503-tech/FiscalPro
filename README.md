## 17.8.127 — Motor ST/MG contextual: NCM + descrição + segmento + finalidade
- corrige o conflito do NCM 7616.99.00 para TAMPA VÁLVULA BUTYL ALUM, sem aplicar automaticamente o CEST 10.073.00 de construção quando a descrição não corresponde;
- em conflito de segmento com finalidade automotiva comprovada, avalia o residual 01.999.00 de autopeças;
- CEST/MVA condicionais viram somente sugestão e não geram cálculo automático de ICMS-ST;
- impede falso “ST NÃO DESTACADO” em item cujo enquadramento ainda precisa de revisão;
- o motor integrado de MG não transforma mais CEST + MVA candidatos em ST confirmada;
- preserva CEST específicos com novas normalizações de FIACAO/FIOS e INTER;
- inclui testes de regressão 17.8.127.

## 17.8.126 — Filtro de ar: enquadramento específico de ST/MG

- Corrige falso CEST 21.014.00/MVA 40% para filtro completo de ar de motor quando o cadastro/XML veio genericamente como NCM 8421.99.99.
- Descrição compatível passa a direcionar a análise de ST para 8421.31.00, CEST 01.041.00, MVA original 71,78%.
- A MVA ajustada continua sendo calculada pela fórmula legal conforme alíquota interestadual e interna (ex.: 4%→18% = 101,11%; 12%→18% = 84,35%).
- O NCM original do documento não é sobrescrito; a divergência é mostrada para revisão cadastral.

## 17.8.125 — Restauração portátil entre PCs

- Corrige `[WinError 5] Acesso negado: C:\\Users\\<usuário antigo>` ao restaurar backup em outro computador.
- Remapeia referências do perfil Windows antigo para o usuário atual.
- Migra caminhos do robô de e-mail, pasta de scans e anexos do Contas a Pagar após a restauração.
- O backup de segurança pré-restauração deixa de consultar pasta externa quando `incluir_documentos=False`.

# FiscalPro 17.8.124

No fluxo Excel → TXT, o C175 agora sincroniza `VL_BC_PIS` e `VL_BC_COFINS` quando uma contribuição já contém a base corrigida (por exemplo, após exclusão do ICMS) e a outra ainda está na base bruta. O valor do tributo espelhado é recalculado automaticamente, com proteção para edições manuais e modalidades por quantidade.

# FiscalPro 17.8.95

A rotina de Estorno ICMS agora exige crédito real no C170 antes de gerar C197: BC, alíquota e VL_ICMS devem ser positivos. Entradas de uso/consumo (1407/1556/2407/2556) são bloqueadas para geração automática. Ajustes C197 existentes sem crédito correspondente são mostrados em **REVISAR** na Conferência por NF.

## Novidade 17.8.94 — Arredondamento acumulado no estorno ICMS

A conferência do **Estorno ICMS** passa a separar uma divergência fiscal real de um acúmulo matemático de arredondamento. Quando a soma dos `C170` difere do ICMS do `C100` por mais de R$ 0,01, o FiscalPro só reconcilia automaticamente se conseguir provar duas condições: cada item precisa coincidir com `BC_ICMS × ALIQ_ICMS` arredondado a centavos, e o total do `C100` precisa coincidir exatamente com a soma teórica calculada sem arredondar cada item individualmente.

Quando essas condições são atendidas, a diferença é distribuída em passos de **R$ 0,01** entre os itens cujos resíduos justificam o ajuste. Assim, uma diferença mensal como **R$ 1,88** pode ser corrigida sem simplesmente subtrair R$ 1,88 do total e sem esconder uma NF incorreta. Se a prova matemática não fechar, a nota permanece em **REVISAR** e nenhum C197 é gerado automaticamente.

Na janela **🔎 Conferir por NF**, passam a aparecer também **ICMS teórico**, **teto de arredondamento**, **impacto bruto** e **ajuste aplicado**. A memória CSV mantém o valor original do C170, o ajuste e o valor efetivamente estornado em colunas separadas.

## Novidade 17.8.93 — C190 detectado mesmo quando o Excel mostra 0 alterações

O FiscalPro passa a auditar a coerência interna entre `C170` e `C190` durante a validação do Excel, mesmo quando a planilha foi gerada a partir de um TXT que já continha o `C170` corrigido e o `C190` antigo. Nesse caso, a comparação Excel x origem pode mostrar **0 campos alterados**, mas o sistema agora identifica a divergência de `CST_ICMS + CFOP + ALIQ_ICMS` e reconstrói o analítico.

A reconstrução automática só ocorre quando os totais comprováveis de `VL_BC_ICMS`, `VL_ICMS`, `VL_BC_ICMS_ST`, `VL_ICMS_ST` e `VL_IPI` fecham entre C170 e C190. Assim, o FiscalPro pode alterar/fundir o C190 sem apagar grupos que não estejam representados nos itens. Se os totais não fecharem, a nota fica em revisão manual. Quando o novo C190 possui um único grupo, `VL_RED_BC` existente é preservado. A tela de validação passa a mostrar explicitamente a quantidade de **Ajustes automáticos C190** e de documentos reconstruídos.

Caso real validado em `ArquivoSPEDFiscal 3_ORGANIZADO.xlsx`: **30 documentos** foram identificados e reagrupados com segurança; **2 notas** permaneceram em revisão porque os totais C170 x C190 não fechavam. Pré-PVA local: **0 erro novo**.

## Novidade 17.8.92 — C170 → C190 no Excel → TXT

O `C190` é o resumo analítico do ICMS por combinação de `CST_ICMS + CFOP + ALIQ_ICMS`. A partir da 17.8.92, quando um desses campos é alterado no `C170`, o FiscalPro não deixa mais o resumo antigo no documento: ele reconstrói os `C190` do `C100` afetado, preservando o valor total da operação e recompensando os campos tributários pelos itens.

A automação é conservadora. Se o próprio `C190` tiver sido editado manualmente, ou se houver redução de base/observações que não possam ser vinculadas aos itens com segurança, o sistema preserva a escrituração e sinaliza revisão em vez de inventar um rateio. O resultado aparece na **Conferência Excel** antes da geração do TXT.

## Novidade 17.8.91 — CST do C170 → C100 no Excel → TXT

Ao reconstruir o SPED a partir da planilha, o FiscalPro agora trata a troca de CST como uma mudança tributária encadeada. Em entradas, se o CST de PIS/COFINS for alterado para `70–75`, `98` ou `99` e os campos dependentes não tiverem sido editados manualmente, base/alíquota/quantidade/valor do tributo são zerados e o total `VL_PIS`/`VL_COFINS` do C100 pai é recomposto.

O sistema não inventa crédito ao mudar para `50–66`; quando faltarem base/alíquota/valor, ele avisa para revisão. Toda edição manual explícita continua prevalecendo e aparece na conferência antes da geração do TXT.

## Novidade 17.8.90 — Conferência do estorno por NF

- A aba **Estorno ICMS** ganhou o botão **🔎 Conferir por NF**.
- A conferência mostra, por nota: **ICMS do C100**, **soma dos C170**, **C197 existente**, **estorno previsto**, **impacto no total** e **ajuste de centavos**.
- As divergências aparecem primeiro e podem ser localizadas na tabela principal com duplo clique.
- O motor agora reconcilia automaticamente diferenças de arredondamento de até **R$ 0,01 por NF**, ajustando um único C197 para que o total estornado da nota coincida exatamente com o ICMS do C100.
- Isso evita que centavos aceitos isoladamente se acumulem no mês (por exemplo, R$ 1,88).
- A memória CSV passa a registrar **Crédito C170**, **Ajuste de arredondamento** e **Crédito estornado** separadamente.
- Nenhum banco de dados é alterado.

## Atualização 17.8.89 — E-commerce MG: CFOP de entrada e responsabilidade própria do ICMS-ST

Para destinatários mineiros com regime especial de e-commerce que transfere a responsabilidade do ICMS-ST ao próprio estabelecimento, o FiscalPro deixa de converter automaticamente uma compra normal em `1403/2403` apenas porque o NCM/CEST do produto consta da lista de ST.

A Mega Mix E-Commerce Ltda (PTA 45.000044018-75) passa a ser reconhecida nessa condição. Quando a NF-e do fornecedor vier com `5101/5102/6101/6102`, CST de operação própria e sem base/valor de ICMS-ST, a compra para revenda fica em `1102/2102`. Havendo retenção efetiva de ST no XML ou CFOP de saída da família 54xx/64xx, permanece `1403/2403`.

**Versão atual: 17.8.86 — Entradas por XML no estorno de ICMS**

# FiscalPro 17.8.86

## Atualização 17.8.86 — XML das entradas no fluxo de créditos/estorno

Na aba **Estorno ICMS**, a etapa **1. ICMS das compras** passa a aceitar diretamente os **XMLs autorizados das NF-e de entrada**, individualmente ou dentro de ZIP. O XML é a fonte preferencial; DANFEs digitais em PDF continuam aceitas como contingência.

O FiscalPro lê os campos fiscais estruturados da NF-e e cruza a chave, o CNPJ destinatário, os itens, quantidades, valores, base, alíquota e ICMS com o SPED aberto. Só notas compatíveis com C100/C170/C190 e compra para revenda 1102/2102 podem seguir automaticamente. Divergências permanecem em revisão e o arquivo original não é alterado.


# FiscalPro 17.8.85

## Atualização 17.8.85 — Layout das divergências

As telas de auditoria deixam de concentrar divergências, revisões e fundamentos em uma caixa pequena. O detalhe agora abre em uma janela ampla e responsiva, com cada grupo em uma aba própria. Em notebooks com pouca altura a janela é maximizada automaticamente, e **F11** alterna maximização/restauração.

Na **Auditoria Tributária do SPED**, o botão **Ver divergência completa** e o duplo clique na linha abrem o problema, a orientação, a comparação entre valor atual/esperado e o contexto do item em tela grande. O acesso à **Ficha do NCM** permanece separado.

A mesma visualização ampliada é usada na **Análise Tributária em Lote**, **Auditoria de Cadastro por Excel** e **Auditoria de Cadastro por XML**. Esta atualização é exclusivamente de interface e não altera regras fiscais nem bancos de dados.


# FiscalPro 17.8.84

## Atualização 17.8.84 — NCM 3919.90 / CEST 01.090.00

O motor de ICMS-ST/MG deixa de confirmar o CEST `01.090.00` apenas pela coincidência do NCM `3919.90`. A descrição legal desse item é restrita a fitas, tiras, adesivos e autocolantes **refletores**, atuando como dispositivos refletivos de segurança rodoviária.

Para descrições como **“ADESIVO KIT PRATA BIZ125”**, o FiscalPro passa a concluir **NÃO APLICÁVEL — CEST 01.090.00**, sem CEST aplicado e sem MVA de 71,78%. Para descrições expressamente refletivas de segurança, o enquadramento permanece confirmado. Quando a descrição for insuficiente, o sistema mantém a análise condicional e exige confirmar a refletividade.

O hotfix também impede o uso automático do CEST residual `01.999.00` para esse caso, pois esse residual depende da hipótese específica de regime especial prevista no RICMS/MG. Nenhum banco de dados é alterado.

# FiscalPro 17.8.73

## Atualização 17.8.73 — Consolidação Estável

Esta versão elimina a bifurcação que reutilizou os números 17.8.71 e 17.8.72 em duas linhas diferentes. O `src/` volta a ser a única fonte operacional do sistema. Foram preservados o motor tributário condicional por finalidade, a correção visual do resumo, os detalhes técnicos ampliados, a regra do Simples Nacional no XML e a finalidade automotiva do item. As coberturas AC/AM foram recuperadas do ramo preservado e AP/RO foram reintegradas conforme os testes/documentação do projeto, com comportamento conservador quando a tabela estadual não está integralmente validada.

**Importante:** os bancos de dados do usuário não foram convertidos nem substituídos nesta consolidação.


## Atualização 17.8.72 — Cobertura Estadual de Rondônia

Rondônia passa a integrar a cobertura estadual estruturada com alíquota interna modal de **19,5%**. Para o NCM `87141000` / CEST `01.076.00`, o Decreto RO nº 29.048/2024 traz MVA original de **30%** e ajustada de **50,19%** na rota `MG → RO` a 7%. Como Rondônia não integra atualmente os Protocolos ICMS 41/08 ou 97/10, o FiscalPro identifica a ST interna, mas não presume a retenção pelo remetente mineiro.

Para o NCM `40114000` / CEST `16.003.00`, a tabela vigente usa MVA original de **50%** e ajustada de **73,29%** em `MG → RO`, conforme o Decreto 29.048/2024 e o Convênio ICMS 102/17. O FECOEP/RO fica separado: **0% para a autopeça testada e 2% para pneumáticos**. A Ficha Inteligente e o Configurador Olist continuam consumindo o mesmo motor central.

# FiscalPro 17.8.67

## Atualização 17.8.67 — Cobertura Estadual do Piauí

O Piauí passa a integrar a cobertura estadual estruturada com alíquota interna modal de **22,5%**. Para autopeças, o FiscalPro usa a regra própria do RICMS/PI, Anexo X, arts. 93 e 94: **MVA original de 40,00% nos demais casos** e **26,50% nas hipóteses qualificadas de fidelidade/exclusividade**. Na rota `MG → PI` a 7%, as MVAs ajustadas são **68,00%** e **51,80%**, respectivamente. A hipótese reduzida continua condicionada aos requisitos legais e, quando aplicável, à autorização prévia do Fisco do Piauí.

Para o NCM `40114000` / CEST `16.003.00`, a regra de pneumáticos usa MVA original de **60,00%** e MVA ajustada de **92,00%** na rota `MG → PI` a 7%, em conjunto com o Convênio ICMS 102/17. O FECOP fica separado e em **0% para autopeças e pneumáticos no escopo estruturado**. Eventual regime especial/credenciamento do destinatário atacadista de peças para motocicletas não é presumido e aparece como ponto de revisão.

Ficha Inteligente e Configurador Olist continuam consumindo o mesmo motor tributário central.

## Atualização 17.8.66 — Simples Nacional no ICMS-ST/MG por XML

No módulo **Importar XML, calcular e conferir ICMS-ST/MG**, ao marcar ou importar uma NF-e cujo remetente seja do Simples Nacional, o FiscalPro passa a aplicar automaticamente a regra mineira: usa **MVA original**, sem MVA ajustada interestadual, e calcula a **dedução da operação própria pela alíquota aplicável** mesmo quando não há `vICMS` destacado no XML. Essa parcela existe apenas na memória do ICMS-ST e não representa crédito escritural do destinatário. O ajuste manual por item continua disponível para exceções.


## Atualização 17.8.65 — Vínculo Automático da Agenda com Contas Existentes

Quando uma fatura da Agenda já foi cadastrada manualmente no Contas a Pagar antes de existir o vínculo da Agenda, o botão **✓ Dar baixa hoje** agora procura esse lançamento automaticamente. A busca exige a mesma empresa e competência e confirma o fornecedor; categoria e proximidade do vencimento ajudam a escolher a melhor correspondência. O usuário sempre confirma o vínculo antes da baixa.

Se houver mais de uma conta compatível, o FiscalPro apresenta os candidatos para escolha pelo ID. Se nenhuma conta compatível for encontrada, o fluxo continua orientando a usar **Lançar no Contas a Pagar**. Nenhuma conta já ligada a outro item da Agenda é reaproveitada.

## Atualização 17.8.64 — Baixa Direta na Agenda de Faturas

A Agenda Inteligente de Faturas passa a permitir a baixa financeira sem sair da própria agenda. Para uma fatura já lançada e vinculada ao Contas a Pagar, selecione a linha e clique em **✓ Dar baixa hoje**. O FiscalPro grava a data atual na conta vinculada e sincroniza a etapa mensal para **PAGA**. Faturas ainda não lançadas permanecem protegidas e precisam primeiro ser vinculadas ao Contas a Pagar.

A rotina de baixa foi centralizada no serviço financeiro e é compartilhada com o botão **Dar baixa hoje** da tela principal, preservando datas de pagamento já existentes.

## Atualização 17.8.63 — Cobertura Estadual do Maranhão

O Maranhão passa a integrar a cobertura estadual estruturada do FiscalPro com alíquota interna modal de **23%**. Para autopeças, o motor aplica o Protocolo ICMS 41/08 quando a rota e o CEST estiverem abrangidos: na operação `MG → MA` a 7%, a MVA-base de **71,78%** resulta em MVA ajustada de **107,47%**; a hipótese qualificada de fidelidade/exclusividade preserva MVA-base de **36,56%**, ajustada para **64,94%**. A responsabilidade do remetente é exibida somente quando o enquadramento do protocolo estiver confirmado.

Para pneumáticos, o NCM `40114000` / CEST `16.003.00` segue o Convênio ICMS 102/17, com MVA-base de **60%** e MVA ajustada de **93,25%** na rota `MG → MA` a 7%. O FUMACOP permanece em **0% para os dois NCMs automotivos estruturados desta cobertura**, enquanto produtos fora desse escopo continuam sujeitos a revisão específica. Ficha Inteligente e Configurador Olist seguem consumindo a mesma base tributária central.


## Atualização 17.8.62 — Cobertura Estadual de Sergipe

Sergipe passa a integrar a cobertura estadual estruturada com alíquota interna modal de 19% e FECOEP de 1% para autopeças e pneumáticos do escopo instalado. O ajuste de MVA considera ICMS + FECOEP, conforme o RICMS/SE. Autopeças usam a Tabela VI/Protocolo 97/10 e, quando a origem é MG, o FiscalPro não força retenção ST pelo remetente: mantém a MVA oficial e sinaliza a antecipação prevista no art. 784, II, d. Pneumáticos seguem o Convênio ICMS 102/17. Ficha Inteligente e Configurador Olist continuam usando o mesmo motor estadual.


## Atualização 17.8.60 — Fundamentação RN Sincronizada

A Ficha e a Base Legal agora mostram a fonte estadual efetivamente usada pela cobertura do Rio Grande do Norte. Em autopeças, a antecipação de 40% é vinculada ao RICMS/RN, Anexo 005; em pneumáticos, o enquadramento é vinculado ao Anexo 007. O fallback visual para a fonte de ST/Minas Gerais foi removido das operações com outras UFs.


**Assistente Fiscal Inteligente** — análise e correção assistida de SPED, SPED ↔ Excel, consulta tributária, ICMS-ST, Robô Fiscal, Contas a Pagar e Controle de Entregas.

## Base consolidada

Esta versão consolida a linha funcional até o Hotfix 17.7.7 e passa a ser a base limpa para novas evoluções. O código-fonte não carrega ambientes virtuais, builds antigos, executáveis antigos, caches Python, backups, logs ou dados pessoais do usuário.

### Fluxo SPED Contribuições

1. Gerar o SPED no sistema de origem.
2. Quando houver apuração/créditos, gerar as apurações no PGE antes de exportar para Excel.
3. Abrir o TXT no FiscalPro e exportar para Excel.
4. Corrigir no Excel usando os nomes técnicos oficiais dos campos.
5. Validar no FiscalPro, revisar a conferência e gerar o TXT.
6. Validar o arquivo final no PGE.

O conversor preserva a precisão técnica por campo e a hierarquia do Bloco M. O FiscalPro não deve inventar códigos/naturezas de crédito quando a relação for ambígua.

## Executar pelo código-fonte

```bat
python -m pip install -r requirements.txt
python main.py
```

No primeiro uso em uma pasta nova, as bases limpas são copiadas de `templates/`. Em uma instalação empacotada, os dados persistentes ficam fora do executável, na pasta de dados do usuário.


## Backup completo

O backup interno protege `fiscalpro.db` e toda a pasta persistente `dados/`, incluindo Contas a Pagar e Controle de Entregas. Os documentos organizados pelo Robô Fiscal permanecem opcionais. Esse backup é o caminho recomendado para migrar dados entre instalações/computadores.

No Hotfix 17.8.3, o banco `dados/financeiro/contas_pagar.db` passa a ter um único caminho oficial. A migração do executável procura instalações antigas/versionadas, recupera automaticamente uma base antiga quando o banco atual estiver vazio e preserva uma cópia `ANTES_MIGRACAO`. O manifesto do backup registra a quantidade de contas e o resultado do `PRAGMA quick_check`; uma restauração que tentaria substituir uma base com contas por um backup financeiro com 0 registros é bloqueada.

## PIS/COFINS nacional — Hotfix 17.8.4

Quando um NCM válido não estiver nos Anexos I e II da Lei nº 10.485/2002, a Ficha Inteligente não apresenta mais a ausência de enquadramento monofásico como se o NCM não existisse. O motor continua para a análise nacional por regime e, quando houver contexto suficiente, exibe a tributação padrão como **sugestão condicional** — sem promover automaticamente essa sugestão a regra confirmada. Para Lucro Real/saída, por exemplo, o padrão não cumulativo pode ser exibido como CST 01 / PIS 1,65% / COFINS 7,60%, sempre sujeito à conferência das exceções legais e setoriais.

## ICMS próprio na Ficha Inteligente — Hotfix 17.8.5

Quando o cadastro local não possui CST/CSOSN de ICMS, mas o motor oficial de MG já determinou uma alíquota nominal, a Ficha deixa de exibir o contraditório **“CST Não informado • 0,00%”**. A linha operacional passa a mostrar a alíquota analisada e o texto **“CST a definir conforme operação”**, preservando a revisão do CST/CSOSN conforme regime, origem da mercadoria, benefício/redução e posição da empresa na substituição tributária. Um CST local real continua prevalecendo, inclusive nos casos em que a alíquota própria é 0,00%.

## CFOP e segurança oficial — Hotfix 17.8.6

A Ficha Inteligente passa a sugerir CFOP com base no contexto já conhecido, sem inventar a posição da empresa na substituição tributária. Em revenda interna com ICMS-ST confirmado, por exemplo, exibe **5405 / 5403 — condicional**, explicando que 5405 se aplica quando o ST já foi retido anteriormente e 5403 quando o estabelecimento for responsável pela retenção na saída.

A segurança geral também deixa de depender exclusivamente da existência de uma regra local completa. NCM, TIPI, ICMS/MG, ICMS-ST/CEST/MVA, PIS/COFINS e o grau de definição do CFOP entram no cálculo. Se houver componentes condicionais, o resultado permanece limitado à faixa **MÉDIA**, evitando tanto percentuais artificialmente baixos quanto falsa confiança alta.

## Testes

```bat
python -m pip install -r requirements-dev.txt
pytest -q
```

## Instalador Windows

Execute `CRIAR_INSTALADOR.bat`. O processo recria `.venv_instalador`, `build/pyinstaller`, `dist/FiscalPro` e `instalador/saida`; essas pastas não fazem parte da base limpa.

## Robô Fiscal Gmail

`INSTALAR_ROBO_EMAIL.bat` instala apenas as dependências necessárias ao robô. Credenciais OAuth e tokens são dados privados e **não fazem parte desta base consolidada**.

## Histórico

Os changelogs e roteiros antigos foram retirados da raiz para evitar confusão e estão compactados em `docs/HISTORICO_TECNICO_ATE_17_7_7.zip`.


## 17.8.87 — Conferência de CFOP nas entradas
Na etapa de XML/PDF das compras para revenda, o FiscalPro pode corrigir CFOPs de entrada quando a decisão for determinística. A análise distingue mercadorias sem ST (1102/2102) e sujeitas à ST (1403/2403), sem usar a alíquota isoladamente. Casos ambíguos permanecem para revisão manual.

## 17.8.88 — Capacetes abreviados nos XMLs de entrada

O motor de CFOP passa a considerar o CEST informado no próprio XML e reconhece descrições abreviadas como `CAP. SPORT MOTO`, evitando separar artificialmente itens equivalentes entre CFOP 2102 e 2403.

