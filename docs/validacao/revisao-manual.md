# Revisão manual dos anúncios

## Método

A revisão usou a base de 10.099 vagas da release `v2026.10.27`. Foram selecionados aleatoriamente 370 anúncios entre os aceitos pelo sistema. [Release usada na revisão](https://github.com/diasgarcia/tech-skills-br/releases/tag/v2026.10.27)

O CSV registra o número da ficha no sorteio e identifica cada anúncio pela fonte (`source`) e pelo ID no portal (`external_id`). [Lista das 370 vagas](amostra.csv)

A revisão comparou o título e a descrição de cada anúncio com os dados registrados. A conferência avaliou o enquadramento no escopo de TI e o registro das habilidades citadas na descrição. Cada anúncio com erro foi contado uma vez.

## Resultado

Foram identificados erros em 11 dos 370 anúncios revisados. A taxa de erro na amostra foi de **2,97%**.

| Resultado da revisão | Anúncios |
| --- | ---: |
| Habilidade citada na descrição e ausente do catálogo | 7 |
| Anúncio fora do escopo de TI aceito pelo filtro | 4 |
| Sem erro nos critérios avaliados | 359 |
| **Total revisado** | **370** |

## Habilidades fora do catálogo

| Ficha | Título do anúncio | Evidência na descrição | Resultado da revisão |
| --- | --- | --- | --- |
| VAL-001 | Engenheiro de Dados Júnior | Operar pipelines do Google Cloud e acompanhar as execuções no Cloud Composer. | O sistema registrou GCP. O catálogo não tinha Cloud Composer. |
| VAL-002 | Desenvolvedor Frontend Júnior | Criar rotas com TanStack Router e desenvolver interfaces em React. | O sistema registrou React. O catálogo não tinha TanStack Router. |
| VAL-003 | Analista Júnior de Sistemas Hospitalares | Registrar e acompanhar incidentes dos usuários no Freshservice. | O sistema registrou Gestão de Chamados. O catálogo não tinha Freshservice. |
| VAL-004 | Engenheiro de Software Júnior | Instrumentar os serviços com OpenTelemetry e acompanhar métricas no Datadog. | O sistema registrou Datadog. O catálogo não tinha OpenTelemetry. |
| VAL-005 | Estágio em Sistemas e Dados | Configurar formulários no LimeSurvey e criar painéis no Power BI. | O sistema registrou Power BI. O catálogo não tinha LimeSurvey. |
| VAL-006 | Analista de Testes Júnior | Criar e executar testes automatizados de fluxos SAP com Tricentis Tosca. | O sistema registrou SAP e Testes Automatizados. O catálogo não tinha Tricentis Tosca. |
| VAL-007 | Analista de Infraestrutura Júnior | Gerenciar dispositivos corporativos pelo Microsoft Intune e contas pelo Active Directory. | O sistema registrou Active Directory. O catálogo não tinha Microsoft Intune. |

## Anúncios fora de TI aceitos pelo filtro

| Ficha | Título do anúncio | Evidência na descrição | Resultado da revisão |
| --- | --- | --- | --- |
| VAL-008 | Analista de Qualidade de Fornecedores I | Auditar fornecedores, tratar não conformidades e acompanhar a qualidade dos materiais comprados. | O sistema aceitou o anúncio como QA. A função é de qualidade de fornecedores. |
| VAL-009 | Técnico de Campo Júnior | Fazer manutenção preventiva e corretiva em empilhadeiras elétricas e a combustão. | O sistema aceitou o anúncio como Field Service / Hardware. A função é de manutenção de empilhadeiras. |
| VAL-010 | Assistente de Help Desk de RH | Atender dúvidas sobre férias, benefícios, ponto e folha de pagamento. | O sistema aceitou o anúncio como Service Desk / Help Desk. A função é de atendimento de RH. |
| VAL-011 | Assistente de Tecnologia de Aplicação | Calibrar pulverizadores e orientar produtores sobre o uso de adjuvantes agrícolas. | O sistema aceitou o anúncio como Outros/TI Geral. A função é de assistência técnica agrícola. |
