# Avaliação do pacote e do comportamento

## Integridade técnica

Executar `python scripts/check_package.py --self-test` na pasta da skill. A verificação cobre arquivos necessários, rotas, limite do núcleo, metadados e estrutura dos casos. Os ensaios determinísticos introduzem defeitos em cópias temporárias para verificar que o empacotamento incompleto é detectado.

Esses testes não executam pareceres nem avaliam qualidade científica. Não apresentar o resultado do script como validação semântica.

## Ensaios com agente

Usar os pedidos e materiais sintéticos de `../assets/casos-avaliacao.json`. Fornecer ao executor apenas a skill, o pedido e o material; manter os critérios esperados fora de seu contexto. Avaliar a resposta pelos critérios depois da execução.

Verificar decisões observáveis: recusar nota sem abandonar avaliação; não presumir análise realizada; distinguir informação ausente de falha; manter alternativas de reparo; respeitar gênero, desenho e escopo; entregar os blocos pertinentes. Não exigir redação idêntica a um gabarito.

Incluir contraprovas em que não há falha: hipótese refutada bem relatada, números com denominadores distintos, argumento teórico sem amostra e contribuição regional adequada ao público. A ausência de críticas fabricadas é parte do resultado esperado.

Registrar separadamente casos preparados, casos executados, saídas examinadas e limitações. Uma execução bem-sucedida não demonstra estabilidade universal. Se surgir falha, corrigir a orientação canônica e repetir o caso afetado e uma contraprova pertinente, sem repetir todo o conjunto por rotina.
