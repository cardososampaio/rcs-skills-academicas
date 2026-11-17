# Busca Acadêmica

Skill para buscar, verificar e revisar literatura acadêmica com prioridade à pesquisa brasileira e capacidade de pesquisa internacional. O ponto de entrada é [`SKILL.md`](SKILL.md).

## Modos de uso

O modo simples entrega revisão breve, referências, CSV e BibTeX. O modo aprofundado define o recorte com o usuário quando necessário e produz relatório com 2.000 a 5.000 palavras analíticas, resumo executivo, tabela resumo, estado da arte, avaliação inicial da robustez, tendências e até 20 referências destacadas. A bibliografia completa e os anexos ficam fora dessa contagem.

Os artigos de periódicos e artigos de revisão têm prioridade. Trabalhos de congressos e capítulos precisam ser recuperados em bases acadêmicas e fazer parte do recorte. BDTD é consultada somente mediante pedido explícito. O download de PDFs é oferecido ao final e exige aceite.

## Fontes e ferramentas

OpenAlex, SciELO e DOAJ vêm primeiro. Crossref e Semantic Scholar são utilizados na recuperação complementar e na conferência de metadados. Integrações disponíveis de Consensus, Scite, SciSpace e serviços semelhantes devem ser usadas quando pertinentes.

O portal SciELO costuma recusar buscas automatizadas. Nesses casos, a skill recupera pelo OpenAlex os periódicos listados na SciELO e identifica os registros como recuperação indireta, sem apresentá-la como busca direta.

O OpenAlex funciona sem chave, com uma cota diária pequena e compartilhada por rede. Cada pessoa que usa a skill cria a própria chave gratuita e a define em `OPENALEX_API_KEY` no próprio computador. Nenhuma chave acompanha este repositório.

O pacote mantém o conjunto de registros recuperados nas exportações, com seleção, motivos de exclusão, URLs, fontes e pendências. Pesquisa sobre o Brasil, afiliação brasileira, periódico brasileiro e idioma português são dimensões distintas.

## Arquivos da skill

- `SKILL.md` contém os fluxos e as regras de execução
- `references/` contém orientações sobre fontes, integrações, qualidade, relatório aprofundado, BDTD e easyScieloPack
- `assets/` contém modelos de plano, registros e relatórios
- `scripts/` contém busca, importação, consolidação, enriquecimento, exportação, gráficos e auditoria
- `tests/` contém testes automatizados com exemplos explicitamente sintéticos
- `agents/openai.yaml` contém os metadados de interface

Copiar a pasta inteira quando for utilizar a skill em um agente. Publicar a pasta no repositório não instala a skill em nenhum ambiente.

## Requisitos e validação

O fluxo central usa Python 3.10 ou superior e a biblioteca padrão. R e easyScieloPack são opcionais. `pypdf` é opcional para validação estrutural mais detalhada dos PDFs. A skill pode usar outras ferramentas expostas pelo ambiente para pesquisa e leitura.

Executar os testes a partir desta pasta

```bash
python -m unittest discover -s tests -v
```

Para um diagnóstico pequeno de acesso às bases

```bash
python scripts/academic_search.py doctor --out diagnostico
```

Na versão 1.1.0, os 89 testes passaram em Windows com Python 3.14.

Na preparação da versão 1.0.0, os 75 testes passaram, inclusive na cópia descompactada do pacote. Foram realizados testes de busca em OpenAlex, DOAJ, Crossref e Semantic Scholar, de enriquecimento por DOI e um uso independente com registros fornecidos. O acesso direto à SciELO retornou bloqueio neste ambiente e foi registrado como tal.

A documentação e o código do easyScieloPack foram examinados, e seu formato de importação possui testes. O pacote R não foi executado no ambiente de preparação porque R não estava disponível. Consulte [`references/easyscielopack.md`](references/easyscielopack.md).

## Histórico do procedimento de busca

Mudanças no modo de procurar alteram os resultados mesmo quando a literatura é a mesma. O CSV e o manifesto registram a versão da skill e a data das consultas para que buscas feitas em momentos diferentes possam ser comparadas.

- **1.1.0** No OpenAlex, a busca padrão passou de texto completo para título e resumo, e os tipos documentais do plano passaram a ser filtrados na própria base. Ambas as mudanças reduzem o número de registros recuperados em relação à 1.0.0. Foram acrescentados os recortes brasileiros opcionais, a busca por citações e referências e a recuperação indireta da SciELO quando o portal bloqueia a busca. As exportações passaram a registrar versão e datas de consulta.
- **1.0.0** Primeira versão publicada.

## Limites

Disponibilidade, cotas, credenciais e esquemas das bases podem mudar. A skill distingue falhas, bloqueios, truncamento e recuperação vazia. Um relatório aprofundado não é automaticamente uma revisão sistemática. Os gráficos descrevem os documentos recuperados e selecionados, sem estimar toda a produção do campo.

Os scripts não substituem a triagem, a conferência das referências nem a análise do agente. A auditoria verifica consistência e estrutura, sem demonstrar que as conclusões científicas estão sustentadas. Resumos, trechos e textos integrais devem ser identificados pelo nível efetivo de leitura.

## Citação e licença

Consulte [`CITATION.cff`](CITATION.cff) para citar esta skill e a [licença MIT do repositório](../../LICENSE). O pacote externo easyScieloPack mantém sua própria autoria e licença e não é redistribuído aqui.
