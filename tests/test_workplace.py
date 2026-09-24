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
        ("Location: São Leopoldo, Brazil. Hybrid position, 3 days per week in the office.", "Híbrido"),
        ("Híbrido: 4 dias presencial / 1 dia home office.", "Híbrido"),
        ("Hibrido 3x na semana.", "Híbrido"),
        ("Hibrido 3 x na semana.", "Híbrido"),
        ("Linx | São Paulo - SP | Híbrido. Seu maior desafio será...", "Híbrido"),
        ("Localização: Híbrido - São Paulo.", "Híbrido"),
        ("Localidade / Atuação: Uberlândia/MG - Híbrido.", "Híbrido"),
        ("Esta é uma oportunidade híbrida para atuação em Belém.", "Híbrido"),
        ("A posição é híbrida em São Paulo.", "Híbrido"),
        ("Forma de trabalho: híbrido em São José dos Campos.", "Híbrido"),
        ("Disponibilidade para atuação híbrida em Campinas.", "Híbrido"),
        ("Trabalho híbrido, dois dias no escritório.", "Híbrido"),
        ("Formato: 4 dias presenciais e 1 dia de Home Office.", "Híbrido"),
        ("Modalidade: 4 vezes presencial e um dia de Home Office.", "Híbrido"),
        ("Jornada de trabalho: 4 dias presenciais, 1 dia Home Office.", "Híbrido"),
        ("Disponibilidade para 4 dias presenciais e 1 dia em Home Office.", "Híbrido"),
        ("Híbrido com 3 dias presenciais na Faria Lima.", "Híbrido"),
        ("São Paulo, Remote, with 1 day in the office every other week.", "Híbrido"),
        ("Informações adicionais: contrato efetivo presencial. Suporte remoto a usuários.", "Presencial"),
        ("Contrato: Estágio. Presencial.", "Presencial"),
        ("Vaga para atuar presencial em Campinas/SP.", "Presencial"),
        ("Regime de contratação: Presencial em Curitiba.", "Presencial"),
        ("30h semanais, presencial em Recife/PE.", "Presencial"),
        ("30hrs semanais presencial em Taubaté.", "Presencial"),
        ("Modelo de trabalho 100% presencial.", "Presencial"),
        ("Modelo de trabalho presencial. Apoiar ambientes híbridos on-premises e cloud.", "Presencial"),
        ("Modelo de trabalho 07h30 às 17h30, presencial.", "Presencial"),
        ("Modelo full presencial em Porto Alegre.", "Presencial"),
        ("Tipo de contrato: CLT - Presencial.", "Presencial"),
        ("Local de trabalho: Cajamar (presencial).", "Presencial"),
        ("Turno de trabalho 08h às 18h (Presencial).", "Presencial"),
        ("Jornada de trabalho: Estágio presencial em Copacabana.", "Presencial"),
        ("A vaga é presencial para atuar na região de Manaus.", "Presencial"),
        ("A atuação será presencial em Uberaba/MG.", "Presencial"),
        ("O trabalho será presencial em Florianópolis.", "Presencial"),
        ("Contrato trainee presencial e em período integral.", "Presencial"),
        ("Contrato aprendiz presencial.", "Presencial"),
        ("Disponibilidade para atuar em escala 12x36 presencial.", "Presencial"),
        ("Este é um cargo full time presencial em Viana/ES.", "Presencial"),
        ("Estágio remunerado presencial em São Paulo.", "Presencial"),
        ("Vaga aberta para estagiário de TI presencial.", "Presencial"),
        ("Disponibilidade para atuação presencial em Campinas/SP.", "Presencial"),
        ("A vaga é presencial em Porto Alegre.", "Presencial"),
        ("Disponibilidade para trabalhar de maneira presencial.", "Presencial"),
        ("Disponibilidade para trabalhar presencialmente na sede, 5x por semana.", "Presencial"),
        ("Disponibilidade para estagiar presencialmente por 30 horas semanais.", "Presencial"),
        ("A pessoa estagiária atuará presencialmente junto à equipe.", "Presencial"),
        ("Interns should expect to work in office Monday-Friday.", "Presencial"),
        ("Modelo de trabalho: HOME OFFICE.", "Remoto"),
        ("Modalidade: HOME OFFICE.", "Remoto"),
        ("A atuação é 100% HOME OFFICE.", "Remoto"),
        ("This is a paid remote internship for software students.", "Remoto"),
        ("Remote work model with flexible hours.", "Remoto"),
        ("Workplace: Remote. About the role...", "Remoto"),
        ("Jornada flexível sendo executada de forma remota.", "Remoto"),
        ("Regime CLT remoto, com treinamentos contínuos.", "Remoto"),
        ("CLT São Paulo Remote. About the company...", "Remoto"),
        ("Atuar remotamente prestando suporte em ambiente home office.", "Remoto"),
        ("Vaga para atuar em Home Office.", "Remoto"),
        ("Build hybrid search for retrieval. This is a full-time remote role.", "Remoto"),
        ("Somos remote-first.", "Remoto"),
        ("Carga mensal de 160 horas/mês100% Remoto.", "Remoto"),
        ("Horário de trabalho: segunda a sexta, das 8h às 18h. Home Office.", "Remoto"),
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
        "Prestar suporte técnico aos usuários de forma presencial e remota.",
        "Realizar chamados de forma remota ou presencial.",
        "Atuação em atendimento presencial e remoto aos clientes.",
        "Objetivo do cargo: prestar suporte técnico presencial e remoto.",
        "Vaga efetiva e presencial ou remota para atuar 44 horas semanais.",
        (
            "Suporte remoto e presencial aos colaboradores. Atuar no atendimento "
            "localmente na unidade de Cuiabá e remotamente nas demais unidades."
        ),
        "Disponibilidade para atuar presencialmente 2 dias por semana.",
        "Disponibilidade para atuar presencialmente 3 dias por semana.",
        "Disponibilidade para atuar presencialmente conforme necessidade da operação.",
        "Vale-transporte e frutas disponíveis no escritório.",
        "Home Office para mães até 12 meses do bebê.",
        "Auxílio home office apenas para vagas 100% remotas.",
        "Auxílio home office para contratos híbridos ou remotos.",
        "Prestar suporte técnico presencial aos usuários. Home Office para mamães até 12 meses.",
        "Apoiar ambientes cloud privados, públicos e híbridos.",
        "Experiência com desenvolvimento mobile e web híbrido.",
        "Trabalhar de forma híbrida entre código tradicional e plataformas low-code.",
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

