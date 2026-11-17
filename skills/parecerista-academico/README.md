# Parecerista Acadêmico

Skill em português para agentes de IA produzirem pareceres acadêmicos rigorosos, rastreáveis e construtivos.

## O que faz

A skill orienta a leitura integral de manuscritos e organiza a avaliação em múltiplas passagens. Ela combina critérios adequados ao desenho da pesquisa com quatro lentes transversais de sustentação, inferência, escopo e contribuição.

Depois da avaliação convencional, executa um **stress test adversarial** para procurar contra-argumentos, explicações alternativas, premissas não examinadas, elos inferenciais frágeis e generalizações excessivas. Nenhuma crítica adversarial entra automaticamente no parecer. O agente deve formular a melhor defesa possível do manuscrito e reconciliar as duas leituras antes da recomendação editorial.

Também inclui regras de rastreabilidade, atomicidade das críticas, verificação de alegações de ausência, classificação de gravidade e separação entre comentários aos autores e recomendação confidencial ao editor.

## Arquivo principal

- [`SKILL.md`](SKILL.md) — núcleo, modos e rotas, versão 2.1.0.
- [`references/`](references/) — protocolo, critérios por desenho, saídas, viabilidade e internacionalização.
- [`assets/casos-avaliacao.json`](assets/casos-avaliacao.json) — cenários sintéticos para ensaios de comportamento.
- [`scripts/check_package.py`](scripts/check_package.py) — verificação de integridade do pacote.

## O que muda na versão 2.1.0

Saídas distintas para parecer completo, avaliação focal, reavaliação e resposta a pareceristas tornam explícito o que foi examinado. A recomendação confidencial fica separada quando a tarefa é dirigida ao editor. Problemas principais incluem viabilidade, sem confundir gravidade com possibilidade de reparo.

Notas de qualidade e probabilidades de aceite são recusadas em favor de diagnóstico fundamentado. A preparação internacional respeita gênero e contribuição, e os módulos de métodos mistos e texto como dado/IA aplicam critérios ao desenho efetivo. Os critérios existentes permanecem disponíveis em referências carregadas conforme a tarefa.

A versão do núcleo fica em `metadata.version`, para compatibilidade com o formato de skills, e corresponde à versão do arquivo de citação.

## Verificação

Executar `python scripts/check_package.py --self-test` na pasta da skill. O comando verifica estrutura e exercita falhas de empacotamento; não avalia qualidade científica. Para ensaios com agentes, seguir [Avaliação](references/avaliacao.md). A existência de casos não significa que suas saídas foram executadas ou aprovadas.

## Instalação

Copie esta pasta para o diretório de skills do seu agente, preservando `SKILL.md` e todos os recursos relativos. Copiar apenas o arquivo principal deixa os critérios e modos incompletos.

Exemplo:

```text
.agents/skills/parecerista-academico/SKILL.md
```

## Uso

```text
Use a skill parecerista-academico para avaliar integralmente este manuscrito e produzir um parecer aos autores e uma recomendação confidencial ao editor.
```

## Limites

A skill apoia o julgamento humano. Não transforma uma execução de IA em parecer independente, consenso entre especialistas ou validação externa do manuscrito. O uso de IA em revisão por pares pode ser restringido por revistas e editoras.

## Citação

> Sampaio, Rafael Cardoso. *Parecerista Acadêmico*. Skill para agentes de IA. Versão 2.1.0. 2026.

Licença MIT conforme o arquivo [LICENSE do repositório](https://github.com/cardososampaio/rcs-skills-academicas/blob/main/LICENSE).
