import pytest

from scraper.export import build_workplace_ranking
from scraper.models import Job, infer_linkedin_workplace, infer_workplace, normalize_workplace
from scraper.sources.vagas_com import VagasComSource


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("remote", "Remoto"),
        ("hybrid", "Híbrido"),
        ("on-site", "Presencial"),
        ("Remoto", "Remoto"),
        ("100% Home Office", "Remoto"),
        ("Híbrido", "Híbrido"),
        ("presencial", "Presencial"),
        ("", "Não informado"),
        (None, "Não informado"),
        ("qualquer coisa", "Não informado"),
    ],
)
def test_normalize_workplace(raw, expected):
    result = normalize_workplace(raw)

    assert result == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("100% Home Office", "Remoto"),
        ("Rio de Janeiro / RJ", "Não informado"),
        ("", "Não informado"),
    ],
)
def test_vagas_afirma_remoto_e_nao_adivinha_o_resto(raw, expected):
    # O card do Vagas.com nao distingue hibrido de presencial: so o remoto
    # aparece explicitamente ("100% Home Office").
    result = VagasComSource._workplace(raw)

    assert result == expected


def test_ranking_respeita_a_ordem_remoto_hibrido_presencial():
    jobs = [
        Job(source="t", external_id="1", title="a", workplace_type="Presencial"),
        Job(source="t", external_id="2", title="b", workplace_type="Remoto"),
        Job(source="t", external_id="3", title="c", workplace_type="Presencial"),
        Job(source="t", external_id="4", title="d", workplace_type="Híbrido"),
    ]

    ranking = build_workplace_ranking(jobs)

    assert [r["modalidade"] for r in ranking] == ["Remoto", "Híbrido", "Presencial"]
    assert ranking[2]["vagas"] == 2
    assert ranking[2]["percentual"] == 50.0


def test_ranking_omite_modalidade_sem_vagas():
    jobs = [Job(source="t", external_id="1", title="a", workplace_type="Remoto")]

    ranking = build_workplace_ranking(jobs)

    assert [r["modalidade"] for r in ranking] == ["Remoto"]


def test_ranking_trata_campo_vazio_como_nao_informado():
    jobs = [Job(source="t", external_id="1", title="a", workplace_type="")]

    ranking = build_workplace_ranking(jobs)

    assert ranking[0]["modalidade"] == "Não informado"


def test_ranking_lista_vazia():
    result = build_workplace_ranking([])

    assert result == []


@pytest.mark.parametrize(
    "explicit,location,title,description,esperado",
    [
        ("hybrid", "SP", "", "", "Híbrido"),
        ("", "São Paulo, SP (Remoto)", "", "", "Remoto"),
        ("", "São Paulo, SP", "Dev Júnior", "Atuação 100% presencial no escritório", "Presencial"),
        ("", "Curitiba, PR", "Estágio TI", "Modelo de trabalho híbrido com 2 dias presenciais", "Híbrido"),
        ("", "Recife, PE", "Dev Jr", "Vaga 100% Home Office", "Remoto"),
        ("", "Brasil", "Junior Software Engineer (Remote)", "", "Remoto"),
        ("", "Goiânia, GO", "Dev Python Junior", "Modalidade 100% remota - trabalhe de qualquer lugar", "Remoto"),
        ("", "Goiânia, GO", "Dev Python Junior", "Time trabalhando remotamente em cargos globais", "Remoto"),
        (
            "", "Florianópolis, SC", "Estagiário de TI",
            "Atuação em regime presencial. Conhecimento em ferramentas de suporte remoto.",
            "Presencial",
        ),
        (
            "", "Betim, MG", "Técnico de Suporte de TI",
            "Atendimento e suporte técnico presencial e remoto. Modalidade: Presencial.",
            "Presencial",
        ),
        (
            "", "Rio de Janeiro e Região", "Analista de Suporte de T.I. Jr.",
            "Prestar suporte técnico de Nível 2 presencial e remoto aos colaboradores.",
            "Presencial",
        ),
        (
            "", "São Paulo, SP", "Analista de Sistemas",
            "Modelo de trabalho presencial e remoto, com dois dias no escritório.",
            "Híbrido",
        ),
        (
            "", "São Paulo, SP", "Analista de Suporte - Presencial",
            "Texto institucional sobre o modelo híbrido da empresa.",
            "Presencial",
        ),
        (
            "", "São Paulo, SP", "Desenvolvedor Júnior - Remoto",
            "O escritório também trabalha de forma híbrida.",
            "Remoto",
        ),
        ("", "", "Dev Jr", "", "Não informado"),
    ],
)
def test_infer_workplace(explicit, location, title, description, esperado):
    result = infer_workplace(explicit, location, title, description)

    assert result == esperado


def test_linkedin_sem_rotulo_nao_converte_cidade_em_presencial():
    result = infer_linkedin_workplace(
        "Presencial",
        False,
        location="São Paulo, SP",
        title="Desenvolvedor Júnior",
        description="Desenvolvimento de APIs.",
    )

    assert result == "Não informado"


def test_linkedin_sem_rotulo_aceita_modalidade_explicita_no_texto():
    result = infer_linkedin_workplace(
        "Presencial",
        False,
        location="São Paulo, SP",
        title="Desenvolvedor Júnior",
        description="Modelo de trabalho híbrido.",
    )

    assert result == "Híbrido"


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Work model: OnsiteOnsite. Job description: suporte remoto a usuários.", "Presencial"),
        ("Work model: HybridHybrid. Job description: infraestrutura de nuvem.", "Híbrido"),
        ("1x por semana Home Office e 4x presencial.", "Híbrido"),
        ("Modelo de trabalho: 4x presencial, 1x Home Office.", "Híbrido"),
        ("Atuação em um hybrid work model.", "Híbrido"),
        ("Informações adicionais: contrato efetivo presencial. Suporte remoto a usuários.", "Presencial"),
        ("Disponibilidade para trabalhar presencialmente na sede, 5x por semana.", "Presencial"),
        ("Disponibilidade para estagiar presencialmente por 30 horas semanais.", "Presencial"),
        ("A pessoa estagiária atuará presencialmente junto à equipe.", "Presencial"),
        ("Interns should expect to work in office Monday-Friday.", "Presencial"),
    ],
)
def test_linkedin_sem_rotulo_recupera_modalidade_em_declaracoes_claras(description, expected):
    result = infer_linkedin_workplace(
        "Não informado", False, title="Analista de TI Júnior", description=description,
    )

    assert result == expected


@pytest.mark.parametrize(
    "description",
    [
        "Atender usuários por telefone ou presencialmente.",
        "Prestar suporte técnico presencial e remoto aos colaboradores.",
        "Disponibilidade para atuar presencialmente 2 dias por semana.",
        "Disponibilidade para atuar presencialmente 3 dias por semana.",
        "Disponibilidade para atuar presencialmente conforme necessidade da operação.",
        "Vale-transporte e frutas disponíveis no escritório.",
        "Home Office para mães até 12 meses do bebê.",
        "Prestar suporte técnico presencial aos usuários. Home Office para mamães até 12 meses.",
        "Apoiar ambientes cloud privados, públicos e híbridos.",
    ],
)
def test_linkedin_sem_rotulo_nao_confunde_atividade_ou_beneficio_com_regime(description):
    result = infer_linkedin_workplace(
        "Não informado", False, title="Analista de TI Júnior", description=description,
    )

    assert result == "Não informado"


def test_linkedin_rotulo_declarado_prevalece_sobre_padrao_da_descricao():
    result = infer_linkedin_workplace(
        "Remoto", True, title="Analista de TI Júnior", description="Work model: OnsiteOnsite.",
    )

    assert result == "Remoto"

