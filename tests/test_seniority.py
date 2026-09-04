from scraper.models import Job
from scraper.seniority import SeniorityFilter, canonicalize_seniority, filter_entry_level


def test_reconhece_variacoes_de_junior():
    flt = SeniorityFilter.from_file()
    assert flt.label("Desenvolvedor Júnior") == "Júnior"
    assert flt.label("Desenvolvedor Jr") == "Júnior"
    assert flt.label("DESENVOLVEDOR JR.") == "Júnior"
    assert flt.label("Analista de Dados Junior") == "Júnior"


def test_reconhece_estagio_trainee_aprendiz():
    flt = SeniorityFilter.from_file()
    assert flt.label("Estágio em Desenvolvimento de Software") == "Estágio"
    assert flt.label("Estagiário de TI") == "Estágio"
    assert flt.label("Programa de Trainee em Tecnologia") == "Trainee"
    assert flt.label("Jovem Aprendiz - Suporte") == "Aprendiz"


def test_descarta_niveis_acima():
    flt = SeniorityFilter.from_file()
    for title in [
        "Desenvolvedor Fullstack .NET Pleno/Sênior - Remoto",
        "Engenheiro de Dados Sênior",
        "Tech Lead Backend",
        "Coordenador de TI",
        "Arquiteto de Soluções",
    ]:
        assert flt.label(title) is None, title


def test_titulo_misto_passa_no_modo_padrao_e_cai_no_estrito():
    padrao = SeniorityFilter.from_file()
    estrito = SeniorityFilter.from_file(strict=True)
    titulo = "Desenvolvedor Java Júnior/Pleno"
    assert padrao.label(titulo) == "Júnior"
    assert estrito.label(titulo) is None


def test_nao_casa_junior_dentro_de_outra_palavra():
    flt = SeniorityFilter.from_file()
    assert flt.label("Analista de BI") is None
    assert flt.label("Gerente de Projetos") is None


def test_n1_com_decimal_e_tier_de_suporte_nao_e_junior():
    flt = SeniorityFilter.from_file()
    assert flt.label("Analista de Suporte Técnico N1.5 Pleno") is None
    assert flt.label("Analista de Suporte Técnico N1.5 Sênior") is None
    assert flt.label("Analista de Redes (N1.5)") is None
    assert flt.label("Técnico de Suporte Nível 1.5 Pleno") is None
    # N1 "puro" continua valendo, mesmo com parentese de escala depois.
    assert flt.label("Analista de Segurança da Informação - N1 (12x36 - Diurno)") == "Júnior"


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
    assert [j.external_id for j in filter_entry_level(jobs)] == ["2"]


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
    assert canonicalize_seniority("Estagiário") == "Estágio"
    assert canonicalize_seniority("Estágio") == "Estágio"
    assert canonicalize_seniority("Trainee") == "Trainee"
    assert canonicalize_seniority("Aprendiz") == "Aprendiz"
    assert canonicalize_seniority("Júnior") == "Júnior"
    # Variante desconhecida passa direto: nada e inventado.
    assert canonicalize_seniority("Coordenador") == "Coordenador"
    assert canonicalize_seniority("") == ""


def test_filter_entry_level_canonicaliza_rotulo_da_fonte():
    """'Estagiario' vindo do filtro nativo do portal vira 'Estágio'."""
    jobs = [
        Job(source="infojobs", external_id="1",
            title="Técnico de Suporte", seniority="Estagiário"),
    ]
    kept = filter_entry_level(jobs)
    assert len(kept) == 1
    assert kept[0].seniority == "Estágio"
