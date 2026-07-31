"""Fixtures da API: banco SQLite em memoria, sem rede e sem tocar em data/vagas.db.

Os testes da API ficam num diretorio proprio para que quem so usa o scraper
possa rodar `pytest tests/` sem ter FastAPI instalado -- o importorskip abaixo
pula esta pasta inteira nesse caso.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi", reason="FastAPI não instalado; testes da API pulados.")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from api.app import app  # noqa: E402
from api.database import Base, get_db  # noqa: E402
from api.models import Tecnologia, Vaga  # noqa: E402


@pytest.fixture
def db_session():
    """SQLite em memoria. StaticPool mantem a mesma conexao entre as sessoes."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def seed(db_session):
    """Um conjunto pequeno e previsivel, no formato que o importador produz."""
    python = Tecnologia(nome="Python", grupo="linguagens")
    sql = Tecnologia(nome="SQL", grupo="linguagens")
    react = Tecnologia(nome="React", grupo="frameworks")
    db_session.add_all([python, sql, react])

    db_session.add_all([
        Vaga(
            source="gupy", external_id="1001",
            title="Engenheiro de Dados Júnior", company="ACME",
            area="Data", seniority="Júnior", location="São Paulo, São Paulo",
            workplace_type="Remoto", published_date=date(2026, 7, 20),
            url="https://exemplo.test/1001", description="Vaga de dados.",
            area_score=12.0, area_matches="engenheiro de dados(t)",
            search_term="engenheiro de dados junior",
            tecnologias=[python, sql],
        ),
        Vaga(
            source="gupy", external_id="1002",
            title="Analista de Dados Júnior", company="Globex",
            area="Data", seniority="Júnior", location="Belo Horizonte, Minas Gerais",
            workplace_type="Híbrido", published_date=date(2026, 7, 10),
            url="https://exemplo.test/1002", description="BI e relatórios.",
            tecnologias=[sql],
        ),
        Vaga(
            source="vagas", external_id="2001",
            title="Desenvolvedor Front-End Jr", company="Initech",
            area="Frontend", seniority="Júnior", location="100% Home Office",
            workplace_type="Remoto", published_date=date(2026, 7, 25),
            url="https://exemplo.test/2001", description="React e CSS.",
            tecnologias=[react],
        ),
        Vaga(
            source="vagas", external_id="2002",
            title="Estágio em Suporte Técnico", company="Umbrella",
            area="Suporte/Infra", seniority="Estágio", location="Curitiba / PR",
            workplace_type="Não informado", published_date=None,
            url="https://exemplo.test/2002", description="Atendimento e chamados.",
        ),
    ])
    db_session.commit()
    return db_session


@pytest.fixture
def client(seed):
    """TestClient com o banco de teste injetado no lugar do banco real."""
    app.dependency_overrides[get_db] = lambda: seed
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
