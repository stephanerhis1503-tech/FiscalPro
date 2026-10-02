"""Metadados centrais do FiscalPro.

Versão 18.2.25 — Consulta NF-e por chave sem disputar o ultNSU:
- adiciona consulta pontual consChNFe pela chave de 44 dígitos no Ambiente Nacional;
- a consulta por chave não altera o ultimo_nsu/max_nsu local da Distribuição DF-e;
- quando a SEFAZ devolve XML completo, o FiscalPro salva a NF-e no banco e grava o XML automaticamente na pasta escolhida;
- quando retorna apenas resumo, a NF-e entra na grade e pode ser manifestada; depois a mesma chave pode ser consultada novamente;
- mantém a sincronização por NSU apenas como modo avançado, com aviso explícito para não usar junto com Digisat/outro distribuidor;
- mesmo durante a proteção de cStat 656 do distNSU, a consulta pontual por chave permanece disponível na interface.

Versão 18.2.24 — Detalhe do documento DF-e + grade ampliada:
- o diagnóstico identifica cada documento retornado com NSU, tipo, disponibilidade, schema, chave e emitente quando disponíveis;
- consultas antigas sem esse detalhe são reconstruídas pelo intervalo de NSU já armazenado localmente, sem nova chamada à SEFAZ;
- eventos e resumos passam a ficar visíveis no diagnóstico mesmo quando não geram uma terceira linha na grade de NF-e;
- aumenta a área da tabela de NF-e e reduz proporcionalmente a prévia do XML para facilitar a conferência das notas;
- preserva o rastro de NSU, a proteção contra cStat 656 e a lógica de manifestação da 18.2.23.

Versão 18.2.23 — Rastro da Distribuição DF-e / diagnóstico cStat 656:
- registra localmente cada chamada feita pelo FiscalPro com horário, NSU enviado, cStat, ultNSU/maxNSU retornados e quantidade de documentos;
- preserva o último maxNSU válido quando uma rejeição 656 omite ou devolve maxNSU zerado;
- o diagnóstico passa a comparar o NSU enviado pelo FiscalPro com o ultNSU informado pela SEFAZ;
- quando os NSUs divergem em um 656, sinaliza indício de sequência concorrente sem afirmar qual programa realizou a outra consulta;
- mostra as últimas chamadas do próprio FiscalPro para separar chamada interna de avanço externo;
- mantém a proteção de 1 hora e o encerramento imediato quando a fila chega ao fim.

Versão 18.2.22 — Motor Semântico Nacional de NCM:
- confronta todo NCM preenchido com o catálogo NCM/TIPI oficial instalado;
- procura candidatos em toda a nomenclatura, sem tabela fixa peça→NCM;
- usa equivalências de linguagem comercial apenas para aproximar descrições, nunca para definir NCM diretamente;
- NCM duvidoso bloqueia correções tributárias derivadas até revisão;
- candidatos fortes recalculam a tributação somente de forma provisória e permanecem REVISAR.

Versão 18.2.21 — Progresso confiável na Auditoria Excel:
- corrige o contador quando o XLSX informa dimensão/max_row incorreta;
- a porcentagem usa a quantidade real de itens encontrados na planilha;
- a leitura de formatação percentual também deixa de depender do max_row.

Versão 18.2.20 — Cadastro PF, exclusão segura e bloqueio de duplicidade:
- o Cadastro Central passa a aceitar Pessoa Jurídica (CNPJ) e Pessoa Física (CPF);
- pessoas físicas ficam disponíveis no Contas a Pagar, sem entrar nos módulos fiscais, NF-e/NFS-e ou Controle de Entregas;
- adiciona botão Excluir para remover cadastros duplicados/manuais sem histórico de entregas;
- protege empresas-base e cadastros com entregas históricas contra exclusão acidental;
- bloqueia novos cadastros com CPF/CNPJ já existente e também nomes equivalentes por caixa/acentuação;
- a grade passa a exibir Tipo e CPF/CNPJ e permite pesquisar pelo documento.

Versão 18.2.19 — DIFAL / memória de cálculo por C190/CST:
- acrescenta memória de cálculo rastreável no DIFAL automático sem alterar a lógica principal aprovada na 18.2.16;
- detalha cada segmento C190 com CST, origem, CFOP, base, alíquota interna, alíquota interestadual do cenário, diferença e fórmula;
- mantém o DIFAL devido principal como está e apresenta a memória SPED/CST como cenário de conferência;
- notas com origens mistas são demonstradas segmento a segmento e consolidadas no total da NF-e;
- adiciona a coluna “Memória cálculo SPED/CST” na tela;
- adiciona a aba “Memória de Cálculo” no Excel, com linhas de segmento e uma linha TOTAL NF por documento;
- preserva confronto XML × SPED/CST, C101, CFOP 6.102/CPF, cálculo quando o XML não informa DIFAL e FCP conservador.

Versão 18.2.18 — Cadastro Central de Empresas:
- cria a aba “Empresas” no menu principal do FiscalPro;
- transforma o cadastro persistente de empresas na fonte única de nome, CNPJ, regime e situação;
- propaga novas empresas para Tributação, Controle de Entregas e Contas a Pagar;
- NF-e/NFS-e passam a usar as empresas do cadastro central, mantendo certificado A1, NSU e documentos no módulo fiscal;
- migra de forma conservadora CNPJs já existentes nos cadastros antigos de NFS-e/Financeiro;
- preserva históricos e documentos: nenhuma sincronização apaga notas, NSU, contas ou entregas;
- corrige a precedência do regime das empresas-base para que alterações salvas no banco prevaleçam sobre os defaults em código.

Versão 18.2.17 — cadastro de empresas no Controle de Entregas:
- adiciona os botões “+ Nova empresa” e “Editar empresa” na configuração do Controle de Entregas;
- cadastra nome/razão social, CNPJ e regime tributário diretamente pelo FiscalPro;
- cria automaticamente a grade padrão de obrigações da nova empresa;
- preserva empresas cadastradas manualmente nas próximas inicializações, sem desativá-las pelo cadastro-base;
- disponibiliza as empresas ativas também nas listas dos módulos tributários e resolve o regime salvo no banco;
- protege o nome das seis empresas-base já confirmadas, permitindo editar CNPJ e regime sem duplicá-las.

Versão 18.2.16 — DIFAL: auditoria de origem/CST SPED × XML:
- compara pICMSInter do XML com a alíquota interestadual sugerida pela origem do CST no C190;
- divergências são marcadas como REVISAR ORIGEM, sem substituir silenciosamente XML ou SPED;
- mostra lado a lado Alíq. inter. XML, Alíq. inter. SPED/CST e o cenário de DIFAL calculado pela origem do SPED;
- quando houver origens/CST diferentes na mesma NF-e, calcula por segmento C190 e soma os valores;
- a exportação Excel passa a levar as duas alíquotas, o cenário SPED/CST e o detalhamento das origens;
- preserva cálculo de XML sem DIFAL, CFOP 6.102/CPF, alíquotas internas por data e proteção conservadora do FCP.

Versão 18.2.15 — XML sem DIFAL: cálculo automático pelo FiscalPro:
- quando a NF-e existe, mas o XML não informa vICMSUFDest/DIFAL, o FiscalPro calcula o valor devido em vez de aceitar zero;
- se o XML tiver base e alíquota interestadual, usa esses dados com a alíquota interna vigente da UF/data;
- se o XML não tiver memória suficiente, reconstrói a base/alíquota pelo C190/C100 do SPED;
- compara o DIFAL calculado contra o C101 e sinaliza divergência, ausência de C101 ou coincidência;
- preserva CFOP 6.102 para revisão sem bloquear o cálculo, Exportar Excel e as alíquotas vigentes da 18.2.14.

Versão 18.2.14 — DIFAL: CPF/consumidor final não bloqueado por CFOP 6.102:
- quando o XML confirma operação interestadual, consumidor final e não contribuinte (idDest=2, indFinal=1, indIEDest=9), o CFOP 6.102 não bloqueia mais o cálculo do DIFAL;
- se o XML não trouxer ICMSUFDest, o FiscalPro reconstrói o cálculo pela base/ICMS do C190 ou, em contingência, pelo valor do C100;
- a alíquota interna vigente por UF/data continua sendo usada no cálculo devido;
- CFOP 6.102 fica marcado para revisão separada, sem zerar o imposto calculado;
- sem XML, destinatário CPF sem IE também passa a ser candidato ao cálculo estimado mesmo com CFOP 6.102;
- FCP sem regra específica continua marcado para revisão, sem valor presumido indevidamente;
- preserva Exportar Excel e as correções de alíquotas das versões 18.2.12/18.2.13.

Versão 18.2.13 — DIFAL: alíquota interna devida × XML:
- corrige a auditoria com XML para usar na grade a alíquota modal vigente da UF na data da NF-e, em vez de repetir cegamente o pICMSUFDest do XML;
- Bahia: 20,5% desde 07/02/2024, preservando 19% de 22/03/2023 a 06/02/2024 e o histórico anterior;
- quando o XML trouxer alíquota diferente da modal vigente, mantém o valor original em evidência, recalcula o DIFAL devido pela alíquota modal e sinaliza REVISAR;
- a coluna passa a se chamar “Alíq. interna devida”;
- preserva Exportar Excel, cálculo sem XML e todas as demais funções da 18.2.12.

Versão 18.2.12 — DIFAL automático: Excel + cálculo sem XML + alíquotas 2026:
- adiciona Exportar Excel no módulo DIFAL automático, com abas Resumo, Detalhes DIFAL e Sem XML;
- quando o XML não estiver disponível, reconstrói um cálculo estimado do DIFAL usando C190/C100 e a alíquota modal vigente na data da NF-e;
- separa na tela e no Excel a origem do cálculo (XML autorizado ou SPED estimado), o DIFAL devido e a diferença contra o C101;
- atualiza a tabela modal de 2026: AL 20,5% desde 01/04/2026, MA 23% desde 23/02/2025 e RN 20% desde 20/03/2025, preservando o histórico por data;
- FCP/FECOP sem XML não é presumido quando depende do produto; AL 2026 usa referência geral de 1% e os demais casos ficam sinalizados para revisão;
- nenhuma correção é aplicada automaticamente ao SPED.

Versão 18.2.11 — layout estável da grade + XML:
- substitui o divisor móvel que espremia a tela em resoluções menores;
- mantém a lista de NF-e sempre visível na parte superior;
- mantém a caixa de XML sempre visível na parte inferior;
- compacta os botões de manifestação/download para liberar espaço vertical;
- preserva sincronização, NFS-e e controle de NSU/cStat 656.

Versão 18.2.10 — tela dividida com caixa de XML abaixo:
- divide verticalmente a área da Manifestação NF-e em duas partes;
- mantém a grade de NF-e na parte superior;
- adiciona uma caixa de XML na parte inferior para visualizar o XML completo da nota selecionada;
- quando houver apenas resumo, informa isso na caixa inferior;
- preserva integralmente o download manual local de XML e a proteção de NSU/cStat 656.

Versão 18.2.9 — botões de Manifestação/XML sempre visíveis:
- move as ações de manifestação e download de XML para cima da grade de NF-e;
- evita que o rodapé fique oculto pela tabela expansível em telas de menor altura;
- preserva integralmente o download local de XML da 18.2.8 e a proteção de NSU/cStat 656 da 18.2.7.

Versão 18.2.8 — download manual de XMLs na Manifestação NF-e:
- adiciona seleção múltipla de NF-e para baixar XMLs completos já armazenados localmente;
- permite escolher a pasta base e organiza os arquivos por Empresa / Ano / Mês;
- adiciona botão para baixar todos os XMLs completos atualmente exibidos na grade;
- o download é exclusivamente local: não consulta a SEFAZ, não usa NSU e não pode provocar cStat 656;
- NF-e disponíveis apenas como resumo são ignoradas e informadas ao usuário;
- preserva integralmente a NFS-e Nacional e as proteções de NSU/cStat 656 da 18.2.7.

Versão 18.2.7 — proteção cStat 656 / NSU na Manifestação NF-e:
- grava o ultNSU devolvido pela SEFAZ quando a Distribuição DF-e retorna cStat 656;
- mantém o controle de NSU separado por CNPJ e ambiente;
- bloqueia novas consultas por 1 hora após cStat 656, cStat 137 ou chegada ao maxNSU;
- mostra na tela o horário exato de liberação e impede cliques que reiniciariam a contagem;
- migra automaticamente o banco da Manifestação sem alterar a NFS-e ou os demais módulos.

Versão 18.2.6 — auditoria IBS/CBS encontrada × esperada:
- adiciona a aba Auditoria IBS/CBS dentro do leitor de XML;
- compara CST, cClassTrib, alíquotas e valores encontrados no XML com a regra geral determinística de 2026;
- para CRT 3 + CST 000 + cClassTrib 000001 em 2026, confere pIBSUF 0,1%, pIBSMun 0% e pCBS 0,9%;
- recalcula IBS UF, IBS Município, IBS total e CBS a partir da base informada e aponta divergências;
- confere coerência básica CST × cClassTrib e itens sem grupo IBSCBS;
- operações especiais, Simples/MEI e classificações específicas não recebem conclusão automática: ficam como REGRA ESPECIAL/REVISAR;
- exporta uma nova planilha Auditoria_IBS_CBS sem alterar XMLs, SPED ou banco de dados.

Versão 18.2.5 — correção de abertura do leitor IBS/CBS em XML:
- corrige erro Tkinter "bad screen distance '0 8'" na criação do painel.

Versão 18.2.4 — leitor IBS/CBS em XML:
- adiciona a subaba IBS/CBS • XML dentro da central NF-e / NFS-e;
- lê XMLs avulsos, ZIPs e pastas sem alterar os documentos;
- identifica os blocos IBSCBS e IBSCBSTot e lista todas as tags folha com caminho completo e valor;
- resume por item CST IBS/CBS, cClassTrib, base, alíquotas e valores de IBS UF, IBS Município e CBS;
- confere soma dos itens contra os totais IBS/CBS do XML e sinaliza divergências;
- exporta Resumo_XML, Itens_IBS_CBS e Todas_Tags_IBS_CBS para Excel;
- preserva a DeRE 18.2.3 e os demais módulos.

Versão 18.2.3 — DeRE / fluxo ampliado:
- amplia o pré-validador para D-1001 (Informações do Contribuinte), D-1106 (Aplicações Financeiras) e D-1199 (Fechamento Mensal);
- mantém D-1011 e D-1101 com os novos limites de Produção Restrita;
- monitora até 100 infoAplic no D-1106 e até 500 detAtivo por infoAplic;
- reconhece D-1199 v0.0.2 e valida pelo XSD quando o pacote completo v1.2.0 estiver selecionado;
- quando o usuário usa o ZIP piloto, informa que esse pacote não contém o XSD do D-1199 em vez de acusar erro falso;
- generaliza a grade DeRE para mostrar grupo, quantidade e limite conforme cada evento.

Versão 18.2.2 — DeRE / XSD oficial:
- corrige a validação do pacote oficial de Produção Restrita, que referencia xmldsig-core-schema.xsd sem incluir esse arquivo no ZIP;
- valida estruturalmente D-1011 e D-1101 contra os XSDs oficiais sem alterar o pacote baixado pelo usuário;
- deixa explícito que o pré-validador não verifica criptograficamente a assinatura digital;
- mantém os limites de 150.000 infoConta no D-1011 v1.0.3 e 90.000 no D-1101 v1.0.1.

Versão 18.2.1 — DeRE / pré-validação local:
- adiciona aba DeRE sem remover ou alterar a central NF-e / NFS-e da versão 18.2.0;
- identifica e pré-valida D-1011 (PGCC) e D-1101 (Balancete Mensal);
- aplica os limites vigentes na Produção Restrita desde 22/09/2026: 150.000 grupos infoConta no D-1011 v1.0.3 e 90.000 no D-1101 v1.0.1;
- permite validar XML contra pasta ou ZIP de XSDs oficiais quando lxml estiver disponível;
- exporta relatório técnico para Excel;
- não transmite declarações e não altera SPED, NF-e/NFS-e, ICMS-ST, Financeiro nem bases operacionais.


Versão 18.2.0 — NF-e / NFS-e e Manifestação do Destinatário:
- preserva integralmente a tela e o fluxo existentes da NFS-e Nacional;
- renomeia a central para NF-e / NFS-e e adiciona subaba própria para NF-e;
- consulta NF-e destinadas via Distribuição DF-e do Ambiente Nacional com controle incremental de NSU;
- registra Ciência, Confirmação, Desconhecimento e Operação não Realizada com certificado A1 e assinatura XML;
- mantém senha do certificado somente em memória, registra protocolos/retornos e permite salvar XML completo quando disponível;
- aplica o prazo conclusivo de 90 dias vigente desde 01/06/2026 e isola os dados da NF-e em banco próprio.




Versão 18.1.11 — serviços separados da auditoria de mercadorias:
- identifica linhas de serviço/mão de obra com NCM zerado e evita sugerir o NCM da peça citada na descrição;
- adiciona o status SERVIÇO, filtro próprio e contador separado na Auditoria por Excel;
- linhas de serviço deixam de entrar em “Exportar pendências” e aparecem na Ficha Tributária com campos de mercadoria como N/A;
- exclui serviços do índice de aprendizado de NCM para não contaminar futuras sugestões;
- reconhece GASOLINA como NCM 27101259, mantendo o CEST em revisão quando a descrição não informa tipo A/C/Premium;
- no arquivo real analisado, os 98 itens antes sem qualquer evidência se dividem em 96 serviços e 2 linhas de gasolina.

Versão 18.1.10 — candidatos de NCM para descrições ambíguas:
- mantém a inferência automática somente quando existe evidência suficiente para um único NCM;
- quando o NCM está zerado e a descrição é ambígua, mostra até 3 candidatos com confiança e quantidade de referências do próprio cadastro;
- famílias como capa, cabo, lâmpada, rolamento, junta, mangueira, lanterna e painel recebem alternativas para revisão sem alimentar automaticamente o motor tributário;
- acrescenta a coluna “NCM candidatos” na tela, no relatório da auditoria e na Ficha Tributária Completa;
- na base de teste de 40.848 produtos, 3.178 dos 3.489 NCMs zerados passam a ter uma sugestão única ou candidatos de revisão, restando 311 sem evidência suficiente;
- preserva todas as proteções, velocidade e regras tributárias das versões anteriores.

Versão 18.1.9 — NCM semântico por função e consenso conservador:
- antes de copiar NCM de descrições parecidas, aplica regras de alta confiança baseadas na função explícita da peça (motor de partida, escova de arranque, filtros, pistão, válvulas, CDI, regulador, bomba, buzina, corrente de transmissão etc.);
- trata lâmpadas pela tecnologia/tensão quando a descrição traz evidência suficiente, evitando classificar toda lâmpada como acessório genérico de motocicleta;
- cria consenso hierárquico por família/marca apenas quando o próprio cadastro apresenta concordância muito forte;
- bloqueia inferência aproximada em famílias ambíguas (capa, cabo, lâmpada, rolamento, mangueira, painel etc.) quando material/tecnologia/função podem mudar o NCM;
- mantém toda classificação inferida como REVISAR, sem sobrescrever o NCM original ou transformar sugestão em classificação legal definitiva;
- preserva a velocidade e todas as melhorias das versões 18.1.3 a 18.1.8.

Versão 18.1.8 — NCM zerado com sugestão por descrição:
- quando o NCM está vazio/00000000, aprende candidatos a partir de itens já classificados no próprio cadastro;
- prioriza mesmo código/EAN, descrição idêntica, família comercial e variantes semelhantes da mesma marca;
- descarta famílias ambíguas em que o próprio cadastro aponta para mais de um NCM;
- usa o NCM candidato apenas para simular provisoriamente CEST, ICMS-ST, PIS/COFINS e IPI, mantendo o item como REVISAR até validação humana;
- preserva NCM atual zerado na ficha e mostra NCM sugerido, referência usada, método e confiança da inferência;
- mantém a velocidade da auditoria com índice montado uma única vez por planilha.

Versão 18.1.7 — coerência final da Ficha Tributária:
- impede Status OK quando CST ICMS, CFOP ou ICMS desonerado ainda estiverem marcados como REVISAR;
- transforma essas pendências operacionais em REVISAR com motivo explícito, sem promover divergência objetiva para CORRIGIR;
- Natureza da Receita pendente em CST PIS/COFINS não padrão também passa a impedir Status OK;
- CST IPI deixa de aparecer como REVISAR em massa quando a condição industrial/equiparada não é conhecida: o campo fica em branco e a limitação vai para a Observação FiscalPro;
- preserva a velocidade da 18.1.5 e as regras de status inteligente da 18.1.6.

Versão 18.1.6 — Ficha Tributária Completa com status inteligente:
- separa divergências objetivas de alertas genéricos do motor, evitando transformar toda a base em REVISAR;
- mantém alertas de cautela na Observação FiscalPro sem rebaixar, sozinhos, o status do item;
- preenche CST ICMS, CFOP e ICMS desonerado quando o contexto de venda/revenda permite conclusão segura;
- quando CST IPI ou Natureza da Receita dependem de premissa ausente, grava REVISAR no campo em vez de inventar código;
- preserva a velocidade restaurada na 18.1.5 e toda a Ficha Tributária Completa.

Versão 18.1.5 — desempenho restaurado na Auditoria por Excel:
- volta a usar leitura rápida do openpyxl (values_only=True) durante a auditoria;
- detecta o formato percentual de cada coluna apenas uma vez, em vez de carregar estilos de todas as células;
- preserva a Ficha Tributária Completa da 18.1.3 e os aliases ampliados da 18.1.4;
- reduz a frequência de atualizações de progresso em cadastros grandes, mantendo a interface responsiva.

Versão 18.1.4 — correção de reconhecimento das planilhas de auditoria:
- volta a reconhecer a própria planilha exportada pelo FiscalPro, inclusive a coluna “NCM atual”;
- amplia aliases para Código/Cód. Produto, Descrição e NCM/Cód. NCM/NCM cadastrado sem exigir cabeçalhos idênticos;
- mantém a Ficha Tributária Completa da 18.1.3 e não altera o motor tributário.

Versão 18.1.3 — Ficha Tributária Completa na Auditoria Excel:
- mantém a auditoria atual e acrescenta uma exportação separada no formato de ficha tributária;
- reproduz as 22 colunas do modelo fornecido e adiciona status, referências, divergências, fundamentos e fontes;
- lê percentuais formatados do Excel corretamente (ex.: 18%, 0,65% e 3%) sem confundir fração com ponto percentual;
- preserva campos não determinísticos, como CST/CFOP/benefícios, e sinaliza REVISAR em vez de corrigir silenciosamente;
- não altera planilha original, SPED, Contas a Pagar, NFS-e ou motores tributários.

Versão 18.1.2 — correção da sincronização inicial NFS-e/ADN:
- inicia a primeira consulta do contribuinte pelo NSU 1, compatível com o endpoint atual de distribuição;
- trata HTTP 404 “Nenhum documento localizado” como caixa postal vazia/fim da fila, sem apresentar falso erro de certificado;
- mantém a conexão mTLS, filtro por CNPJ e sincronização incremental por NSU.

Versão 18.1.1 — ajuste responsivo da tela NFS-e Nacional:
- adiciona rolagem vertical ao painel de empresa/certificado para manter Salvar, Validar, Testar conexão e Sincronizar visíveis em telas de 768 px ou com escala do Windows;
- preserva integralmente a integração ADN introduzida na 18.1.0.

Versão 18.1.0 — NFS-e Nacional integrada ao FiscalPro:
- adiciona a aba NFS-e Nacional com cadastro de múltiplas empresas e certificado digital A1;
- consulta oficial do ADN por NSU, com autenticação mTLS e suporte a CNPJ da mesma raiz quando aceito pelo serviço;
- mantém a senha do certificado apenas em memória, sem gravá-la no banco;
- sincroniza documentos emitidos, recebidos e eventos e guarda o último NSU por empresa;
- permite filtrar por período/direção, pesquisar e exportar Excel consolidado ou XMLs em lote;
- usa banco próprio em dados/nfse/nfse_nacional.db, sem alterar os bancos do SPED, Financeiro ou Entregas.


Versão 17.8.130 — acesso direto à calculadora ICMS-ST/MVA:
- corrige o botão ICMS-ST / MVA da Central Tributária, que chamava a janela sem os parâmetros obrigatórios;
- o acesso direto passa a abrir a calculadora em modo manual usando empresa/operação/UFs já selecionadas no painel;
- mantém intacto o cálculo aberto pela Ficha Tributária, que continua recebendo NCM, CEST, MVA e enquadramento oficial.

Versão 17.8.129 — janela de ajuste do XML responsiva:
- mantém os botões Salvar e recalcular/Cancelar sempre visíveis, inclusive com escala do Windows acima de 100%;
- adiciona rolagem somente ao formulário quando a altura útil da tela for pequena;
- adiciona Ctrl+S como atalho de salvamento sem alterar o motor tributário ou os cálculos de ICMS-ST.

Versão 17.8.128 — correção do cálculo ST/MG sem bloqueio global:
- restaura o cálculo automático dos itens que já eram calculados quando há CEST/MVA aplicáveis;
- mantém a correção contextual do NCM 7616.99.00 para não confundir autopeça com material de construção;
- quando o usuário confirma AUTOPEÇAS, abreviações da descrição não derrubam o cálculo do segmento Autopeças;
- continua bloqueando o residual de autopeças para consumíveis como cola, tinta, graxa e fluidos.

Versão 17.8.127 — motor ST/MG contextual por descrição, segmento e finalidade:
- corrige o caso NCM 7616.99.00 / TAMPA VÁLVULA BUTYL ALUM, impedindo que a regra de materiais de construção (CEST 10.073.00) prevaleça quando a descrição comprova acessório automotivo e não adere à descrição legal de construção;
- nesses conflitos, o motor passa a avaliar o residual de autopeças 01.999.00 antes de concluir o enquadramento;
- resultados ST condicionais deixam de calcular ICMS-ST automaticamente: CEST e MVA permanecem apenas como sugestão até NCM + descrição + segmento + decisão estarem confirmados;
- o XML → ICMS-ST não exibe mais “ST NÃO DESTACADO” quando a própria regra oficial está apenas condicional;
- o motor integrado de MG deixa de promover CEST + MVA candidatos para ST confirmada;
- amplia a leitura segura de abreviações FIACAO/FIOS e INTER sem perder os CEST específicos já validados;
- adiciona regressões automatizadas para tampa de válvula 7616.99.00, bloqueio de cálculo condicional e preservação do motor em lote.


Versão 17.8.126 — filtro de ar do motor: NCM/CEST/MVA por descrição material:
- impede que filtro completo de entrada de ar para motor cadastrado genericamente em 8421.99.99 caia no CEST 21.014.00 de eletrodomésticos;
- quando a descrição comprova FILTRO + AR + aplicação em motor/motocicleta, consulta o enquadramento específico 8421.31.00 / CEST 01.041.00;
- usa MVA original 71,78% e deixa a calculadora aplicar a fórmula legal de MVA ajustada conforme as alíquotas da operação;
- preserva o NCM original do XML/cadastro e apenas sinaliza a necessidade de revisão cadastral, sem alterar documento fiscal automaticamente.


Versão 17.8.125 — restauração portátil entre computadores:
- impede WinError 5 quando o backup veio de outro usuário do Windows;
- o backup de segurança anterior à restauração não tenta acessar a pasta de documentos do PC antigo;
- caminhos C:\\Users\\usuario_antigo são remapeados para o perfil Windows atual;
- após restaurar, migra pasta do robô de e-mail, pasta de scans e caminhos de anexos do Contas a Pagar;
- não altera valores financeiros nem o conteúdo fiscal dos bancos restaurados.

Versão 17.8.124 — Bloco M: fechamento PGE + devolução de compra:
- retotaliza M400/M410 e M800/M810 usando A170/C170/C175 suportados, inclusive NFC-e analítica;
- cria M205/M605 ausentes quando M200/M600 possuem valor a recolher e o 0110 comprova incidência exclusiva;
- corrige devolução de compra escriturada como saída com CST 70-75 para CST 49 quando CFOP e campos zerados tornam o caso determinístico;
- o Pré-PVA passa a apontar CST 70-75 em operações de saída e também M205/M605 ausentes;
- validado no TXT real SPED CONT 08-2026_CONVERTIDO5.txt, preservando créditos e corrigindo apenas os fechamentos determinísticos.

Versão 17.8.123 — C175: sincronização PIS/COFINS no Excel → TXT:
- corrige bases divergentes de PIS e COFINS no C175 quando um lado já traz a exclusão do ICMS e o outro permanece na base bruta;
- espelha a base corrigida somente em cenários comprováveis e recalcula o valor do tributo correspondente;
- preserva edições manuais divergentes dos dois lados em vez de escolher uma delas;
- mantém intactos C175 por quantidade e situações sem evidência suficiente;
- validado na planilha real SPED CONT 08-2026_ORGANIZADO.xlsx, eliminando as divergências VL_BC_PIS x VL_BC_COFINS sem alterar a planilha original.

Versão 17.8.122 — Conferência Excel automática após validação:
- preenche automaticamente a grade Original × Novo assim que a planilha é validada;
- elimina o segundo clique obrigatório em “Conferir alterações”;
- mostra no status a quantidade de campos alterados e de itens da conferência, incluindo ajustes automáticos;
- preserva integralmente as correções Excel → TXT da 17.8.121.

Versão 17.8.121 — Correção do sincronizador oficial ST/MG:
- corrige falso bloqueio da sincronização em linhas oficiais que usam NBM/SH amplo, como 08.13, 09.09 e “Capítulos 39, 42...”;
- diferencia regra realmente residual (coluna NBM/SH vazia) de regra com cobertura por capítulo/posição/subposição;
- indexa também capítulos de 2 dígitos e códigos NBM/SH parciais como prefixos pesquisáveis;
- expande intervalos oficiais como “Capítulos 13 e 15 a 23” sem tratá-los como CEST residual desconhecido;
- sobe o selo da base ST/MG para schema 3, impedindo que uma base 17.8.119 incompleta seja considerada COMPLETA antes de nova sincronização;
- preserva as regras residuais reais 01.999.00 e 28.999.00;
- não altera Contas a Pagar, SPED, empresas ou dados financeiros.

Versão 17.8.119 — Motor ST/MG com base oficial completa da SEF/MG:
- substitui o remendo por NCM individual por uma cópia local sincronizável da Parte 2 do Anexo VII do RICMS/MG;
- baixa somente as páginas 4/7, 5/7 e 6/7, onde está a Parte 2, sem misturar Parte 1 ou Parte 3;
- armazena NCM/NBM-SH, CEST, descrição, âmbito e MVA/regra textual dos segmentos publicados;
- só conclui “NÃO ST/MG por ausência nominal” quando a sincronização completa recebeu selo de integridade; base parcial continua conservadora;
- avalia antes as regras sem NCM fechado, especialmente o residual CEST 01.999.00 de autopeças;
- preserva linhas com PMPF, preço fixado ou cálculo textual para não perder o enquadramento apenas porque não há MVA numérica;
- adiciona na Ficha e no Motor ICMS/MG o comando de sincronização da tabela oficial e exibe data/status da base;
- migração do banco é automática e não apaga dados existentes.

Versão 17.8.118 — Ficha Tributária: NCM 6110/coletes sem falso ST condicional:
- confirma como NÃO ST/MG a posição 6110, após conferência nominal na Parte 2 vigente do Anexo VII;
- corrige o caso NCM 61103000 (colete), que estava caindo no fallback genérico CONDICIONAL mesmo sem enquadramento ST/MG;
- transforma a lista de posições conferidas fora da ST em mapa extensível, preservando 3506 e adicionando 6110;
- mantém conservador o restante: NCM sem cobertura técnica continua CONDICIONAL até conferência na fonte oficial;
- não altera banco de dados, Financeiro, SPED ou a busca por descrição da 17.8.117.

Versão 17.8.117 — Ficha Inteligente: busca real de NCM por descrição:
- a pesquisa por descrição passa a usar a mesma base nacional NCM/TIPI do Catálogo Nacional, em vez de consultar apenas as tabelas antigas da Ficha;
- normaliza acentos e linguagem digitada, preservando buscas como “abraçadeira” e “abracadeira”;
- combina catálogo oficial, descrições locais da empresa e uma camada controlada de termos comerciais que não aparecem literalmente na nomenclatura;
- termos ambíguos não escolhem NCM sozinhos: “abraçadeira” mostra candidatos conforme material, e descrições como “abraçadeira plástica”/“abraçadeira inox” refinam a sugestão;
- mantém a descrição real digitada para a análise tributária posterior e não altera banco de dados.

Versão 17.8.116 — Ficha Tributária: cola NCM 3506 sem falso ST condicional:
- confirma como NÃO ST/MG, na regra geral do Anexo VII, a posição 3506 (colas e outros adesivos preparados), que não consta na Parte 2 vigente conferida em 10/09/2026;
- remove CEST e MVA sugeridos/antigos quando a decisão legal for NÃO;
- diferencia "NCM não encontrado na cobertura local" de "NCM conferido e fora da Parte 2", preservando o modo condicional para códigos ainda sem cobertura suficiente;
- ajusta a Ficha para exibir "NÃO — sem enquadramento ST/MG" em vez de "CONDICIONAL" no caso 35061090;
- mantém ressalva para eventual regime especial específico do contribuinte, sem transformar essa exceção em ST padrão.

Versão 17.8.115 — Ficha Tributária: trava de falso ICMS-ST por NCM isolado:
- exige aderência entre a descrição real do produto e a descrição legal antes de confirmar ST/MG;
- mantém como condicional o NCM localizado cuja descrição não foi comprovada;
- impede o CEST residual 01.999.00 de transformar cola, adesivo, tinta, graxa e outros consumíveis em autopeça apenas pela finalidade informada;
- preserva a descrição digitada na pesquisa da Ficha para a análise oficial, em vez de substituí-la pela descrição genérica do NCM;
- trata CEST/MVA de resultados condicionais apenas como sugestão e não como tributação confirmada;
- normaliza singular/plural na comparação para preservar casos válidos como PASTILHA DE FREIO.

Versão 17.8.114 — CNPJ por conta e múltiplos CNPJs por fornecedor:
- mostra o CNPJ do fornecedor diretamente no cadastro/edição da conta;
- permite cadastrar vários CNPJs para o mesmo fornecedor;
- quando existe um único CNPJ, preenche automaticamente; com vários, exige escolher o CNPJ correto da conta;
- grava o CNPJ na própria conta para o relatório mensal usar o estabelecimento correto;
- migra com segurança os CNPJs já cadastrados nas versões anteriores;
- mantém renomear/excluir fornecedores, Central da Contabilidade, downloads, anexos e relatórios anteriores.

Versão 17.8.113 — gerenciamento de fornecedores:
- adiciona Renomear fornecedor na Central da Contabilidade;
- sincroniza o novo nome com contas, fila financeira e Agenda de Faturas;
- recalcula chaves de duplicidade para preservar a conferência do Contas a Pagar;
- adiciona Excluir fornecedor: sem uso, remove o cadastro; com histórico, apenas oculta para não apagar lançamentos;
- permite unir cadastros ao renomear para um nome já existente quando não houver conflito de CNPJ;
- mantém CNPJ, relatórios, downloads, anexos, baixas e módulos fiscais das versões anteriores.

Versão 17.8.112 — Central da Contabilidade separada:
- remove as ferramentas contábeis extras das linhas de ações do Contas a Pagar;
- devolve espaço vertical para a grade de lançamentos;
- adiciona um único botão “Contabilidade” no painel operacional;
- abre uma central separada com Downloads de scans, Organizar scans, Pacote para Contabilidade, Pagas do mês e Fornecedores/CNPJ;
- mantém integralmente busca por Enter, CNPJ, relatório mensal, escolha de pasta e anexos das versões anteriores;
- não altera banco de dados, baixas, anexos existentes, SPED ou regras fiscais.

Versão 17.8.111 — busca de fornecedor pelo Enter:
- o campo Buscar em Fornecedores / CNPJ passa a responder ao Enter e ao Enter do teclado numérico;
- após a busca, seleciona o primeiro resultado automaticamente;
- quando houver um único fornecedor, leva o foco direto para o campo CNPJ;
- quando houver vários, deixa a lista pronta para navegação pelas setas;
- mantém download de scans, escolha de pasta, CNPJ e relatório mensal da 17.8.110.

Versão 17.8.110 — correção regressiva do download de scans:
- restaura o BaixadorDocumentosAdobe compatível com o parâmetro pasta_destino;
- mantém a escolha de pasta para os downloads do WhatsApp/Adobe da 17.8.107;
- preserva cadastro/CNPJ de fornecedores e relatório mensal da 17.8.109;
- não altera contas, baixas, anexos existentes, valores ou módulos fiscais.

Versão 17.8.109 — CNPJ de fornecedores no Financeiro e no relatório mensal:
- adiciona cadastro centralizado “Fornecedores / CNPJ” no Contas a Pagar;
- permite pesquisar fornecedor existente e salvar/alterar o CNPJ uma única vez;
- valida o CNPJ informado e preserva fornecedores antigos com CNPJ em branco até o cadastro;
- o relatório Pagas do mês passa a trazer Data de pagamento, Vencimento, Fornecedor e CNPJ do fornecedor logo no início;
- alerta quantos fornecedores do período ainda estão sem CNPJ antes de gerar o Excel;
- não altera contas, baixas, valores, documentos anexados, SPED ou regras fiscais.

Versão 17.8.108 — relatório mensal de contas pagas:
- adiciona “Pagas do mês” ao Contas a Pagar;
- filtra pelo mês da DATA DA BAIXA, independentemente do vencimento/competência;
- permite selecionar uma ou várias empresas e mostra quantidade/total antes de gerar;
- gera Excel com Resumo, Pagamentos consolidados e uma aba por empresa com pagamentos;
- inclui Nº Documento, vencimento, data da baixa, valor, competência, origem e status do anexo;
- não altera nenhuma conta, baixa, banco, documento, SPED ou regra fiscal.

Versão 17.8.107 — escolha da pasta de download dos scans:
- adiciona “Escolher pasta” na tela Baixar scans do WhatsApp/Adobe;
- permite salvar os PDFs em qualquer pasta escolhida pela usuária, como Área de Trabalho ou Documentos;
- memoriza a última pasta escolhida para os próximos lotes;
- o botão Anexar documento abre primeiro essa pasta escolhida;
- mantém como opção a pasta interna dados/financeiro/recebidos/AAAA-MM;
- não altera banco de dados, baixas, anexos existentes, SPED ou regras fiscais.

Versão 17.8.106 — organização visual dos scans baixados:
- adiciona “Organizar scans baixados” ao Contas a Pagar;
- esconde os nomes confusos do Adobe e apresenta os arquivos como SCAN 01, SCAN 02...;
- permite abrir o scan, pesquisar a conta pelo Nº Documento e vincular diretamente;
- depois do vínculo, o anexo permanente mantém o Nº Documento no nome e o arquivo bruto sai da fila principal;
- não altera baixas, banco de dados, SPED ou regras fiscais.

Versão 17.8.105 — anexos identificados pelo número do documento:
- ao anexar PDF/imagem no Contas a Pagar, o nome interno passa a priorizar o Nº Documento;
- padrão: DOC_<numero>_<fornecedor>_<vencimento>.pdf;
- se não houver número, usa SEM_DOC_ID_<id>_<fornecedor>_<vencimento>.pdf;
- o Pacote para Contabilidade usa o mesmo padrão, inclusive ao exportar anexos antigos;
- não altera banco de dados, baixas, SPED ou regras fiscais.

Versão 17.8.104 — correção responsiva da tela de download dos scans:
- mantém os links Adobe identificados e o download em lote da 17.8.103;
- move “Baixar todos” para a barra de ações ao lado de “Identificar links”, deixando a ação sempre visível;
- reduz a altura fixa das áreas de texto/resultado e maximiza automaticamente em telas baixas;
- não altera banco de dados, documentos financeiros, pacote da contabilidade ou módulos fiscais.

Versão 17.8.103 — download em lote dos scans do WhatsApp/Adobe:
- adiciona no Contas a Pagar o botão “Baixar scans do WhatsApp”;
- permite colar a mensagem inteira, identifica links compartilhados do Adobe Acrobat e tenta baixar todos;
- salva os arquivos em dados/financeiro/recebidos/AAAA-MM e abre essa pasta primeiro ao anexar uma conta;
- mostra sucesso, links que exigem abertura manual e erros sem interromper o restante do lote;
- gera relatório de download e arquivo com links não baixados;
- mantém banco de dados, anexos 17.8.102, pacote da contabilidade e módulos fiscais inalterados.

Versão 17.8.102 — documentos financeiros e pacote mensal para a contabilidade:
- Contas a Pagar passa a copiar PDFs/imagens anexados para dados/financeiro/documentos;
- adiciona status de anexo e ação rápida para anexar/abrir documento;
- gera ZIP mensal por competência e empresas selecionadas com os documentos e relatório Excel;
- lista contas sem anexo no pacote para conferência antes do envio à contabilidade;
- mantém bancos, regras fiscais, SPED e demais módulos inalterados.

Versão 17.8.100 — Excel → TXT sem linhas vazias intercaladas:
- elimina referências RAW totalmente vazias antes do Pré-PVA e da gravação do TXT;
- adiciona uma segunda barreira na escrita para nunca entregar linhas físicas em branco ao PVA;
- corrige o caso em que o PVA acusava “Estrutura da linha inválida” nas linhas 2, 4, 6, 8...;
- mantém CRLF correto, participante legível no Excel, CT-e sem crédito e todas as regras acumuladas.

Versão 17.8.99 — Excel → TXT com uma linha física por registro:
- normaliza terminador CR isolado para CRLF ao reconstruir o SPED, evitando que o PVA leia o arquivo inteiro como uma única linha;
- grava cada registro individualmente em vez de montar um texto gigante por concatenação;
- valida a quantidade de linhas físicas depois da gravação e bloqueia o arquivo se houver divergência;
- mantém a correção 17.8.98 de Código Participante + CNPJ/CPF + Nome no Excel e todas as regras fiscais acumuladas.

Versão 17.8.98 — participante legível no Excel:
- nas abas filhas como D190, a coluna de contexto Participante(D100) passa a exibir o CNPJ/CPF do 0150 em vez do COD_PART interno;
- o COD_PART técnico do D100/C100 permanece inalterado para preservar a conversão Excel → TXT;
- corrige especialmente os CT-e incluídos pelo módulo 17.8.97, cujos códigos podem ser numéricos curtos ou CTE_<CNPJ>.

Versão 17.8.97 — inclusão de CT-e ausentes sem crédito de ICMS:
- adiciona ao SPED Inteligente o botão “Incluir CT-e sem crédito” na aba CT-e / XML;
- lê ZIP com XMLs de CT-e autorizados e inclui somente documentos do período em que o declarante é tomador;
- cria participantes 0150, D100 e D190 quando necessários e não duplica chaves já existentes;
- escritura os CT-e sem apropriação de crédito de ICMS e preserva a apuração E110 original;
- gera relatório CSV com o ICMS destacado nos XMLs, porém não apropriado;
- não altera bancos de dados nem o arquivo SPED original.


Versão 17.8.95 — bloqueio de estorno sem crédito real no C170:
- nunca gera C197 automático quando o C170 não possui VL_BC_ICMS, ALIQ_ICMS e VL_ICMS positivos;
- bloqueia CFOPs de aquisição para uso/consumo 1407/1556/2407/2556 no estorno automático;
- passa a auditar C197 já existente mesmo quando o C100 tem ICMS zero, em vez de ignorar o documento;
- C197 sem C170 elegível correspondente fica em REVISAR e aparece na Conferência por NF;
- o caso real da NF 49092 (item 90401KRMR20, CFOP 1556, C170 ICMS zero e C197 indevido de R$ 1,88) passa a ser identificado e bloqueado.

Versão 17.8.94 — reconciliação segura de arredondamento no estorno ICMS:
- diferenças superiores a R$ 0,01 entre C100 e soma dos C170 deixam de ser tratadas automaticamente como erro quando houver prova matemática de arredondamento acumulado item a item;
- a prova exige que cada C170 coincida com BC × alíquota arredondado a centavos e que o C100 coincida exatamente com a soma teórica calculada sem arredondar cada item;
- o ajuste é distribuído em passos de R$ 0,01 entre os itens cujos resíduos de arredondamento justificam o sinal, em vez de concentrar todo o valor em um item;
- divergências sem prova exata continuam em REVISAR e não geram C197 automaticamente;
- a conferência por NF passa a exibir ICMS teórico, teto matemático de arredondamento e a reconciliação aplicada.

Versão 17.8.93 — auditoria interna C170 x C190 mesmo sem edição nova no Excel:
- detecta quando o próprio SPED de origem já chega com CST/CFOP/alíquota dos C170 divergentes do C190, mesmo que a planilha mostre 0 campos alterados;
- só reconstrói automaticamente quando os totais comprováveis de BC/ICMS/BC-ST/ICMS-ST/IPI fecham entre C170 e C190, evitando apagar grupos que não estejam representados nos itens;
- funde C190 antigos quando vários grupos passaram a uma única combinação no C170;
- preserva VL_RED_BC quando o novo resumo forma um único grupo analítico; em múltiplos grupos com redução de base, mantém revisão manual;
- a validação e a tela passam a mostrar explicitamente a quantidade de ajustes automáticos C190 e os documentos reconstruídos.

Versão 17.8.92 — C190 sincronizado com alterações de ICMS do C170 no Excel → TXT:
- quando CST_ICMS, CFOP ou ALIQ_ICMS muda no C170, o FiscalPro reconstrói os C190 do C100 afetado pela nova combinação analítica;
- preserva o VL_OPR total já escriturado e o distribui entre os novos grupos proporcionalmente ao valor dos itens;
- recompõe base/ICMS, base/ICMS-ST, ICMS-ST e IPI pelos valores efetivos dos C170;
- edição manual do próprio C190 prevalece e bloqueia a automação para aquele documento;
- documentos com VL_RED_BC ou COD_OBS distintos ficam em revisão, sem rateio inventado;
- a Conferência Excel registra o reagrupamento automático do C190.

Versão 17.8.91 — CST do C170 sincronizado com C100 no Excel → TXT:
- quando a usuária altera CST_PIS/CST_COFINS de uma entrada para 70-75/98/99, o FiscalPro zera os campos dependentes do tributo no C170 se eles não tiverem sido editados manualmente;
- em seguida, VL_PIS/VL_COFINS do C100 pai são retotalizados pela soma real dos C170 reconstruídos;
- alterações manuais de base/alíquota/valor são preservadas e ficam para conferência/Pré-PVA;
- mudanças para CST 50-66 não criam crédito por aproximação: o sistema avisa quando faltam base/alíquota/valor.

Versão 17.8.90 — Conferência do estorno por NF e reconciliação de centavos:
- Nova conferência por NF compara C100, soma dos C170 e C197 e mostra o impacto de cada nota no total.
- Diferenças de arredondamento de até R$ 0,01 por NF são reconciliadas na geração do C197 para não acumularem no mês.

Versão 17.8.89 — CFOP de entrada em regime especial de e-commerce/MG:
- reconhece a Mega Mix E-Commerce (PTA 45.000044018-75) como destinatária com atribuição própria de responsabilidade pelo ICMS-ST;
- quando o XML do fornecedor vem como venda normal (5101/5102/6101/6102), sem base/valor de ICMS-ST, a compra para revenda permanece 1102/2102 mesmo que o produto tenha NCM/CEST listado na ST;
- não converte capacetes 65061090 / CEST 01.013.00 para 1403/2403 apenas pelo enquadramento material do produto;
- se o próprio XML trouxer CFOP de ST ou base/valor de ICMS-ST, preserva 1403/2403;
- mantém a regra geral de ST para empresas sem esse regime especial e não altera bancos de dados.

Versão 17.8.85 — divergências e revisões em visão ampliada:
- cria um painel reutilizável com abas grandes para Resumo, Divergências, Revisões, Tributação, Fundamentos e Tratamento sugerido;
- amplia os detalhes da Análise Tributária em Lote e das Auditorias de Cadastro por Excel/XML;
- na Auditoria Tributária do SPED, adiciona “Ver divergência completa” e faz o duplo clique abrir a divergência/orientação em tela ampla;
- mantém o acesso separado à Ficha do NCM e preserva todas as regras fiscais acumuladas até a 17.8.84;
- não altera bancos de dados, SPED, Financeiro, regras de ICMS-ST, PIS/COFINS ou cálculos.

Versão 17.8.84 — adesivos NCM 3919.90 por descrição legal do CEST 01.090.00:
- impede que o FiscalPro confirme ICMS-ST apenas porque o NCM 3919.90 coincide com o item 90.0 do segmento de autopeças;
- para descrições de kit/grafismo decorativo de motocicleta, como “ADESIVO KIT PRATA BIZ125”, confirma que o CEST 01.090.00 não se aplica e não aplica MVA 71,78%;
- para descrição expressamente refletiva de segurança, mantém CEST 01.090.00 e MVA 71,78% na operação interna de MG;
- quando a descrição for insuficiente, mantém a decisão condicional e exige confirmar se o adesivo é refletivo, sem aplicar ST/MVA pelo NCM isolado;
- impede o fallback automático para CEST 01.999.00 neste caso, pois o residual depende da hipótese específica de regime especial prevista no RICMS/MG;
- atualiza Detalhes técnicos e indicador de segurança para mostrar “100% — NÃO APLICÁVEL” quando a exclusão pela descrição estiver confirmada;
- não altera bancos de dados, SPED, PIS/COFINS nem demais regras de ICMS-ST.

Versão 17.8.83 — PIS/COFINS por aplicação específica no NCM 8481.10.00:
- quando a aplicação em motocicleta (posição 87.11) estiver explicitamente informada ou fortemente identificada pela descrição/modelo, o FiscalPro confirma que o item 11 do Anexo II da Lei nº 10.485/2002 não alcança essa destinação;
- a exclusão do enquadramento monofásico não transforma a tributação padrão em regra absoluta: o motor continua para a sugestão do regime da empresa e mantém as demais exceções de PIS/COFINS em revisão;
- sem aplicação suficiente, o NCM 8481.10.00 continua em REVISÃO NECESSÁRIA, preservando o comportamento conservador;
- a Ficha passa a usar o campo de aplicação tanto para ICMS-ST quanto para PIS/COFINS e mostra o status monofásico nos Detalhes técnicos;
- não altera bancos de dados nem as regras de ICMS-ST/CEST/MVA já confirmadas.

Versão 17.8.82 — fidelidade PGE e revisões FiscalPro separadas:
- corrige o falso positivo de IND_MOV nos blocos A/D quando A010/D010 estão presentes;
- diferença C100.VL_MERC × soma C170 na EFD Contribuições deixa de ser erro do Pré-PGE e vira REVISÃO FISCALPRO;
- o Pré-Validador passa a distinguir erros/avisos PVA-PGE de auditorias extras do FiscalPro;
- preserva todas as validações bloqueantes comprovadas e não altera bancos de dados.

Versão 17.8.81 — Excel → TXT com geração direta:
- adiciona o fluxo completo dentro da aba Excel → TXT;
- cria geração direta ao lado da planilha validada, sem depender da janela “Salvar como”;
- mostra o caminho do TXT e do relatório após a geração;
- preserva MotorSPED, regras fiscais e bancos de dados.

Versão 17.8.80 — Conferência Excel com fluxo visível:
- adiciona “Selecionar Excel”, “Validar planilha”, “Conferir alterações” e “Gerar relatório” diretamente na aba Conferência Excel;
- sincroniza os estados dos atalhos da aba com a seleção, validação e conferência da planilha;
- preserva integralmente o MotorSPED, as regras fiscais e os bancos de dados.

Versão 17.8.79 — Pré-Validador PVA com ação visível:
- adiciona “Validar antes do PVA” diretamente dentro da aba Pré-Validador PVA;
- mantém “Salvar relatório” ao lado da validação e sincroniza o estado dos dois atalhos com a faixa superior;
- preserva integralmente o MotorSPED, as regras fiscais e os bancos de dados.

Versão 17.8.78 — Limpeza técnica e blindagem do SPED:
- remove da janela principal o pipeline SPED legado (LeitorSPED/MotorCorrecao) e mantém o MotorSPED/JanelaSPEDInteligente como caminho operacional único;
- substitui o atalho desconectado “Selecionar XML” por acesso direto ao módulo ativo XML → Planilha ST;
- atualiza testes históricos para validar versão mínima da funcionalidade, evitando falhas artificiais a cada nova release;
- atualiza a regressão do resumo para o aviso contextual atual sem reintroduzir a mensagem antiga;
- não altera bancos de dados nem regras tributárias.

Versão 17.8.77 — Contas a Pagar compacto e Agenda contextual:
- mantém “Detalhes da conta” sempre visíveis no cadastro financeiro, com layout mais compacto;
- desabilita “Lançar no Contas a Pagar” quando a fatura da Agenda já possui conta vinculada;
- mantém integralmente as correções tributárias acumuladas até a 17.8.76;
- não altera bancos de dados.

Versão 17.8.76 — Coerência da Ficha Tributária:
- a Ficha reconhece como confirmado o padrão legado `confirmado=True` + `decisao_st=SIM`, mesmo quando o motor estadual não preenche `decisao_confirmada`;
- o card ICMS-ST mostra SIM, e não REVISAR, quando a própria regra estadual já foi confirmada;
- o aviso superior deixa de dizer “NCM não listado” quando existe CEST/MVA confirmados e passa a refletir o contexto real;
- CEST é padronizado visualmente no formato 00.000.00, inclusive quando a origem fornece apenas os sete dígitos;
- mantém integralmente as correções da 17.8.75 e não altera bancos de dados.

Versão 17.8.75 — EX TIPI no PIS/COFINS e MVA interna confirmada:
- NCM dependente de EX TIPI passa a aparecer como CONDICIONAL, com a hipótese monofásica claramente descrita, sem aplicar alíquota zero automaticamente;
- para 85365090, EX 01 confirmado na revenda mantém CST 04 e alíquota zero; sem EX confirmado, a ficha exige revisão;
- em operação interna MG→MG com ICMS-ST confirmado, a MVA original estruturada é exibida também como MVA aplicada quando não há ajuste separado;
- mantém integralmente as correções da 17.8.74.

Versão 17.8.74 — Consistência CEST/MVA condicional:
- alinha cabeçalho, Resumo e Detalhes Técnicos quando o CEST/MVA são apenas sugestões residuais;
- mantém CEST/MVA como não confirmados até a validação da finalidade automotiva;
- não altera banco de dados nem a regra fiscal do motor condicional.

Versão 17.8.73 — Consolidação e recuperação de versões:
- unifica a linha estadual 17.8.69–17.8.72 com o motor condicional 17.8.70;
- restaura o resumo visível 17.8.71;
- incorpora finalidade automotiva no XML sem regredir a regra do Simples 17.8.66;
- remove a ambiguidade operacional dos dois ramos 17.8.71/17.8.72.

Versão 17.8.70 — Motor Tributário Condicional por Finalidade:
substitui a falsa negativa de ICMS-ST por decisão em três estados (SIM, NÃO fundamentado ou CONDICIONAL), impede que NCM ausente na base seja interpretado como "não ST", adiciona a confirmação de finalidade automotiva na Ficha Inteligente e aplica o CEST residual 01.999.00/MVA 71,78% somente quando a finalidade de peça, componente ou acessório de motocicleta estiver confirmada ou validada pelo motor. Inclui o NCM 85444200 (cabo do motor de partida), preserva os NCMs 85452000, 90268000 e 85365090 e mantém os Detalhes técnicos ampliados.

Versão 17.8.69 — Autopeças Residuais MG e Detalhes Técnicos:
inclui o enquadramento do NCM 85452000 (escova do motor de partida de motocicleta) e do NCM 90268000 (sensor híbrido de motocicleta) no CEST residual 01.999.00, com MVA original de 71,78%, preserva o enquadramento específico do NCM 85365090 no CEST 01.065.00 e elimina a duplicidade do campo ICMS interno nos Detalhes técnicos.

Versão 17.8.68 — Cobertura Estadual do Tocantins:
estrutura alíquota interna modal de 20%, FECOEP separado, autopeças do Anexo XXI/Protocolo 97/10 com MVA 36,56%/71,78% e ajuste interestadual, além de pneumáticos do Convênio 102/17. Na rota MG→TO a 7%, a MVA padrão de autopeças é 99,69% e a de pneu de motocicleta é 86,00%; como MG não é signatário do Protocolo 97/10, a retenção de autopeças pelo remetente não é presumida.

Versão 17.8.67 — Cobertura Estadual do Piauí:
estrutura alíquota modal de 22,5%, FECOP separado, autopeças do RICMS/PI (Anexo X, arts. 93-94) com MVA original de 26,50% na fidelidade qualificada e 40,00% nos demais casos, e pneumáticos dos arts. 75-76/Convênio 102/17. Na rota MG→PI a 7%, as MVAs de referência são 51,80%/68,00% para autopeças e 92,00% para pneu de motocicleta. Regime especial/credenciamento de atacadista de peças para motocicletas permanece como alerta e não é presumido.

Versão 17.8.66 — Simples Nacional no cálculo ICMS-ST/MG por XML:
quando o remetente é ME/EPP do Simples Nacional, o módulo XML usa automaticamente a MVA original (sem ajuste interestadual) e deduz, na memória do ICMS-ST, o valor da operação própria calculado pela alíquota interna ou interestadual aplicável, conforme RICMS/MG/2023, Anexo VII, Parte 1, art. 20, § 6º e art. 22, § 1º. A dedução não cria crédito escritural e continua podendo ser sobrescrita manualmente por item.

Versão 17.8.65 — Vínculo Automático da Agenda com Contas Existentes:
a baixa direta da Agenda passa a localizar lançamentos já existentes no Contas a Pagar quando o item mensal ainda não possui conta_id. A busca usa empresa, competência, fornecedor e proximidade do vencimento, solicita confirmação antes de vincular e depois executa a mesma rotina segura de baixa.

Versão 17.8.64 — Baixa Direta na Agenda de Faturas:
adiciona o botão “Dar baixa hoje” na Agenda Inteligente para contas já vinculadas ao Contas a Pagar. A ação grava a data da baixa na conta, preserva baixas existentes e sincroniza automaticamente a etapa da agenda para PAGA.

Versão 17.8.63 — Cobertura Estadual do Maranhão:
estrutura alíquota modal de 23%, FUMACOP separado, autopeças alcançadas pelo Protocolo 41/08 com MVA ajustada à carga interna maranhense e pneumáticos do Convênio 102/17. A rota MG→MA reconhece, em regra, a responsabilidade do remetente, preservando exceções e regimes especiais.

Versão 17.8.62 — Cobertura Estadual de Sergipe:
estrutura alíquota modal de 19%, FECOEP geral de 1% no escopo automotivo, MVA ajustada com ICMS + FECOEP, autopeças do Protocolo 97/10/Tabela VI com antecipação segura para origem MG não signatária e pneumáticos do Convênio 102/17.

Versão 17.8.61 — Origem da Regra RN Corrigida:
corrige o fallback visual dos Detalhes técnicos para que valores ausentes exibidos como “Não informada” também acionem a fonte oficial contextual do motor estadual. Para 87141000 MG→RN, “Origem da regra” passa a mostrar SEFAZ/RN — RICMS/RN, Anexo 005.

Versão 17.8.60 — Fundamentação RN Sincronizada:
sincroniza a regra estadual estruturada com os Detalhes técnicos e a Base Legal, identifica corretamente as fontes oficiais do Rio Grande do Norte e elimina o fallback indevido para a fonte de ST/Minas Gerais.

Versão 17.8.59 — Detalhes Técnicos Ampliados:
cria uma visualização maximizada da aba Detalhes técnicos, com tabela mais larga, rolagem horizontal/vertical e explicação ampliada, preservando integralmente os motores tributários da 17.8.58.

Versão 17.8.56 — Cobertura Estadual da Paraíba:
estrutura alíquota modal de 20%, FUNCEP objetivo para o escopo automotivo, autopeças do Anexo 05 com MVA oficial 36,56%/71,78% e tabelas interestaduais, além de pneumáticos com MVAs próprias. A rota MG→PB reconhece a responsabilidade do remetente pelo Protocolo 41/08, enquanto pneumáticos seguem o Convênio 102/17.

Versão 17.8.55 — Cobertura Estadual de Alagoas:
estrutura a alíquota modal de 20,5% vigente desde 01/04/2026, FECOEP de 1% separado para o escopo automotivo, autopeças do Anexo I do Decreto 90.309/2023 com MVA 36,56%/71,78% e ajuste interestadual, além de pneumáticos do Anexo XI com Convênio 102/17. A rota MG→AL reconhece a responsabilidade do remetente pelo Protocolo 41/08, preservando exceções e alertas de regime especial.

Versão 17.8.54 — Cobertura Estadual de Pernambuco:
estrutura alíquota modal de 20,5%, FECEP separado, autopeças com MVA oficial de PE e responsabilidade interestadual condicionada ao Protocolo 97/10, além de pneumáticos com tabela oficial e Convênio 102/17. A Ficha diferencia MVA conhecida de retenção ST efetivamente atribuída ao remetente.

Versão 17.8.53 — Cobertura Estadual do Ceará:
estrutura alíquota modal de 20%, FECOP objetivo para o escopo automotivo, autopeças pelo modelo cearense de carga líquida condicionado ao CNAE do destinatário e pneumáticos com separação segura entre carga líquida e regime específico. A Ficha e o Configurador Olist passam a exibir o modelo de cálculo ST sem transformar carga líquida em MVA.

Versão 17.8.52 — Cobertura Estadual do Distrito Federal:
estrutura alíquota modal de 20%, FCP objetivo, autopeças do item 28 com MVA 71,78%/36,56% de fidelidade e pneumáticos com MVA original própria, aplicando a fórmula de MVA ajustada nas operações interestaduais. O Configurador Olist continua consumindo o mesmo motor estadual do FiscalPro.

Versão 17.8.51 — Sincronização da Ficha com a Cobertura Estadual:
força Resumo, Detalhes técnicos e explicação do parecer a usar a UF de destino, separa alíquota interestadual da alíquota interna e evidencia MVA-base/MVA aplicada e FCP na cobertura estadual.

Versão 17.8.50 — Cobertura Estadual de Mato Grosso:
estrutura alíquota modal de 17%, autopeças e pneumáticos do Anexo X com MVA condicional da Portaria 195/2019 e FCP objetivo para o escopo automotivo, sem inventar MVA ajustada interestadual.

Versão 17.8.49 — Cobertura Estadual de Mato Grosso do Sul:
estrutura alíquota modal de 17%, autopeças e pneumáticos do Subanexo I/Anexo III com MVAs próprias e FECOMP objetivo para o escopo automotivo.

Versão 17.8.48 — Atalhos Enter nas consultas e Contas a Pagar:
padroniza Enter/KP Enter como ação de analisar NCM e cria fluxo por teclado no cadastro rápido de contas, avançando pelos campos obrigatórios e salvando quando o formulário estiver completo.

Versão 17.8.47 — Cobertura Estadual do Rio Grande do Sul:
estrutura a alíquota modal de 17%, pneumáticos em ST com MVA do RICMS/RS, exclusão das autopeças da ST desde 01/11/2024 e AMPARA objetivo para o escopo automotivo.

Versão 17.8.46 — Cobertura Estadual de Santa Catarina:
estrutura alíquotas internas catarinenses, pneumáticos em ST com MVA dos arts. 53 a 55 do Anexo 3, exclusão das autopeças da ST desde 01/04/2020 e tratamento seguro do Fundo Social.

Versão 17.8.45 — Cobertura Estadual do Paraná:
estrutura a alíquota modal de 19,5%, autopeças e pneumáticos do Anexo IX com MVAs da Resolução SEFA 571/2019, ajuste interestadual e FECOP objetivo para os segmentos automotivos instalados.

Versão 17.8.44 — Cobertura Estadual de Goiás:
abre a cobertura goiana com alíquota modal de 19%, pneumáticos estruturados pela tabela vigente do Decreto 10.799/2025 e exclusão segura das autopeças da ST pelas operações posteriores desde 01/03/2018.

Versão 17.8.42 — Cobertura Estadual do Espírito Santo:
estrutura pneumáticos pela Portaria 16-R atualizada, corrige a autoaplicação de ST em autopeças após a denúncia capixaba do Protocolo 41/08 e evidencia a antecipação parcial da Portaria 13-R/2022.

Versão 17.8.41 — Cobertura Estadual da Bahia:
expande a cobertura baiana para pneumáticos, consolida autopeças do Anexo 1/2026 e torna o FECOP objetivo para os segmentos automotivos estruturados, sem generalizar a outros NCMs.

Versão 17.8.40 — Cobertura Estadual de São Paulo:
estrutura autopeças e pneumáticos paulistas com IVA-ST, ajuste interestadual, FECOEP objetivo e transição legal de 01/10/2026, evitando aplicar IVA genérico a itens revogados ou com regra específica.

Versão 17.8.39 — Cobertura Estadual do Pará:
incorpora alíquota modal de 19% e regras estruturadas de ICMS-ST/PA para autopeças e pneumáticos, mantendo FCP/fundo como revisão explícita quando ainda não automatizado.

Versão 17.8.38 — Mapa de Cobertura Tributária Nacional:
mede a cobertura efetivamente instalada por UF, separando cobertura ampliada, estadual parcial e regra interestadual geral, sem inferir ausência de tributo pela ausência de regra local.

Versão 17.8.37 — Resumo Inteligente em Mini-cards:
reorganiza a leitura orientativa do comparador em cartões de PIS/COFINS, ICMS, ICMS-ST, pendências/segurança e conclusão, sem alterar regras fiscais.

Versão 17.8.36 — Resumo Inteligente da Comparação:
interpreta as diferenças do comparador em linguagem orientativa, sem eleger automaticamente um cenário fiscal e sem confundir alíquota nominal com carga efetiva.

Versão 17.8.35 — Comparação sempre sincronizada:
limpa imediatamente cartões, tabela e resultado anterior quando NCM, empresa,
operação ou UFs são alterados, impedindo que valores antigos permaneçam visíveis.

Versão 17.8.34 — Comparador Visual e Uso de Cenário:
destaca as principais diferenças em cartões e permite aplicar o Cenário A ou B
diretamente na Ficha Inteligente, preservando o contexto comparado.

Versão 17.8.33 — Comparar Cenários Tributários:
compara o mesmo NCM em duas empresas/regimes/rotas usando os mesmos motores da
Ficha Inteligente e destaca somente as diferenças tributárias relevantes.

Versão 17.8.32 — Histórico Tributário sem Duplicidades:
saneia registros repetidos do Acesso Rápido, normaliza o contexto da consulta e
diferencia visualmente cenários distintos do mesmo NCM.

Versão 17.8.31 — Acesso Rápido Tributário:
acrescenta últimas consultas, favoritos visíveis na Central, botão de favoritar na
Ficha Simplificada e refina os cards de saúde das bases sem alterar os motores fiscais.

Versão 17.8.30 — Correção do carregamento da Ficha pela Central Tributária:
garante que a Ficha Inteligente conclua a montagem da interface quando recebe
empresa/regime/operação/UF pela consulta rápida, sem deixar campos pela metade.

Versão 17.8.29 — Empresa obrigatória na consulta tributária:
impede que “Todas as empresas” assuma Lucro Real por padrão e bloqueia o cálculo
até que uma empresa específica defina o regime correto de PIS/COFINS.

Versão 17.8.28 — Central Tributária Inteligente:
repagina a área Tributação com consulta rápida, saúde das bases e ferramentas
agrupadas por finalidade; a Ficha Inteligente passa a priorizar cartões-resumo
e mantém os detalhes técnicos em uma aba separada.

Base cumulativa da 17.8.27 — Clareza do IPI e Revisão Explicada:
separa TIPI de referência do tratamento do IPI na operação e explica os motivos do status REVISAR.

Base cumulativa da 17.8.26 — Regime Tributário Automático por Empresa:
centraliza empresa → regime e aplica o regime correto nas consultas tributárias,
com prioridade para regras específicas como monofásico e alíquota zero.

Base cumulativa da 17.8.25 — Clareza das Baixas no Contas a Pagar:
separa visualmente Vencimento de Data da Baixa e mantém compatibilidade com planilhas antigas.

Versão 17.8.24 — SPED Final Cumulativo:
padroniza a saída da Etapa 2 como um único arquivo FINAL, usando o SPED selecionado como base cumulativa e preservando correções anteriores.

Base cumulativa da 17.8.23 — Sincronização PGE M205/M605 na Etapa 2:
fecha a cadeia M200→M205 e M600→M605 após a redução do débito, e o
Pré-PVA passa a detectar essa mesma divergência antes da validação oficial.

Base cumulativa da 17.8.22 — Correção segura da Etapa 2 de ICMS-ST nas saídas:
libera a geração de um novo SPED somente quando a auditoria SPED + XML estiver
sem pendências e os itens a corrigir forem C170 com vínculo de confiança ALTA.
Atualiza bases/valores de PIS/COFINS, retotaliza C100, sincroniza o Bloco M,
executa Pré-PVA comparativo e reaudita o arquivo antes de gravar.

Base cumulativa da 17.8.21 — seleção múltipla de empresas nos relatórios do Contas a Pagar.
Base cumulativa da 17.8.20 — Exclusão ICMS-ST da Base PIS/COFINS — Etapa 2 com XMLs.
Base cumulativa da 17.8.19 — pré-auditoria das saídas pelo SPED.
Base cumulativa da 17.8.18 — ICMS próprio separado das pendências de ICMS-ST.
Base cumulativa da 17.8.17 — Alíquota Zero fora das Pendências de ICMS-ST.
Base cumulativa da 17.8.16 — Exclusão ICMS-ST da Base PIS/COFINS — Etapa 1.
Base cumulativa da 17.8.15 — Controle de Entregas mais enxuto.
Base cumulativa da 17.8.14 — empresas/regimes corrigidos no Controle de Entregas.
Base cumulativa da 17.8.13 — Controle de Entregas em grade mensal.
Base cumulativa da 17.8.12 — Interface enxuta.
Base cumulativa da 17.8.11 — Exportação rápida da Auditoria Excel.
"""

from __future__ import annotations

NOME_APP = "FiscalPro"
NOME_COMPLETO = "FiscalPro — Assistente Fiscal Inteligente"
DESCRICAO_APP = (
    "Assistente para análise de SPED, consultas tributárias, cálculo de ICMS-ST, "
    "auditoria tributária, controle de obrigações e contas a pagar."
)
SLOGAN = "Simples, seguro e rastreável"

# Versão exibida no sistema e versão numérica reservada ao instalador do Windows.
VERSAO_APP = "18.2.25"
VERSAO_INTERFACE = VERSAO_APP
VERSAO_ARQUIVO_WINDOWS = "18.2.25.0"

PUBLICADOR = "Stephane Rhis"
CREDITOS = "Stephane Rhis + ChatGPT"
NOME_EXECUTAVEL = "FiscalPro"
NOME_PASTA_INSTALACAO = "FiscalPro"

AVISO_LEGAL = (
    "O FiscalPro é uma ferramenta de apoio. Resultados tributários devem ser "
    "conferidos com a legislação vigente e com o responsável fiscal antes da escrituração."
)
