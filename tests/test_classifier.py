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
    ],
)
def test_classifica_pelo_titulo(clf, title, expected):
    assert clf.classify(title).area == expected


def test_titulo_vale_mais_que_descricao(clf):
    # Descricao cita AWS/Kubernetes, mas o titulo e claramente frontend.
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


def test_titulo_dominante_vence_ruido_da_descricao(clf):
    # Descricao longa citando "dados" de passagem nao pode sequestrar a vaga.
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
    # "goiania" nao pode disparar a keyword "go"; "java" nao pode vir de "javascript"
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
    assert clf.is_tech(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "Estágio Syngenta 2026 - Holambra | Pesquisa e Desenvolvimento",
        "Estágio em Odontologia Digital",
        "Estágio em Pedagogia para Tecnologia Educacional",
        "Analista de Desenvolvimento de Negócios Jr",
        "Técnico de Segurança do Trabalho Júnior",
    ],
)
def test_tech_gate_exclui_contextos_nao_tech(clf, title):
    assert clf.is_tech(title) is False


def test_tech_gate_ignora_palavra_generica_na_descricao(clf):
    # Snippet de vaga administrativa citando "sistemas"/"dados" no meio do texto
    # nao pode transformar a vaga em vaga de tecnologia.
    assert clf.is_tech(
        "Analista Administrativo Junior",
        "Alimentar os sistemas da empresa e organizar os dados dos contratos.",
    ) is False


@pytest.mark.parametrize(
    "title",
    [
        "Desenvolvedor Júnior",
        "Técnico de Suporte Júnior",
        "Estágio em TI",
        "Analista de Sistemas Jr",
        "Estágio em Tecnologia",
    ],
)
def test_tech_gate_mantem_vagas_de_tecnologia(clf, title):
    assert clf.is_tech(title) is True


def test_tech_gate_usa_a_descricao_quando_o_titulo_e_generico(clf):
    assert clf.is_tech("Analista Júnior") is False
    assert clf.is_tech(
        "Analista Júnior", "Atuar com desenvolvimento de software em Python."
    ) is True


def test_suporte_tecnico_vai_para_area_propria(clf):
    assert clf.classify("Analista de Suporte Técnico Júnior").area == "Suporte/Infra"
    assert clf.classify("Técnico de Suporte Júnior").area == "Suporte/Infra"


def test_seguranca_nao_dispara_com_a_palavra_solta(clf):
    # Boilerplate de "normas de seguranca" nao pode virar vaga de Seguranca.
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


def test_score_all_ordena_por_pontuacao(clf):
    ranked = clf.score_all("Desenvolvedor Fullstack React e Node Júnior")
    assert ranked[0].score >= ranked[-1].score
    assert ranked[0].area == "Fullstack"
