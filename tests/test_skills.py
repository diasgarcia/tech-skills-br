import pytest

from scraper.models import Job
from scraper.skills import (
    SkillExtractor,
    attach_skills,
    jobs_with_skills_by_area,
    normalize_tech,
    overall_skill_counts,
    skills_by_area,
)


@pytest.fixture(scope="module")
def ext():
    return SkillExtractor.from_file()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("C# e C++", "c# e c++"),
        ("Node.js", "node js"),
        ("Programação Ágil", "programacao agil"),
    ],
)
def test_normalize_tech_preserva_cerquilha_e_mais(raw, expected):
    result = normalize_tech(raw)

    assert result == expected


@pytest.mark.parametrize(
    "texto,espera_nodejs,espera_node_red",
    [
        ("Node", True, False),
        ("Node.js", True, False),
        ("NodeJS", True, False),
        ("Node-RED", False, True),
        ("node red", False, True),
        ("nodered", False, True),
        ("Node-RED e Node.js", True, True),
    ],
)
def test_node_nao_confunde_nodejs_com_node_red(
    ext, texto, espera_nodejs, espera_node_red
):
    encontradas = set(ext.extract("Desenvolvedor Júnior", texto))
    assert ("Node.js" in encontradas) is espera_nodejs
    assert ("Node-RED" in encontradas) is espera_node_red


def test_exclusao_de_sufixo_do_alias_e_generica():
    extractor = SkillExtractor(
        {"grupo": {"Ferramenta": ["foo"], "Ferramenta Bar": ["foo bar"]}},
        secoes_descarte=[],
        secoes_conteudo=[],
        contextos_descarte={},
        exclusoes_sufixo_alias={"Ferramenta": {"foo": ("bar",)}},
    )

    foo = extractor.extract("Uso de foo")
    foo_bar = extractor.extract("Uso de foo bar")

    assert foo == ["Ferramenta"]
    assert foo_bar == ["Ferramenta Bar"]


def test_extrai_linguagens_e_frameworks(ext):
    found = ext.extract("Desenvolvedor Júnior", "Vaga com Python, Django e PostgreSQL.")
    assert {"Python", "Django", "PostgreSQL"} <= set(found)


def test_extrai_habilidades_de_analise_de_redes_sociais(ext):
    texto = (
        "Analisar dados e desenvolver dashboards de social media. "
        "Atuar com Social Listening nas ferramentas Stilingue e Sprinklr. "
        "Transformação de dados em narrativas para apoiar decisões."
    )

    found = set(ext.extract("Analista de Dados Júnior", texto))

    assert {
        "Análise de Dados",
        "Social Listening",
        "Data Storytelling",
        "Stilingue",
        "Sprinklr",
    } <= found
    assert "Dashboards" not in found


def test_c_sharp_nao_vira_c_solto(ext):
    # "C#" nao pode ser reduzido a "c" e casar com qualquer letra c do texto.
    legitimas = ext.extract("Dev .NET", "Experiência com C# e SQL Server.")
    falso_positivo = ext.extract("Analista", "Turno c de segunda a sexta.")

    assert "C#" in legitimas
    assert "C#" not in falso_positivo


def test_nao_casa_dentro_de_outra_palavra(ext):
    found = ext.extract("Vaga em Goiânia", "Atuação presencial.")
    java_only = ext.extract("Dev", "Stack JavaScript no front.")

    assert "Go" not in found
    assert "JavaScript" in java_only
    assert "Java" not in java_only


def test_go_casa_so_com_g_maiusculo(ext):
    # "Go" (linguagem) casa; "go" minusculo e palavra comum do ingles.
    linguagem = ext.extract("Dev", "Conhecimento de Go.")
    go_live = ext.extract("Dev", "Apoiar o go live do sistema.")
    estado = ext.extract("Dev", "Vaga em Anápolis, GO.")

    assert "Go" in linguagem
    assert "Go" not in go_live
    assert "Go" not in estado


def test_alias_de_caixa_mista_casa_em_qualquer_caixa(ext):
    # "pfSense" tem maiuscula no proprio nome: continua casando normalizado.
    textos = [
        "Configurar pfSense na rede.",
        "Configurar PFSENSE na rede.",
        "Configurar pfsense na rede.",
    ]

    resultados = [ext.extract("Dev", texto) for texto in textos]

    assert all("Firewall" in resultado for resultado in resultados)


def test_secao_de_beneficios_nao_conta_como_requisito(ext):
    # "Open English" e uma parceria, nao requisito de ingles.
    desc = (
        "Requisitos: conhecimento em hardware e software. "
        "Beneficios: plano de saude e parcerias com Open English e Gympass."
    )
    found = ext.extract("Analista de Suporte", desc)
    assert "Hardware" in found
    assert "Inglês" not in found


def test_beneficio_de_hardware_nao_conta_como_skill(ext):
    # Padrao BairesDev: hardware como item de beneficio, nao requisito.
    desc = (
        "Atuar com Python e Django. "
        "What to Expect from Us: Home Office Setup: Complete hardware provision."
    )
    found = ext.extract("Desenvolvedor Python", desc)
    assert "Python" in found
    assert "Hardware" not in found


def test_requisitos_depois_de_beneficios_seguem_valendo_antes(ext):
    desc = "Conhecimento em Git e AWS. Informações adicionais: vale refeição."

    found = ext.extract("Dev", desc)

    assert {"Git", "AWS"} <= set(found)


def test_beneficios_no_meio_nao_corta_requisitos(ext):
    # Padrao LinkedIn (Camisaria FMW): "Beneficios" vem ANTES de
    # "Principais atividades" e "Requisitos" -- o corte ali descartaria
    # os proprios requisitos.
    desc = (
        "Sobre a vaga: auxiliar de ti. Salario: R$ 2.100,00. "
        "Beneficios: vale transporte e vale refeicao. "
        "Principais atividades: suporte em hardware, Windows e Pacote Office. "
        "Requisitos: conhecimento em Hardware, Windows e Pacote Office."
    )
    found = ext.extract("Auxiliar de TI", desc)
    assert {"Hardware", "Windows"} <= set(found)


def test_beneficios_no_fim_continuam_sendo_cortados(ext):
    # Sem marcador de conteudo depois, o corte segue valendo normalmente.
    desc = "Requisitos: conhecimento em hardware e software. Beneficios: plano de saude."
    found = ext.extract("Analista de Suporte", desc)
    assert "Hardware" in found
    assert "Inglês" not in found


def test_extrai_tecnologias_recentemente_adicionadas(ext):
    desc = (
        "Noções de Kubernetes e Argo CD, Temporal.io, Camunda, Retool e WireMock. "
        "Inglês intermediário e espanhol."
    )
    found = ext.extract("Dev", desc)
    assert {"Kubernetes", "ArgoCD", "Temporal.io", "Camunda",
            "Retool", "WireMock", "Inglês", "Espanhol"} <= set(found)


def test_extrai_stack_ios_da_evoluservices(ext):
    # Vaga da Evoluservices: iOS nativo com Swift, libs e MVVM.
    desc = (
        "Aplicações em iOS nativo escritas em Swift, utilizando Storyboard, "
        "Alamofire, ReactiveSwift e Firebase. Criação e manutenção de testes "
        "unitários. Padrões de arquitetura (MVVM). TDD e BDD."
    )
    found = ext.extract("Desenvolvedora iOS", desc)
    assert {"Swift", "iOS", "Storyboard", "Alamofire", "ReactiveSwift",
            "Firebase", "Testes Automatizados", "MVVM", "TDD", "BDD"} <= set(found)


def test_storyboard_de_ux_nao_conta_como_ferramenta_ios(ext):
    # "Ilustrar ideias de design por meio de storyboards" e tecnica de UX.
    desc = (
        "Ilustrar ideias de design por meio de storyboards, fluxos de "
        "processo e mapas de sites. Desenvolver em React e JavaScript."
    )
    found = ext.extract("Desenvolvedor Front-end JR", desc)
    assert "Storyboard" not in found


def test_llama_cpp_nao_conta_como_cpp(ext):
    # "llama.cpp" vira "llama cpp" na normalizacao e casava com o alias
    # "cpp" da linguagem C++.
    desc = "Execucao local de modelos abertos (ollama, vllm ou llama.cpp)."
    found = ext.extract("Desenvolvedor FullStack", desc)
    legitimas = ext.extract("Dev", "Conhecimento de C++.")

    assert "C++" not in found
    assert "C++" in legitimas


def test_extrai_certificacoes_sla_e_oci_da_mv(ext):
    # Vaga da MV Saude Digital: CSM/PSM, governanca de SLA e OCI ficavam de fora.
    desc = (
        "Governança de SLA. Metodologias ágeis (Scrum, Kanban). CSM. PSM. "
        "Cloud (AWS, OCI ou GCP). Integrações via APIs REST. Jira."
    )
    found = ext.extract("Coordenador Sistemas Junior", desc)
    assert {"Certificações Ágeis", "SLA", "OCI", "AWS", "GCP", "API REST", "Jira"} <= set(found)


def test_extrai_requisitos_genericos_de_engenharia(ext):
    desc = (
        "Requisitos: lógica de programação, qualidade de software, "
        "engenharia de software e métodos ágeis."
    )
    found = ext.extract("Dev", desc)
    assert {"Lógica de Programação", "Qualidade de Software",
            "Engenharia de Software", "Metodologias Ágeis"} <= set(found)


def test_complexidade_generica_nao_vira_algoritmos(ext):
    # "requisições de baixa complexidade" nao e complexidade algoritmica.
    found = ext.extract(
        "Analista", "Tratar incidentes e requisições de baixa complexidade."
    )

    assert "Algoritmos" not in found


def test_https_de_link_nao_vira_criptografia(ext):
    found = ext.extract("Analista", "Saiba mais em https://exemplo.com/pagina")

    assert "Criptografia" not in found


def test_extrai_conceitos_genericos_de_dados(ext):
    desc = (
        "Análise de dados, qualidade de dados, conceitos de bancos de dados "
        "e processos de automação."
    )
    found = ext.extract("Analista de Dados Júnior", desc)
    assert {"Análise de Dados", "Qualidade de Dados", "Banco de Dados",
            "Automação"} <= set(found)


def test_extrai_skills_adicionadas_na_revisao_de_cobertura(ext):
    desc = (
        "Usar Node-RED e arquitetura de dados Bronze, Silver e Gold em um "
        "lakehouse. Possuir certificação CTFL (ISTQB Foundation Level), "
        "conhecimento de SOQL, Gherkin, Azure DevOps e Businessmap/Kanbanize."
    )
    found = ext.extract("Analista de Tecnologia", desc)
    assert {
        "Node-RED", "Arquitetura de Dados", "CTFL (ISTQB Foundation Level)",
        "SOQL", "Gherkin", "Azure DevOps", "Businessmap/Kanbanize",
    } <= set(found)


def test_extrai_atividades_de_suporte_da_vaga_embelleze(ext):
    desc = (
        "Auxiliar na manutencao de equipamentos e redes. Acompanhar chamados "
        "para garantir o funcionamento da infraestrutura de TI. Apoiar na "
        "seguranca da informacao e backupsVaga Presencial."
    )
    found = ext.extract("Estagio em TI", desc)
    assert {
        "Hardware", "Redes de Computadores", "Gestão de Chamados",
        "Infraestrutura de TI", "Segurança da Informação", "Backup",
    } <= set(found)


def test_extrai_api_e_planilhas_genericas_da_vaga_omie(ext):
    desc = "Conhecimento em integrações via API ou planilhas será um diferencial."

    found = ext.extract("Analista Júnior", desc)

    assert {"APIs", "Planilhas"} <= set(found)


def test_extrai_atividades_especificas_de_suporte_gupy(ext):
    desc = (
        "Análise de alarmes, diagnóstico e troubleshooting de redes. "
        "Conhecimento de microinformática e sistemas operacionais. Abertura de tickets. "
        "Atender usuários - 1º nível - e fazer abertura de incidentes. "
        "Manutenções preventivas em hardwares e equipamentos de informática. "
        "Registrar as solicitações no sistema de chamados e montar racks."
    )
    found = ext.extract("Técnico de Suporte", desc)

    assert {
        "Redes de Computadores", "Gestão de Chamados", "Suporte N1/N2",
        "Manutenção Preventiva", "Hardware", "Microinformática",
        "Sistemas Operacionais",
    } <= set(found)


def test_sem_texto_devolve_lista_vazia(ext):
    vazio = ext.extract("")
    titulo_sem_descricao = ext.extract("Analista Júnior", "")

    assert vazio == []
    assert titulo_sem_descricao == []


def test_resultado_sem_repeticao_e_ordenado(ext):
    found = ext.extract("Dev Python", "Python, python e mais Python. Também AWS.")
    assert found == sorted(found)
    assert found.count("Python") == 1


def test_attach_skills_preenche_o_campo():
    jobs = [Job(source="t", external_id="1", title="Dev Jr",
                description="Rotina com Java, Spring e Docker.")]
    attach_skills(jobs)
    assert {"Java", "Spring", "Docker"} <= set(jobs[0].skills)


def test_skills_by_area_agrupa_e_ordena():
    jobs = [
        Job(source="t", external_id="1", title="a", area="Data", skills=["SQL", "Python"]),
        Job(source="t", external_id="2", title="b", area="Data", skills=["SQL"]),
        Job(source="t", external_id="3", title="c", area="Backend", skills=["Java"]),
    ]
    result = skills_by_area(jobs)
    assert result["Data"][0] == ("SQL", 2)
    assert result["Backend"] == [("Java", 1)]


def test_skills_by_area_ignora_area_sem_skills():
    jobs = [Job(source="t", external_id="1", title="a", area="QA", skills=[])]

    result = skills_by_area(jobs)

    assert "QA" not in result


def test_jobs_with_skills_by_area():
    """Base dos percentuais: nem toda vaga informa tecnologia."""
    jobs = [
        Job(source="t", external_id="1", title="a", area="Data", skills=["SQL"]),
        Job(source="t", external_id="2", title="b", area="Data", skills=[]),
        Job(source="t", external_id="3", title="c", area="Data", skills=["Python"]),
        Job(source="t", external_id="4", title="d", area="Backend", skills=[]),
    ]
    base = jobs_with_skills_by_area(jobs)
    assert base["Data"] == 2  # e não 3
    assert "Backend" not in base  # nenhuma vaga informa tecnologia


def test_jobs_with_skills_by_area_lista_vazia():
    result = jobs_with_skills_by_area([])

    assert result == {}


def test_overall_skill_counts():
    jobs = [
        Job(source="t", external_id="1", title="a", skills=["SQL", "Python"]),
        Job(source="t", external_id="2", title="b", skills=["SQL"]),
    ]

    result = overall_skill_counts(jobs)

    assert result[0] == ("SQL", 2)


def test_skills_vao_para_o_csv_como_texto():
    job = Job(source="t", external_id="1", title="a", skills=["SQL", "Python"])

    row = job.to_row()

    assert row["skills"] == "SQL, Python"

def test_contextos_descarte_ignora_mencao_a_empresa(ext):
    # 'Hardware' nao deve contar quando fala da empresa contratante.
    texto = ('Vaga de suporte. Uma gigante brasileira de hardware e servicos, '
             'referencia em inovacao. Requisitos: conhecimento em redes.')

    found = ext.extract('Vaga', texto)

    assert 'Hardware' not in found


def test_contextos_descarte_ignora_nome_proprio(ext):
    found = ext.extract('Estagio', 'Vaga no Instituto Hardware BR.')

    assert 'Hardware' not in found


def test_contextos_descarte_mantem_menção_legitima(ext):
    texto = 'Tecnico: realizar manutencao de hardware e software. Instalar equipamentos.'

    found = ext.extract('Tecnico', texto)

    assert 'Hardware' in found
