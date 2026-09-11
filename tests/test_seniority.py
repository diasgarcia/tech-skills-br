from scraper.models import Job
from scraper.seniority import SeniorityFilter, canonicalize_seniority, filter_entry_level


def test_reconhece_variacoes_de_junior():
    flt = SeniorityFilter.from_file()
    titulos = [
        "Desenvolvedor Júnior",
        "Desenvolvedor Jr",
        "DESENVOLVEDOR JR.",
        "Analista de Dados Junior",
    ]

    result = [flt.label(titulo) for titulo in titulos]

    assert result == ["Júnior"] * 4


def test_reconhece_estagio_trainee_aprendiz():
    flt = SeniorityFilter.from_file()
    titulos = [
        "Estágio em Desenvolvimento de Software",
        "Estagiário de TI",
        "Programa de Trainee em Tecnologia",
        "Jovem Aprendiz - Suporte",
    ]

    result = [flt.label(titulo) for titulo in titulos]

    assert result == ["Estágio", "Estágio", "Trainee", "Aprendiz"]


def test_descarta_niveis_acima():
    flt = SeniorityFilter.from_file()
    titles = [
        "Desenvolvedor Fullstack .NET Pleno/Sênior - Remoto",
        "Engenheiro de Dados Sênior",
        "Tech Lead Backend",
        "Coordenador de TI",
        "Arquiteto de Soluções",
    ]

    result = [flt.label(title) for title in titles]

    assert result == [None] * len(titles)


def test_titulo_misto_passa_no_modo_padrao_e_cai_no_estrito():
    padrao = SeniorityFilter.from_file()
    estrito = SeniorityFilter.from_file(strict=True)
    titulo = "Desenvolvedor Java Júnior/Pleno"

    result = (padrao.label(titulo), estrito.label(titulo))

    assert result == ("Júnior", None)


def test_nao_casa_junior_dentro_de_outra_palavra():
    flt = SeniorityFilter.from_file()
    titulos = ["Analista de BI", "Gerente de Projetos"]

    result = [flt.label(titulo) for titulo in titulos]

    assert result == [None, None]


def test_n1_com_decimal_e_tier_de_suporte_nao_e_junior():
    flt = SeniorityFilter.from_file()
    titulos_invalidos = [
        "Analista de Suporte Técnico N1.5 Pleno",
        "Analista de Suporte Técnico N1.5 Sênior",
        "Analista de Redes (N1.5)",
        "Técnico de Suporte Nível 1.5 Pleno",
    ]
    titulo_valido = "Analista de Segurança da Informação - N1 (12x36 - Diurno)"

    invalidos = [flt.label(titulo) for titulo in titulos_invalidos]
    valido = flt.label(titulo_valido)

    assert invalidos == [None] * len(titulos_invalidos)
    # N1 "puro" continua valendo, mesmo com parentese de escala depois.
    assert valido == "Júnior"


def test_senioridade_declarada_pela_fonte_vence_o_titulo():
    """Título sem marca de nível não descarta a vaga se a fonte já sabe o nível."""
    jobs = [
        Job(source="solides", external_id="1",
            title="Programador(a) PHP", seniority="Júnior"),
        Job(source="solides", external_id="2",
            title="Analista de Sistemas", seniority="Estágio"),
    ]

    kept = filter_entry_level(jobs)

    assert [j.external_id for j in kept] == ["1", "2"]
    assert kept[0].seniority == "Júnior"


def test_sem_senioridade_da_fonte_cai_no_regex_do_titulo():
    jobs = [
        Job(source="gupy", external_id="1", title="Programador(a) PHP"),
        Job(source="gupy", external_id="2", title="Programador(a) PHP Júnior"),
    ]

    kept = filter_entry_level(jobs)

    assert [j.external_id for j in kept] == ["2"]


def test_filter_entry_level_preenche_rotulo():
    jobs = [
        Job(source="t", external_id="1", title="Desenvolvedor Júnior"),
        Job(source="t", external_id="2", title="Desenvolvedor Sênior"),
        Job(source="t", external_id="3", title="Estágio em Dados"),
    ]

    kept = filter_entry_level(jobs)

    assert [j.external_id for j in kept] == ["1", "3"]
    assert kept[0].seniority == "Júnior"
    assert kept[1].seniority == "Estágio"


def test_canonicalize_senioridade():
    entradas = ["Estagiário", "Estágio", "Trainee", "Aprendiz", "Júnior", "Coordenador", ""]

    result = [canonicalize_seniority(entrada) for entrada in entradas]

    assert result[:5] == ["Estágio", "Estágio", "Trainee", "Aprendiz", "Júnior"]
    # Variante desconhecida passa direto: nada e inventado.
    assert result[5:] == ["Coordenador", ""]


def test_filter_entry_level_canonicaliza_rotulo_da_fonte():
    """'Estagiario' vindo do filtro nativo do portal vira 'Estágio'."""
    jobs = [
        Job(source="infojobs", external_id="1",
            title="Técnico de Suporte", seniority="Estagiário"),
    ]

    kept = filter_entry_level(jobs)

    assert len(kept) == 1
    assert kept[0].seniority == "Estágio"
