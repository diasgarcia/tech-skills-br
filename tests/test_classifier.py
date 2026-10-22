import pytest

from scraper.classifier import AreaClassifier, classify_jobs, filter_tech
from scraper.models import Job


@pytest.fixture(scope="module")
def clf():
    return AreaClassifier.from_file()


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Desenvolvedor Front-End Júnior", "Frontend"),
        ("Desenvolvedor React Jr", "Frontend"),
        ("Desenvolvedor Back-End Java Júnior", "Backend"),
        ("Engenheiro de Dados Júnior", "Data"),
        ("Analista de Dados Jr", "Data"),
        ("Estágio em Business Intelligence", "Data"),
        ("Desenvolvedor Mobile Flutter Júnior", "Mobile"),
        ("Desenvolvedor Android Jr", "Mobile"),
        ("Analista DevOps Júnior", "DevOps"),
        ("Estágio em Quality Assurance", "QA"),
        ("Analista de Testes Júnior", "QA"),
        ("Desenvolvedor Fullstack Júnior", "Fullstack"),
        ("Estágio em Segurança da Informação", "Segurança"),
        ("Administrador de Banco de Dados (DBA) Júnior", "Data"),
        ("Analista de RPA Júnior", "Backend"),
        ("Analista de Telecom Júnior", "Infraestrutura / Redes"),
        ("Desenvolvedor de Jogos Júnior", "Engenharia de Software"),
        ("Analista de Integração de Sistemas Júnior", "Engenharia de Software"),
        ("Mainframe Tester Júnior", "QA"),
        ("Engenheiro de Software Embarcado Júnior", "Hardware / Eletrônica"),
        ("Desenvolvedor de Sistemas Embarcados Júnior", "Hardware / Eletrônica"),
        ("Suporte de Aplicações Júnior", "Suporte Técnico"),
    ],
)
def test_classifica_pelo_titulo(clf, title, expected):
    result = clf.classify(title)

    assert result.area == expected


def test_titulo_vale_mais_que_descricao(clf):
    result = clf.classify(
        "Desenvolvedor Front-End Júnior",
        "Nosso ambiente roda em AWS com Kubernetes e Docker.",
    )
    assert result.area == "Frontend"


def test_descricao_decide_quando_titulo_e_generico(clf):
    result = clf.classify(
        "Desenvolvedor Júnior",
        "Vaga para atuar com pipelines de ETL, SQL, Airflow e data warehouse.",
    )
    assert result.area == "Data"


def test_integracao_na_descricao_classifica_titulo_generico(clf):
    result = clf.classify(
        "Analista de TI Jr",
        "Configurar e validar integrações entre sistemas, APIs e logs.",
    )
    assert result.area == "Engenharia de Software"


def test_titulo_dominante_vence_ruido_da_descricao(clf):
    result = clf.classify(
        "Estágio em Governança de TI",
        "Apoiar a governanca, tratar dados cadastrais e zelar pela protecao "
        "de dados conforme a LGPD, com apoio de planilhas e relatorios.",
    )
    assert result.area != "Data"


def test_titulo_dominante_escolhe_entre_areas_do_titulo(clf):
    result = clf.classify(
        "Estágio em desenvolvimento Android - Kotlin/Java",
        "Trabalhamos com SQL, dados e relatorios de BI no dia a dia.",
    )
    assert result.area == "Mobile"


def test_keyword_fraca_isolada_na_descricao_nao_define_area(clf):
    result = clf.classify("Estagiário de Escritório em TI", "Organizar dados.")
    assert result.area == clf.fallback_area


def test_titulo_sem_sinal_cai_no_fallback(clf):
    result = clf.classify("Jovem Aprendiz Administrativo")
    assert result.area == clf.fallback_area
    assert result.score == 0.0


def test_keyword_nao_casa_parcialmente(clf):
    scores = {s.area: s.score for s in clf.score_all("Vaga em Goiania")}
    assert scores.get("DevOps", 0) == 0
    assert scores.get("Backend", 0) == 0


def test_classify_jobs_preenche_campos():
    jobs = [Job(source="t", external_id="1", title="Engenheiro de Dados Júnior")]
    classify_jobs(jobs)
    assert jobs[0].area == "Data"
    assert jobs[0].area_score > 0
    assert "engenheiro de dados" in jobs[0].area_matches


@pytest.mark.parametrize(
    "title",
    [
        "Analista Contábil Jr",
        "Analista Fiscal Júnior",
        "Analista Administrativo Financeiro Jr.",
        "Analista Comercial Jr",
        "Jovem Aprendiz - Recepção",
        "Analista de Ouvidoria Junior",
        "Analista Administrativo I",
        "Analista de Middle Office Júnior",
    ],
)
def test_tech_gate_descarta_vagas_fora_de_tecnologia(clf, title):
    result = clf.is_tech(title)

    assert result is False


@pytest.mark.parametrize(
    "title",
    [
        "Estágio Syngenta 2026 - Holambra | Pesquisa e Desenvolvimento",
        "Estágio em Odontologia Digital",
        "ESTÁGIO SISTEMAS BIOMÉDICOS - BOS BANCO DE OLHOS",
        "Analista de Qualidade Júnior",
        "Programador de Carga Júnior",
        "Estágio em Pedagogia para Tecnologia Educacional",
        "Analista de Desenvolvimento de Negócios Jr",
        "Técnico de Segurança do Trabalho Júnior",
        "Programador de Logística de Vendas Jr",
        "Assistente Administrativo (Controle e Processos de TI)",
        "Pesquisador Tecnologia Farmacêutica Júnior",
        "Analista de Cultura e Desenvolvimento Júnior",
        "Analista de Gestão de Contratos Jr - Telecomunicações",
        "Aprendiz - Monitoração Redes Clientes",
        "Operador de Programação Logística I",
        "Auxiliar de Encanador de Redes (Serviços Comerciais)",
        "Encanadora de Redes Júnior",
    ],
)
def test_tech_gate_exclui_contextos_nao_tech(clf, title):
    result = clf.is_tech(title)

    assert result is False


@pytest.mark.parametrize(
    "description",
    [
        "",
        "Instalação de hidrômetros, manutenção de redes e conexões hidráulicas.",
        "Registrar ordens de serviço no software e prestar suporte técnico às equipes de campo.",
    ],
)
def test_tech_gate_descarta_encanador_mesmo_com_termos_tecnicos(clf, description):
    title = "Auxiliar de Encanador de Redes (Serviços Comerciais)"

    result = clf.is_tech(title, description)

    assert result is False


def test_tech_gate_mantem_redes_de_ti_em_empresa_de_saneamento(clf):
    title = "Analista de Redes Júnior - GS Inima Brasil"
    description = "Configurar roteadores e redes de computadores usadas pelas equipes de encanadores."

    result = clf.is_tech(title, description)

    assert result is True


@pytest.mark.parametrize(
    "description",
    [
        "",
        "Apoiar propostas comerciais, cotações e atendimento. Requisitos: "
        "Administração ou Sistemas de Informação, Pacote Office, CRM e ERP.",
        "A empresa desenvolve software, usa SQL e banco de dados. "
        "A função apoia o time de vendas com propostas e cotações.",
    ],
)
def test_tech_gate_bloqueia_suporte_administrativo_comercial(clf, description):
    title = "Estágio em Suporte Administrativo Comercial - Presencial Petrópolis"

    result = clf.is_tech(title, description)

    assert result is False


@pytest.mark.parametrize(
    "title",
    [
        "Inspetor de Qualidade N1 - Uberlândia/MG",
        "EXAMINADOR(A) I (INSPEÇÃO SOLDA N1)",
        "TÉCNICO ELETROMECÂNICO N1",
        "Técnico Químico JR - Engenharia e Tecnologia",
        "Analista de Desenvolvimento Farmacotécnico Júnior",
        "Sous Chef de Desenvolvimento Jr",
        "Psicólogo Júnior",
        "Psicóloga Júnior",
        "Estágio em Educação Física e Esporte",
        "Estágio para academia de musculação",
        "Assistente de SIF Nível 1",
        "Analista de Segurança de Alimentos Jr",
        "Estagiário de RH",
        "Estágio RH (Recrutamento e Seleção)",
        "Trainee RH Generalista | Desenvolvimento para Coordenação de RH",
        "Analista de Recrutamento e Seleção Junior",
        "Estágio em Comunicação e Marketing",
        "Pessoa Analista de PR Junior - Tecnologia",
        "Estágio Jurídico (Cível e Consumidor)",
        "Estagiário/a Jurídico | Tecnologia Privacidade e Proteção de Dados",
        "Estágio em Direito",
        "Assistente Jurídico-Operacional com Inteligência Artificial",
        "Estagiário Comercial - Travel Tech & Educação",
        "Analista Comercial Junior – Consultoria de TI",
        "Assistente Financeiro Sênior - Restaurante",
        "Analista Administrativo Financeiro Jr | Desenvolvimento Imobiliário",
        "Assistente administrativo para imobiliaria com conhecimento sistema nido",
        "Assistente Administrativo - Desenvolvimento Agronômico",
        "Trainee em Desenvolvimento Imobiliário",
        "Jovem Aprendiz | Desenvolvimento Imobiliário",
        "Jovem Aprendiz Administrativo | Desenvolvimento Imobiliário",
        "Estágio em Engenharia Desenvolvimento Cabines",
        "Trainee de Engenharia (Sistemas Mecânicos de Instalações)",
        "Assistente Técnico de Campo – Especialidade Mecânica",
        "CONDUTOR SISTEMAS MANUFATURA I",
        "Planejador Processo Jr - Programação de Ferramentas",
        "Programador de Produção Junior",
        "Operador Programação Logística I",
        "Analista de Transportes JR | Programação de Veículos",
        "Auxiliar de Sistema de Biogás",
        "Assistente de Projetos e Vendas",
        "Auxiliar de Qualidade (Satisfação do cliente) - Telecomunicações",
        "Estagiário de Projetos (Fábrica)",
        "Estágio Administrativo de Infraestrutura",
        "Estagiário na área de Engenharia de Produção",
    ],
)
def test_tech_gate_descarta_funcoes_nao_tech_observadas_em_outubro(clf, title):
    description = "A empresa usa banco de dados e presta suporte técnico."

    result = clf.is_tech(title, description)

    assert result is False


@pytest.mark.parametrize(
    "title,description",
    [
        ("Estágio em Suporte Administrativo", "Suporte em processos administrativos e pedidos de compra."),
        ("Analista de Suporte Administrativo JR", "Apoiar processos financeiros relacionados a pagamentos e contratos."),
        ("Analista de Suporte Operacional Júnior", "Atuar na preservação dos bens patrimoniais da empresa."),
        ("Analista de Engenharia Jr", "Elaborar projetos de centrais de gás e acompanhar instalações."),
        ("Analista de Programação Júnior", "Planejar estoques e programação de materiais para a produção."),
        ("Analista de Produto JR (Desenvolvimento em CAD)", "Projetar componentes para processos de usinagem."),
        ("Estágio em Comunicação | Tecnologia", "Apoiar a equipe de relações públicas na comunicação das marcas."),
        ("Controlador(a) Operação de Sistema I", "Operar o sistema elétrico de potência do estado."),
        ("Estágio em suporte à produção - Melhoria contínua", "Melhorar processos de usinagem e medir tempos de ciclo."),
        ("Estágio de Sistema de Gestão", "Apoiar rotinas do sistema de gestão industrial e reuniões de produção."),
        ("Estágio em Integrated Management System (Quality Assurance)", "Engenharia (todas as modalidades), Farmácia ou Química."),
        ("Analista de Sistema de Gestão Integrada I", "Realizar o gerenciamento dos resíduos da unidade."),
        ("Pessoa Auxiliar de Sistema Gestão Integrada", "Controlar informações relacionadas a produtos químicos."),
        ("Analista de Qualidade e Melhoria Contínua", "Realizar análises de fécula de mandioca no laboratório."),
        ("Estagiário na área de Qualidade", "Realizar testes das matérias-primas e acompanhar a fábrica."),
        ("Estagiário na área de Administração de Empresas", "Realizar publicação de anúncios nos marketplaces."),
        ("Estagiário na área de Arquitetura", "Pesquisar zoneamento e legislação urbana para terrenos."),
        ("Assistente Administrativo", "Registrar demandas da Assessoria Jurídica e organizar documentos."),
    ],
)
def test_tech_gate_descarta_contextos_nao_tech_observados_em_outubro(clf, title, description):
    result = clf.is_tech(title, description)

    assert result is False


@pytest.mark.parametrize(
    "title,description",
    [
        ("Analista de Suporte Administrativo JR - PCD", "Suporte a infraestrutura e periféricos, gestão de acessos e help desk nível 1."),
        ("Assistente administrativo de TI", "Configurar Wi-Fi, redes, computadores e dispositivos móveis."),
        ("Auxiliar Administrativo - Suporte Técnico", "Instalar drivers e equipamentos e prestar suporte remoto aos usuários do ERP."),
        ("Estágio em Suporte Operacional", "Monitorar redes de computadores, TCP/IP e GPON."),
        ("Assistente Fiscal de Tecnologia", "Parametrizar SAP Business One, configurar addons e testar melhorias para usuários."),
        ("Assistente de Sistemas da Controladoria Jurídica", "Administrar sistemas, desenvolver relatórios com SQL e automatizar rotinas com Python."),
        ("Assistente de Qualidade de Software | QA", "Executar testes de software e registrar defeitos."),
        ("Analista de Qualidade e Processos JR", "Criar dashboards em Power BI e automações no ServiceNow."),
        ("Analista em Sistemas de Saúde e Segurança I", "Integrar sistemas, tratar dados com SQL e desenvolver automações."),
        ("Auxiliar de Remanufatura", "Diagnosticar hardware e reparar equipamentos de tecnologia da informação."),
        ("Estágio Setor Patrimônio", "Atualizar firmware e testar equipamentos de redes de computadores."),
        ("Estágio em TI aplicada à Automação Industrial", "Criar APIs com Python, Node.js e interfaces React para CLPs."),
        ("Desenvolvedor de Sistemas de RH Júnior", "Desenvolver software de recrutamento com Python e SQL."),
        ("Estágio em Comunicação de Dados", "Configurar redes de computadores e roteadores TCP/IP."),
        ("Estágio em Desenvolvimento em CAD para Eletrônica", "Projetar placas de circuito impresso e hardware embarcado."),
    ],
)
def test_tech_gate_preserva_funcoes_tech_com_titulos_ambiguos(clf, title, description):
    result = clf.is_tech(title, description)

    assert result is True


@pytest.mark.parametrize(
    "title,description",
    [
        (
            "Analista de Expansão de Redes Jr",
            "Prospecção e expansão comercial da carteira de clientes.",
        ),
        (
            "Analista de Implantação Júnior",
            "Atuação em corretora de seguros e envio do primeiro faturamento.",
        ),
        (
            "Auxiliar de Tecnologia da Informação",
            "Oportunidade administrativa com conhecimento de legislação marítima.",
        ),
        (
            "Instrutor de Nível Superior Jr - Automação Industrial",
            "Aplicar a metodologia SENAI e ministrar aulas e treinamentos.",
        ),
    ],
)
def test_tech_gate_exclui_titulo_ambiguo_pelo_contexto(clf, title, description):
    result = clf.is_tech(title, description)

    assert result is False


@pytest.mark.parametrize(
    "title,description",
    [
        (
            "Analista de Expansão de Redes Jr",
            "Planejar enlaces, roteadores e redes de telecomunicações.",
        ),
        (
            "Analista de Implantação Júnior",
            "Implantar software ERP, configurar APIs e banco de dados.",
        ),
        (
            "Auxiliar de Tecnologia da Informação",
            "Prestar suporte técnico, configurar computadores e redes.",
        ),
    ],
)
def test_tech_gate_mantem_titulo_ambiguo_em_contexto_tech(clf, title, description):
    result = clf.is_tech(title, description)

    assert result is True


def test_tech_gate_ignora_palavra_generica_na_descricao(clf):
    result = clf.is_tech(
        "Analista Administrativo Junior",
        "Alimentar os sistemas da empresa e organizar os dados dos contratos.",
    )

    assert result is False


@pytest.mark.parametrize(
    "title",
    [
        "Desenvolvedor Júnior",
        "Técnico de Suporte Júnior",
        "Estágio em TI",
        "Analista de Sistemas Jr",
        "Estágio em Tecnologia",
        "Administrador de Banco de Dados (DBA) Júnior",
        "Analista de RPA Júnior",
        "Analista de Telecom Júnior",
        "Suporte de Aplicações Júnior",
    ],
)
def test_tech_gate_mantem_vagas_de_tecnologia(clf, title):
    result = clf.is_tech(title)

    assert result is True


def test_tech_gate_usa_a_descricao_quando_o_titulo_e_generico(clf):
    sem_descricao = clf.is_tech("Analista Júnior")
    com_descricao = clf.is_tech(
        "Analista Júnior", "Atuar com desenvolvimento de software em Python."
    )

    assert sem_descricao is False
    assert com_descricao is True


def test_suporte_tecnico_vai_para_area_propria(clf):
    titulos = ["Analista de Suporte Técnico Júnior", "Técnico de Suporte Júnior"]

    areas = [clf.classify(titulo).area for titulo in titulos]

    assert areas == ["Suporte Técnico", "Suporte Técnico"]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Analista de Suporte N1 Junior", "Service Desk / Help Desk"),
        ("Técnico de Suporte Júnior Nível 1", "Service Desk / Help Desk"),
        ("Jovem Aprendiz | Service Desk - Suporte de TI", "Service Desk / Help Desk"),
        ("Estagiário de TI – Infraestrutura", "Infraestrutura / Redes"),
        ("Estagiário de suporte técnico TI (Infraestrutura e Redes)", "Infraestrutura / Redes"),
        ("Técnico de Suporte Júnior VOLANTE", "Field Service / Hardware"),
        ("Técnico Suporte Júnior - Field Dedicado", "Field Service / Hardware"),
    ],
)
def test_titulo_especifico_vence_suporte_generico(clf, title, expected):
    result = clf.classify(title)

    assert result.area == expected


@pytest.mark.parametrize(
    "title",
    [
        "Estagiário(a) Atendimento Aos Estudantes",
        "Analista de Gestão de Saúde Jr",
        "Atendente de SAC",
        "Suporte Técnico - Cobrança/Retenção",
    ],
)
def test_tech_gate_descarta_nao_tech_do_suporte(clf, title):
    result = clf.is_tech(title)

    assert result is False


def test_seguranca_nao_dispara_com_a_palavra_solta(clf):
    result = clf.classify(
        "Analista de Suporte Técnico Júnior",
        "Seguir as normas de seguranca da empresa e atender chamados de suporte.",
    )
    assert result.area != "Segurança"


def test_filter_tech_separa_as_duas_listas():
    jobs = [
        Job(source="t", external_id="1", title="Desenvolvedor Júnior"),
        Job(source="t", external_id="2", title="Analista Contábil Jr"),
    ]
    tech, non_tech = filter_tech(jobs)
    assert [j.external_id for j in tech] == ["1"]
    assert [j.external_id for j in non_tech] == ["2"]


def test_keyword_contida_em_outra_nao_pontua_duas_vezes(clf):
    """'suporte tecnico' contém 'suporte' -- o mesmo trecho não pode somar duas vezes."""
    scores = {s.area: s.score for s in clf.score_all("Suporte Técnico Júnior")}
    # peso_alto (4.0) x title_boost (3.0) = 12, e não 15 (12 + 3 do 'suporte' contido).
    assert scores["Suporte Técnico"] == 12.0


def test_frases_que_so_se_sobrepoem_em_parte_ainda_somam(clf):
    """A regra é contenção, não sobreposição: duas frases fortes distintas contam."""
    scores = {s.area: s.score for s in clf.score_all("Analista de Suporte Técnico Jr")}
    # 'analista de suporte' e 'suporte tecnico' compartilham uma palavra, mas
    # nenhuma está contida na outra -- são dois sinais fortes de verdade.
    assert scores["Suporte Técnico"] == 24.0



def test_titulo_backend_com_suporte_nao_vira_suporte(clf):
    """Caso real de portal com tags: a soma em dobro fazia Suporte vencer Backend."""
    resultado = clf.classify(
        "DESENVOLVEDOR BACKEND JÚNIOR - SUSTENTAÇÃO E SUPORTE TÉCNICO",
        "Tecnologias: API, Node.js, SQL, PostgreSQL.",
    )
    assert resultado.area == "Backend"


def test_ocorrencias_separadas_ainda_pontuam(clf):
    """A regra só ignora trecho sobreposto, não repetição em lugares diferentes."""
    scores = {s.area: s.score for s in clf.score_all("Suporte", "Precisa de SQL e ETL.")}
    assert scores["Data"] > 0


def test_score_all_ordena_por_pontuacao(clf):
    ranked = clf.score_all("Desenvolvedor Fullstack React e Node Júnior")
    assert ranked[0].score >= ranked[-1].score
    assert ranked[0].area == "Fullstack"
