## 18.2.1 — Auditoria NCM por descrição/família
- deixa de tratar todo NCM de 8 dígitos como automaticamente coerente com a mercadoria;
- valida NCM já preenchido contra regras semânticas e consenso forte da mesma marca/família;
- corrige o caso real **SANFONA BENG. 24D VERM (CIRCUIT)**, em que 33030010 era repetido apesar de ser um outlier frente às demais sanfonas Circuit do cadastro;
- **FAIXA/ADESIVO TANQ TWISTER** passa a sugerir 39199020 como candidato quando o cadastro traz NCM incompatível, mantendo status **REVISAR** até confirmar que o material é PVC;
- a tributação de referência pode ser simulada com o NCM sugerido, mas nenhuma correção cadastral é aplicada automaticamente.

## 18.2.0 — NF-e / NFS-e e Manifestação do Destinatário
- preserva sem alterações funcionais o módulo NFS-e Nacional existente;
- renomeia a aba principal para **NF-e / NFS-e** e adiciona subaba própria para NF-e;
- consulta NF-e destinadas ao CNPJ pela Distribuição DF-e do Ambiente Nacional, com controle incremental de NSU;
- transmite Ciência da Operação, Confirmação da Operação, Desconhecimento da Operação e Operação não Realizada com certificado A1;
- assina o XML do evento, armazena retorno/protocolo e mantém a senha do A1 somente em memória;
- permite salvar o XML completo quando disponibilizado pela distribuição;
- mostra o prazo conclusivo de 90 dias vigente desde 01/06/2026;
- mantém dados da NF-e isolados em `dados/nfe/manifestacao_nfe.db`.

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

# FiscalPro 17.8.124 — Bloco M fecha com o PGE

- Corrige o fechamento de `M400/M410` e `M800/M810` a partir das fontes documentais suportadas, incluindo `C175` de NFC-e.
- Cria `M205` e `M605` quando `M200/M600` possuem contribuição a recolher e o `0110` comprova incidência exclusiva não cumulativa/cumulativa.
- Corrige devolução de compra em saída com CFOP de devolução e CST de aquisição `70–75`: quando não há base/alíquota/valor preenchidos, o FiscalPro normaliza PIS e COFINS para `CST 49` sem inventar valores.
- O Pré-PVA passa a apontar CST de aquisição usado em operação de saída e a ausência de `M205/M605`.
- Caso real `SPED CONT 08-2026_CONVERTIDO5.txt`: o item `PNEU 1306013 HB37 SCAM RINALDI`, CFOP `6411`, é normalizado de CST 73 para 49; `M400/M800` CST 04 fecham em R$ 239.942,64, CST 07 em R$ 675,90; `M205` é criado com R$ 2.760,92 e `M605` com R$ 12.684,98.
- Nenhum banco de dados é alterado.

# FiscalPro 17.8.123 — C175: bases PIS/COFINS sincronizadas no Excel → TXT

- corrige o erro do PGE em C175 quando `VL_BC_PIS` e `VL_BC_COFINS` ficam diferentes após a exclusão do ICMS;
- se uma base foi editada explicitamente no Excel, ela passa a prevalecer e é espelhada para o outro tributo;
- também repara o padrão herdado das versões anteriores em que uma base permanecia igual ao `VL_OPR` e a outra já continha a redução;
- recalcula `VL_PIS` ou `VL_COFINS` do lado espelhado usando a alíquota percentual do próprio registro;
- não interfere em modalidade por quantidade, CSTs diferentes ou quando as duas bases foram editadas manualmente e ficaram divergentes;
- caso real `SPED CONT 08-2026_ORGANIZADO.xlsx`: 129 C175 com bases divergentes foram reconciliados e a validação local ficou sem divergência de base PIS/COFINS.
- nenhum banco de dados é alterado.

# FiscalPro 17.8.122 — Conferência Excel automática

- Ao validar a planilha, a grade **Original × Novo** passa a ser preenchida automaticamente.
- Remove a necessidade de clicar novamente em **Conferir alterações** depois de uma validação bem-sucedida.
- O status passa a informar a quantidade de campos alterados no Excel e a quantidade total de itens da conferência, incluindo ajustes automáticos.
- Mantém a conferência manual disponível para reexecutar/filtros.
- Não altera banco de dados nem as regras tributárias; preserva a correção 17.8.121 de 0206 e Bloco M.

# FiscalPro 17.8.121 — Excel → TXT: vínculos 0206 e Bloco M

- Corrige planilhas em que a aba 0206 perdeu a coluna oculta `__FP_ID__`: o vínculo é recuperado somente quando as linhas continuam idênticas às referências originais da aba `_FISCALPRO_ORDEM`.
- Corrige a sincronização de M100/M105 e M500/M505 quando o mesmo CST/alíquota possui naturezas de crédito distintas.
- Para o retorno Excel → TXT, os CFOPs 1102/2102/1403/2403 são tratados como uma família documental de revenda para provar o M105/M505 correspondente, sem ampliar a rotina fiscal de exclusão automática de ICMS próprio.
- Validado no arquivo real `SPED CONT 08-2026_ORGANIZADO.xlsx`: 0 erros estruturais de importação, 1.030 alterações preservadas e Bloco M recalculado de forma determinística.

# 17.8.97 — Inclusão de CT-e ausentes sem crédito de ICMS

- Novo botão **➕ Incluir CT-e sem crédito** em **SPED Inteligente > CT-e / XML**.
- Importa ZIP com XMLs de CT-e, filtra autorização, período e tomador do frete.
- Ignora chaves já existentes, cria 0150/D100/D190 e não apropria crédito de ICMS.
- Preserva o E110 original e gera relatório CSV.
- Hotfix preparado diretamente para a base 17.8.95.

# FiscalPro 17.8.95 — bloqueio de C197 sem crédito real

- Bloqueia geração automática de C197 para C170 sem base, alíquota ou VL_ICMS positivos.
- Bloqueia CFOP 1407/1556/2407/2556 (uso/consumo) no estorno automático.
- Detecta C197 indevido já existente mesmo em C100 com ICMS zero.
- C197 órfão/sem C170 elegível passa a REVISAR e aparece na conferência por NF.
- Regressão real: NF 49092 / item 90401KRMR20 / CFOP 1556 / C197 R$ 1,88 é identificado como indevido.

## 17.8.94 — Reconciliação segura de arredondamento no estorno ICMS

- Amplia a conferência do estorno por NF para detectar **arredondamento acumulado item a item**, inclusive quando a diferença total da nota é superior a R$ 0,01.
- A correção automática só é liberada quando **cada C170 = BC × alíquota arredondado a centavos** e o **C100 = soma teórica exata** calculada antes do arredondamento individual.
- O teto matemático de arredondamento é calculado pela quantidade de linhas C170; diferenças fora desse teto ficam em **REVISAR**.
- O ajuste é distribuído em passos de R$ 0,01 pelos itens com resíduos compatíveis com o sinal, em vez de concentrar toda a diferença em um único C197.
- A tela **Conferir por NF** passa a mostrar ICMS teórico, impacto bruto, teto de arredondamento e ajuste aplicado.
- A memória CSV continua separando Crédito C170, Ajuste de arredondamento e Crédito estornado.
- Caso de regressão automatizada: 392 itens com diferença acumulada de **+R$ 1,88** e **-R$ 1,88**, ambos reconciliados exatamente; divergência de R$ 1,89 sem prova exata permanece bloqueada.
- Nenhum banco de dados é alterado.

## 17.8.93 — Auditoria interna C170 x C190

- Corrige o caso em que a planilha mostra **0 campos alterados**, mas o TXT de origem já possui C170 corrigido e C190 antigo.
- A validação compara as chaves analíticas `CST_ICMS + CFOP + ALIQ_ICMS` do C170 com o C190 de cada C100.
- Só reconstrói automaticamente divergências internas quando os totais de BC/ICMS/BC-ST/ICMS-ST/IPI fecham entre itens e analítico.
- Funde C190 antigos quando vários grupos passam a uma única combinação no C170.
- Preserva `VL_RED_BC` quando o novo resumo possui um único grupo; múltiplos grupos com redução permanecem em revisão.
- A tela e o relatório exibem **Ajustes automáticos C190** e **Documentos C190 reconstruídos**, mesmo com 0 alterações manuais no Excel.
- Caso real de agosto/2026: 30 documentos reconstruídos com segurança, 2 mantidos em revisão por diferença monetária, sem novos erros no Pré-PVA.
- Nenhum banco de dados é alterado.

## 17.8.92 — C190 reconstruído a partir do C170

- Corrige o fluxo **Excel → TXT** quando `CST_ICMS`, `CFOP` ou `ALIQ_ICMS` é alterado no `C170`.
- O FiscalPro passa a reagrupar automaticamente o `C190` do `C100` afetado pela nova combinação **CST + CFOP + alíquota de ICMS**.
- O `VL_OPR` total já escriturado é preservado e rateado proporcionalmente entre os novos grupos; `VL_BC_ICMS`, `VL_ICMS`, `VL_BC_ICMS_ST`, `VL_ICMS_ST` e `VL_IPI` são recompostos pelos `C170`.
- Se a usuária também editar o próprio `C190`, a edição manual prevalece.
- Documentos com `VL_RED_BC` diferente de zero ou com `COD_OBS` distintos não sofrem rateio automático: ficam sinalizados para revisão.
- O reagrupamento aparece na **Conferência Excel** antes da geração do TXT.
- Nenhum banco de dados é alterado.

## 17.8.91 — CST do C170 sincronizado com C100

- Corrige o fluxo **Excel → TXT** quando `CST_PIS`/`CST_COFINS` é alterado no `C170`.
- Em entradas `1xxx/2xxx/3xxx`, mudança para CST sem direito a crédito (`70–75`, `98`, `99`) passa a zerar automaticamente base, alíquota, quantidade e valor do respectivo PIS/COFINS, desde que esses campos não tenham sido editados manualmente.
- Depois da normalização, o `C100` pai é retotalizado pela soma efetiva de `VL_PIS` e `VL_COFINS` dos seus `C170`.
- Se a usuária também alterar base/alíquota/valor, o FiscalPro preserva a decisão manual e deixa a conferência/Pré-PVA apontar eventual inconsistência.
- Mudança para CST de crédito `50–66` não cria base nem crédito por aproximação; o sistema apenas avisa quando faltarem valores calculáveis.
- Nenhum banco de dados é alterado.

## 17.8.90 — Conferência do estorno por NF e centavos

- A aba **Estorno ICMS** ganhou o botão **🔎 Conferir por NF**.
- A conferência mostra, por nota: **ICMS do C100**, **soma dos C170**, **C197 existente**, **estorno previsto**, **impacto no total** e **ajuste de centavos**.
- As divergências aparecem primeiro e podem ser localizadas na tabela principal com duplo clique.
- O motor agora reconcilia automaticamente diferenças de arredondamento de até **R$ 0,01 por NF**, ajustando um único C197 para que o total estornado da nota coincida exatamente com o ICMS do C100.
- Isso evita que centavos aceitos isoladamente se acumulem no mês (por exemplo, R$ 1,88).
- A memória CSV passa a registrar **Crédito C170**, **Ajuste de arredondamento** e **Crédito estornado** separadamente.
- Nenhum banco de dados é alterado.

# FiscalPro 17.8.89 — CFOP de entrada no regime especial E-commerce/MG

- Corrige falso **2403** nas compras para revenda da **Mega Mix E-Commerce Ltda** quando o fornecedor emite a NF-e sem retenção de ICMS-ST, conforme o regime especial de atribuição de responsabilidade do destinatário (PTA **45.000044018-75**, vigente até 31/12/2032 na relação pública da SEF/MG).
- Para XML de venda normal `5101/5102/6101/6102`, sem `vBCST`/`vST`, a entrada permanece **1102/2102**, mesmo que o produto tenha NCM/CEST materialmente listado em ST.
- Se o XML trouxer CFOP de ST ou valores de ICMS-ST, o FiscalPro continua usando **1403/2403**.
- Valida os casos reais das NF-e **999854 (Marlon Bonilha)** e **238791 (Starplast)**: capacetes NCM `65061090`, CEST `01.013.00`, CFOP `6101`, CST `00`, sem retenção de ST -> **2102** para a Mega Mix.
- Não altera bancos de dados nem a regra geral de ST para destinatários sem regime especial.

# FiscalPro 17.8.88 — Capacete abreviado / CEST no CFOP de entrada

- Corrige falso 2102 em XMLs de capacete quando a descrição vem abreviada como `CAP.`.
- Passa a ler o CEST do item no XML de entrada.
- Para NCM 65061090 + CEST 01.013.00 + contexto de capacete de motocicleta, reconhece a natureza ST mesmo sem a palavra literal `CAPACETE`.
- Mantém as travas para EPI, capacete industrial, balístico e bombeiro.
- Não usa a alíquota de ICMS isoladamente para decidir CFOP.
- Caso real validado: NF 999846 da Marlon Bonilha/LM, itens CAP-388, CAP-389 e CAP-390.

# FiscalPro 17.8.87 — CFOP das entradas por XML

- A etapa **ICMS das compras** passa a conferir e corrigir também o **CFOP de entrada por item**.
- A alíquota de ICMS isoladamente **não determina o CFOP**. O motor cruza natureza da saída do XML, UF, finalidade de revenda e enquadramento de ICMS-ST.
- Compra para revenda sem ST: **1102/2102** conforme operação interna/interestadual.
- Compra para revenda com mercadoria sujeita à ST: **1403/2403**.
- Notas mistas podem gerar C190 separados por CFOP, preservando o valor total da operação.
- NCM **65061090**: quando confirmada a finalidade de capacete de motocicleta, o motor preserva o enquadramento material do antigo 65061000 / CEST 01.013.00 após o desdobramento de 2026.
- A memória CSV registra **CFOP anterior, CFOP corrigido e motivo**.
- Casos ambíguos ficam em **REVISAR**; o FiscalPro não troca CFOP por hipótese.
- Nenhum banco de dados é alterado pelo hotfix.

# 17.8.86 — Entradas por XML no estorno de ICMS

- corrige a etapa **ICMS das compras** para aceitar XML autorizado de NF-e diretamente, além de DANFE em PDF e ZIP;
- XML passa a ser a fonte preferencial porque os campos fiscais são estruturados e não dependem da leitura visual do PDF;
- lê chave, destinatário, número, itens, NCM, CST, CFOP, quantidade, valor, base, alíquota e ICMS próprio do XML;
- cruza a NF-e com C100/C170/C190 do SPED antes de permitir qualquer alteração;
- mantém bloqueios conservadores para CNPJ divergente, item/valor divergente, ausência de CST seguro e notas sem ICMS próprio;
- ZIP pode conter XML e PDF; documentos duplicados pela mesma chave são considerados uma única vez, priorizando XML;
- atualiza a tela para **Selecionar XMLs/PDFs/ZIP** e deixa claro que XML é preferencial;
- nenhum banco de dados é alterado.

# 17.8.85 — Divergências e revisões ampliadas

- substitui os detalhes compactos por janelas grandes, responsivas e maximizáveis;
- separa **Divergências**, **Revisões**, **Tributação**, **Fundamentos** e **Tratamento sugerido** em abas próprias;
- aplica a melhoria à Análise Tributária em Lote e às Auditorias de Cadastro por Excel e XML;
- na Auditoria Tributária do SPED, adiciona **Ver divergência completa** e altera o duplo clique para abrir a visão ampliada;
- mantém o botão da Ficha do NCM separado para não misturar diagnóstico com consulta;
- inclui botão **Copiar aba** e atalho F11 para maximizar/restaurar;
- alteração exclusivamente visual: nenhum banco, SPED ou motor tributário é modificado.

# 17.8.84 — Adesivos 3919.90 por descrição legal

- corrige falso positivo de ICMS-ST no NCM `39199090` quando o produto é kit/adesivo decorativo de motocicleta;
- o CEST `01.090.00` só é confirmado quando a descrição indicar material refletivo de segurança rodoviária;
- `ADESIVO KIT PRATA BIZ125` passa a retornar **NÃO APLICÁVEL**, sem CEST e sem MVA 71,78%;
- descrição insuficiente permanece condicional, sem ST por NCM isolado;
- bloqueia fallback automático para CEST residual `01.999.00` nesse cenário;
- indicador de ICMS-ST mostra `100% — NÃO APLICÁVEL` quando a exclusão pela descrição estiver confirmada;
- preserva bancos, SPED, Financeiro, PIS/COFINS e demais regras tributárias.

# 17.8.73 — Consolidação Estável

- unifica os ramos conflitantes 17.8.71/17.8.72;
- mantém o motor condicional 17.8.70 e a finalidade automotiva;
- restaura o layout compacto do resumo;
- preserva a regra do Simples Nacional 17.8.66 no XML;
- recupera AC/AM e reintegra AP/RO no motor estadual;
- mantém bancos e dados do usuário sem migração destrutiva;
- remove os pacotes conflitantes da raiz operacional.

# 17.8.72 — Cobertura Estadual de Rondônia

- ICMS interno modal RO: 19,5%.
- Autopeça CEST 01.076.00: Decreto 29.048/2024, MVA 30% → 50,19% em MG→RO a 7%; responsabilidade local em revisão.
- RO não integra atualmente os Protocolos 41/08 ou 97/10; a retenção pelo remetente mineiro não é presumida.
- Pneu CEST 16.003.00: MVA 50% → 73,29%, conforme Decreto 29.048/2024 e Convênio 102/17.
- FECOEP/RO separado: 0% na autopeça e 2% no pneumático testado.
- Configurador Olist permanece ligado ao mesmo `ICMSUFService`, sem tabela paralela.

# 17.8.68 — Cobertura Estadual do Tocantins

- ICMS interno modal TO: 20%.
- FECOEP/TO separado: 0% para autopeças/pneumáticos estruturados; adicional de 2 p.p. restrito às hipóteses do art. 27, I.
- Autopeças: Anexo XXI + Protocolo 97/10, MVA 36,56%/71,78% e ajuste interestadual; MG→TO não força retenção pelo remetente porque MG não é signatário atual do Protocolo 97/10.
- Pneumáticos: Convênio 102/17; CEST 16.003.00 usa MVA 60% → 86% na rota MG→TO a 7%.
- Regime especial/beneficiário da Lei TO nº 1.201/2000 permanece como alerta, sem presunção automática.

# Hotfix 17.8.67 — Cobertura Estadual do Piauí

- Inclui PI na cobertura estadual estruturada.
- Alíquota interna modal: 22,5% desde 01/04/2025.
- Autopeças: RICMS/PI, Anexo X, arts. 93-94; MVA original 26,50% (fidelidade qualificada) ou 40,00% (demais casos); MG→PI a 7%: 51,80% / 68,00%.
- Pneumáticos: arts. 75-76 e Convênio ICMS 102/17; pneu de motocicleta 60,00% → 92,00% na rota MG→PI a 7%.
- FECOP separado e 0% para autopeças/pneumáticos no escopo estruturado.
- Regime especial/credenciamento de atacadista de peças para motocicletas permanece como alerta e não é presumido.
- Configurador Olist continua consumindo o mesmo motor central do FiscalPro.

# FiscalPro 17.8.66 — Simples Nacional no ICMS-ST/MG por XML

## XML → ICMS-ST/MG
- Ao identificar **remetente do Simples Nacional**, o FiscalPro passa a usar automaticamente a **MVA original**, sem aplicar a MVA ajustada interestadual, conforme art. 20, § 6º do Anexo VII do RICMS/MG/2023.
- A dedução da operação própria deixa de depender de `vICMS` destacado: para ME/EPP do Simples, é calculada pela **alíquota interna ou interestadual aplicável sobre o valor da operação**, conforme art. 22, § 1º.
- Na operação interestadual, a sugestão continua sendo **12% para mercadoria nacional** e **4% quando a origem da mercadoria exigir a alíquota interestadual de 4%**; o usuário pode informar outra alíquota quando o caso concreto exigir.
- Em operação interna MG→MG, a dedução usa a alíquota interna informada.
- A parcela é identificada como **dedução da memória do ICMS-ST** e **não gera crédito escritural**.
- Ajuste manual por item continua prevalecendo quando informado.
- A interface bloqueia a opção de MVA ajustada e mantém a dedução automática enquanto “Remetente do Simples Nacional” estiver marcado.

## Segurança
- O comportamento anterior para fornecedores fora do Simples foi preservado.
- Nenhum banco de dados faz parte da hotfix.

# FiscalPro 17.8.65 — Vínculo Automático da Agenda com Contas Existentes

## Agenda Inteligente de Faturas
- Corrige a baixa de faturas que **já estavam lançadas manualmente no Contas a Pagar**, mas ainda apareciam na Agenda com `Conta ID` vazio.
- Ao clicar em **✓ Dar baixa hoje**, se não houver vínculo, o FiscalPro procura uma conta compatível pela **mesma empresa + competência + fornecedor**, usando também categoria e proximidade do vencimento para ordenar candidatos.
- Se houver uma única conta compatível, o sistema mostra os dados e pede confirmação antes de vincular.
- Se houver mais de uma, apresenta os candidatos e permite informar o ID correto, evitando vínculo silencioso com a conta errada.
- Depois do vínculo, a mesma rotina de baixa da 17.8.64 é usada; contas já pagas preservam a data de pagamento original.
- Contas já vinculadas a outro item da Agenda não são oferecidas como candidatas.

## Segurança
- Nenhuma regra tributária foi alterada.
- Nenhum banco de dados faz parte da hotfix.

# FiscalPro 17.8.64 — Baixa Direta na Agenda de Faturas

## Agenda Inteligente de Faturas
- Adiciona o botão **✓ Dar baixa hoje** diretamente na Agenda de Faturas.
- O botão funciona para faturas já **LANÇADAS** e vinculadas a uma conta do Contas a Pagar.
- A baixa grava a data atual na conta e sincroniza imediatamente a etapa da Agenda para **PAGA**.
- Se a conta já estiver paga, a data original da baixa é preservada.
- Faturas ainda sem `conta_id` são protegidas: o FiscalPro orienta a lançar no Contas a Pagar antes da baixa.
- O botão **Dar baixa hoje** da tela principal do Contas a Pagar passa a usar a mesma rotina central, evitando comportamentos diferentes entre as duas telas.

## Segurança
- Nenhuma regra tributária foi alterada.
- Nenhum banco de dados faz parte da hotfix.

## Validação
- **3 testes específicos da baixa direta na Agenda** aprovados.
- Suíte completa: **496 testes aprovados, 0 falhas**.
- `python -m compileall -q main.py src tests`: aprovado.
- Instalação simulada sobre a 17.8.63: aprovada.
- Hotfix sem arquivos `.db`.

# FiscalPro 17.8.63 — Cobertura Estadual do Maranhão

## Cobertura tributária MA
- Alíquota interna modal de **23%**, preservando revisão de alíquotas específicas, reduções e benefícios.
- Autopeças: Protocolo ICMS 41/08, com MVA original **36,56%** na hipótese qualificada de fidelidade/exclusividade e **71,78%** nos demais casos. Em `MG → MA` a 7%, as MVAs ajustadas são **64,94% / 107,47%**.
- Na rota `MG → MA`, quando o CEST estiver abrangido pelo Protocolo ICMS 41/08, o FiscalPro identifica a responsabilidade do **remetente/substituto**, mantendo as exceções do protocolo em revisão.
- Pneumáticos: CEST `16.003.00` / NCM `40114000`, Convênio ICMS 102/17, MVA original **60%** e ajustada **93,25%** a 7%.
- FUMACOP/MA: **0% nos dois segmentos automotivos estruturados desta entrega (autopeças e pneumáticos)**; outros produtos permanecem sujeitos a revisão específica.
- Detalhes técnicos e Base Legal identificam a fonte contextual **SEFAZ/MA — RICMS/MA** e a regra efetivamente aplicada.
- O Configurador Olist continua consumindo o mesmo `ICMSUFService`, sem tabela paralela do Maranhão.

## Validação
- **9 testes específicos do Maranhão** aprovados.
- Suíte completa: **493 testes aprovados, 0 falhas**.
- `python -m compileall -q main.py src tests`: aprovado.
- Instalação simulada sobre a 17.8.62: aprovada.
- Hotfix sem arquivos `.db`.

# FiscalPro 17.8.62 — Cobertura Estadual de Sergipe

## Cobertura tributária SE
- Alíquota interna modal de **19%**, mantendo revisão de alíquotas específicas, reduções e benefícios.
- FECOEP/SE separado do ICMS: **1% no escopo automotivo estruturado**; o rol especial do art. 40-C permanece sujeito a 2%.
- A MVA ajustada segue o RICMS/SE, art. 684, § 4º-D-B: para o ajuste, considera **ICMS + FECOEP**; no escopo automotivo, 19% + 1% = 20%.
- Autopeças: MVA original **36,56%** na hipótese qualificada de fidelidade/exclusividade e **71,78%** nos demais casos; na operação interestadual a 7%, **58,75% / 99,69%**.
- Na rota **MG→SE**, MG não é signatário do Protocolo ICMS 97/10; o FiscalPro preserva a MVA oficial, mas **não força retenção ST pelo remetente**, sinalizando a antecipação do art. 784, II, d, do RICMS/SE.
- Pneumáticos: CEST 16.003.00 usa MVA original **60%** e ajustada **86%** a 7%, com responsabilidade interestadual pelo Convênio ICMS 102/17.
- Detalhes técnicos e Base Legal passam a identificar a fonte contextual **SEFAZ/SE — RICMS/SE** e a regra efetivamente aplicada.
- O Configurador Olist continua consumindo o mesmo `ICMSUFService`, sem tabela paralela de Sergipe.

## Validação
- 10 testes específicos de Sergipe aprovados.
- Suíte completa: **484 testes aprovados, 0 falhas**.
- `python -m compileall -q src tests`: aprovado.
- Hotfix sem arquivos `.db`.

# FiscalPro 17.8.61 — Origem da Regra RN Corrigida

- Corrige o campo **Origem da regra** na Ficha Inteligente quando a regra manual está vazia e a interface a normaliza como “Não informada”.
- Para `87141000` em `MG → RN`, a origem passa a exibir **SEFAZ/RN — RICMS/RN, Anexo 005**.
- Mantém **Regra aplicada: ANTECIPAÇÃO ICMS/RN — ANEXO 005**.
- Nenhum cálculo tributário foi alterado.

# FiscalPro 17.8.60 — Fundamentação RN Sincronizada

## Correções
- Detalhes técnicos do RN passam a exibir a fonte oficial da regra estadual estruturada quando não existe regra manual/local cadastrada.
- Para autopeças do RN, `Origem da regra` passa a indicar **SEFAZ/RN — RICMS/RN, Anexo 005** e `Regra aplicada` passa a indicar **ANTECIPAÇÃO ICMS/RN — ANEXO 005**.
- Para pneumáticos, a fonte contextual passa a indicar o **Anexo 007 do RICMS/RN**.
- A janela **Base Legal e Fontes Oficiais** deixa de usar o fallback `SEF_MG_ST` em operações com destino diferente de MG.
- Catálogo oficial passa a reconhecer as fontes RN usadas pelo motor: Lei RN nº 11.999/2024, Anexo 005 e Anexo 007 do RICMS/RN.
- O status `REGRA LOCAL` deixa de ser apresentado como ausente quando o próprio motor estadual já possui decisão estruturada, fundamento e modelo de cálculo oficiais para o contexto.

## Segurança
- Nenhuma alíquota, CEST, MVA, antecipação, FCP/FECOP ou responsabilidade tributária foi alterada.
- A cobertura RN da 17.8.58 e a visualização ampliada da 17.8.59 são preservadas integralmente.
- Hotfix sem banco de dados do usuário.

# FiscalPro 17.8.59 — Detalhes Técnicos Ampliados

- adiciona o botão **⛶ Ampliar detalhes** na Ficha Inteligente Simplificada;
- abre uma janela maximizada com a tabela completa de Campo / Resultado / Observação;
- inclui rolagem horizontal e vertical para não cortar observações extensas;
- amplia a área de Explicação e alertas;
- permite abrir a visualização ampla também com duplo clique na tabela ou na explicação;
- preserva integralmente a cobertura tributária do Rio Grande do Norte e todas as UFs anteriores da 17.8.58.

# FiscalPro 17.8.58 — Cobertura Estadual do Rio Grande do Norte

## Cobertura tributária RN
- Alíquota interna modal de 20% e FECOP separado: 0% para autopeças/pneumáticos do escopo estruturado; 2% apenas no rol legal do art. 27-A.
- Autopeças: o Anexo 005 do RICMS/RN é tratado como **antecipação tributária**, com percentual de agregação de 40%, sem confundir com ICMS-ST/MVA do remetente.
- A rota MG→RN não é marcada como retenção automática de autopeças, pois o RN não figura entre os destinos atuais do Protocolo ICMS 41/08.
- Pneumáticos: ICMS-ST pelo Anexo 007/Convênio 102/17, com tabela atualizada para alíquota interna de 20%; CEST 16.003.00 usa MVA 60% / 86% na entrada interestadual a 7%.
- Ficha Inteligente ganhou exibição específica de **Antecipação / percentual de agregação**, evitando chamar o percentual de 40% de MVA.
- Configurador Olist continua usando o mesmo `ICMSUFService` e agora expõe o campo de antecipação, sem tabela RN paralela.

## Validação
- 9 testes específicos do RN aprovados.
- Suíte completa: 461 testes aprovados, 0 falhas.
- `python -m compileall -q main.py src tests`: aprovado.
- Hotfix sem arquivos `.db`.

# FiscalPro 17.8.57 — Correção do rótulo da rota interestadual na Ficha

- corrige a aba **Detalhes técnicos** para exibir a rota exatamente conforme as UFs selecionadas na própria tela;
- elimina a possibilidade de um rótulo herdado da consulta anterior (ex.: mostrar `MG→PE` durante uma análise `MG→PB`);
- mantém todos os valores tributários da cobertura PB 17.8.56 sem alteração: ICMS, ICMS-ST, CEST, MVA e FUNCEP permanecem os mesmos;
- inclui teste de regressão específico para garantir que o texto `ICMS interestadual origem→destino` seja montado pelas UFs atuais da Ficha;
- nenhuma base `.db` faz parte da hotfix.

# FiscalPro 17.8.56 — Cobertura Estadual da Paraíba

- adiciona a Paraíba à cobertura estadual estruturada, com alíquota modal interna de 20% desde 01/01/2024;
- FUNCEP/PB fica separado do ICMS: 0% para autopeças e pneumáticos desta cobertura, mantendo revisão do rol taxativo de 2% da Lei nº 7.611/2004 para os demais produtos;
- autopeças do Anexo 05: MVA original de 36,56% na hipótese qualificada de fidelidade e 71,78% nos demais casos, com margens oficiais interestaduais para 4%, 7% e 12%;
- na rota MG→PB a 7%, usa 58,75% na hipótese qualificada ou 99,69% nos demais casos;
- para o CEST 01.076.00, reconhece a responsabilidade do remetente na rota MG→PB pelo Protocolo ICMS 41/08, ressalvadas as exceções do próprio acordo;
- pneumáticos do Anexo 05: CEST 16.003.00 / NCM 4011.40.00 com MVA original de 60% e MVA oficial de 86% na operação interestadual a 7%, sob Convênio ICMS 102/17;
- o Configurador Olist continua consumindo o mesmo `ICMSUFService`, sem tabela paralela por UF;
- mapa nacional atualizado para 1 UF ampliada, 16 parciais e 10 em regra geral;
- nenhuma base `.db` faz parte da hotfix.

# FiscalPro 17.8.55 — Cobertura Estadual de Alagoas

- adiciona Alagoas à cobertura estadual estruturada, com alíquota modal interna de 20,5% vigente desde 01/04/2026;
- FECOEP/AL fica separado do ICMS e aplica 1% ao escopo automotivo estruturado, inclusive na apuração da ST, sem confundir o adicional com a alíquota interna;
- autopeças do Anexo I do Decreto AL nº 90.309/2023: MVA original de 36,56% nas hipóteses qualificadas de fidelidade/exclusividade e 71,78% nos demais casos;
- na rota MG→AL a 7%, calcula MVA ajustada de 59,75% (fidelidade qualificada) ou 100,95% (demais casos);
- para o CEST 01.076.00, reconhece a responsabilidade do remetente na rota MG→AL pelo Protocolo ICMS 41/08, preservando as exceções de CEST e os requisitos de uso automotivo;
- pneumáticos do Anexo XI: CEST 16.003.00 / NCM 4011.40.00 com MVA original 60% e MVA ajustada 87,17% na rota MG→AL a 7%, sob Convênio ICMS 102/17;
- mantém alerta para eventual regime especial/credenciamento do destinatário, sem substituir a regra padrão sem evidência;
- o Configurador Olist continua consumindo o mesmo `ICMSUFService`, sem tabela paralela por UF;
- mapa nacional atualizado para 1 UF ampliada, 15 parciais e 11 em regra geral;
- nenhuma base `.db` faz parte da hotfix.

# FiscalPro 17.8.54 — Cobertura Estadual de Pernambuco

- adiciona Pernambuco à cobertura estadual estruturada, com alíquota modal interna de 20,5%;
- FECEP/PE fica separado do ICMS: 0% para autopeças e pneumáticos desta cobertura, mantendo revisão para o rol legal específico;
- autopeças: MVA original de 36,56% nas hipóteses qualificadas de fidelidade/exclusividade e 71,78% nos demais casos; tabela interestadual oficial de PE para 4%, 7% e 12%;
- na rota MG→PE, preserva a MVA oficial de 100,95% para os demais casos, mas NÃO atribui retenção ST automática ao remetente mineiro, pois MG não integra o Protocolo ICMS 97/10; a responsabilidade/antecipação fica indicada para revisão;
- pneumáticos: tabela oficial de PE a partir de 01/01/2024; para o CEST 16.003.00, MVA original 60% e MVA interestadual de 87,17% na operação a 7%;
- Convênio ICMS 102/17 é respeitado na responsabilidade interestadual dos pneumáticos, inclusive suas exceções de CEST;
- a Ficha Inteligente passa a mostrar **REVISAR • MVA** quando a MVA está conhecida, mas a responsabilidade do remetente ainda não está confirmada;
- o Configurador Olist continua consumindo o mesmo `ICMSUFService`, sem tabela paralela por UF;
- nenhuma base `.db` faz parte da hotfix.

# FiscalPro 17.8.53 — Cobertura Estadual do Ceará

- adiciona o Ceará à cobertura estadual com alíquota modal de 20%;
- trata autopeças do Decreto CE nº 30.519/2011 pelo modelo de **carga líquida**, sem convertê-la em MVA;
- na rota MG→CE, sinaliza carga líquida de referência de 21,00% para mercadoria de carga interna de 20%, condicionada ao CNAE principal do destinatário e às demais condições legais;
- registra que o Protocolo ICMS 41/08 não inclui o Ceará como destino na cláusula vigente;
- para pneumáticos, preserva o Convênio ICMS 102/17 e exige revisão da bifurcação carga líquida × regime específico quando houver redução de base, conforme Nota Explicativa SEFAZ/CE nº 03/2022;
- FECOP/CE fica 0% para autopeças e pneumáticos estruturados; outros produtos permanecem em revisão do rol do art. 47 do RICMS/CE;
- Ficha Inteligente e Configurador Olist passam a exibir **Modelo de cálculo ST** e **Carga líquida ST / entrada**, mantendo uma única fonte tributária;
- nenhuma base `.db` faz parte da hotfix.

# FiscalPro 17.8.52 — Cobertura Estadual do Distrito Federal

- Adiciona o DF à cobertura estadual estruturada do motor de ICMS.
- Alíquota modal interna de 20%, com regra interestadual 7%/12%/4% preservada.
- FCP/DF de 2% somente para o rol da Lei 4.220/2008; autopeças e pneumáticos estruturados ficam em 0%.
- Autopeças: MVA-ST original de 71,78% nos demais casos e 36,56% nas hipóteses qualificadas de fidelidade/exclusividade; operações interestaduais usam a fórmula legal de MVA ajustada.
- Pneumáticos: MVAs originais de 42%, 32%, 60% e 45%, conforme a Portaria 189/1997 alterada pela Portaria 173/2011, com ajuste interestadual.
- Mantém o Configurador Olist como consumidor do mesmo motor tributário, sem criar tabela paralela de alíquotas, e restaura seu acesso pela Central Tributária.
- Isola a suíte de testes da cópia histórica FiscalPro/FiscalPro por pytest.ini, sem apagar arquivos do usuário.

# FiscalPro 17.8.51 — Sincronização da Ficha com a Cobertura Estadual

- Mantém a base cumulativa de cobertura estadual até Mato Grosso da 17.8.50.
- Corrige a aba **Detalhes técnicos** para usar a UF de destino em vez de reaproveitar referências de MG.
- Separa a alíquota interestadual da operação da alíquota interna da UF de destino.
- Exibe MVA-base, MVA aplicada, tipo/condição da MVA e FCP da UF quando disponíveis.
- Em MT, mantém 87141000 em 50,39% / 65,29% e 40114000 em 62,27% / 78,79%, com alerta de benefício/situação do destinatário.
- Não altera bancos de dados nem rotinas financeiras.

# FiscalPro 17.8.50 — Cobertura Estadual de Mato Grosso

- Adiciona MT ao motor estadual de ICMS e ao Mapa de Cobertura Tributária Nacional.
- Alíquota modal de referência: 17% (Lei MT nº 7.098/1998 / RICMS-MT).
- Autopeças: ST estruturada pelo Anexo X e Portaria SEFAZ/MT nº 195/2019.
  - tabela-base: MVA 50,39%;
  - destinatário sem benefício informado do art. 2º-B: MVA 65,29%.
- Pneumáticos: segmento 16 estruturado.
  - tabela-base: MVA 62,27%;
  - destinatário sem benefício informado do art. 2º-B: MVA 78,79%.
- O art. 3º da Portaria 195/2019 é respeitado: as MVAs são aplicadas independentemente da UF do remetente; o FiscalPro não inventa MVA ajustada interestadual para MT.
- FCP/MT: 0% confirmado para autopeças e pneumáticos estruturados; demais hipóteses permanecem conservadoras para revisão do rol legal.
- Preserva as coberturas estaduais já aprovadas e os atalhos Enter da 17.8.48.
- Nenhum banco de dados faz parte da hotfix.
