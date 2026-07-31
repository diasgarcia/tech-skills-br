"""Importador CSV -> SQLite e a normalizacao das datas."""

from __future__ import annotations

import csv
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dates import parse_published_date, reference_date_from_csv
from api.database import make_engine
from api.models import Tecnologia, Vaga
from scripts.import_csv import importar

REFERENCIA = date(2026, 7, 31)


@pytest.mark.parametrize(
    "bruto,esperado",
    [
        ("2026-06-26", date(2026, 6, 26)),          # ISO, da Gupy
        ("09/07/2026", date(2026, 7, 9)),           # dd/mm/aaaa, do Vagas.com
        ("Hoje", REFERENCIA),
        ("Ontem", date(2026, 7, 30)),
        ("Anteontem", date(2026, 7, 29)),
        ("Há 3 dias", date(2026, 7, 28)),
        ("há 1 dia", date(2026, 7, 30)),
        ("Há mais de 30 dias", date(2026, 7, 1)),
        ("Há 2 meses", date(2026, 6, 1)),
        ("", None),
        (None, None),
        ("qualquer coisa", None),
        ("32/13/2026", None),                       # data impossivel
    ],
)
def test_parse_published_date(bruto, esperado):
    assert parse_published_date(bruto, REFERENCIA) == esperado


def test_datas_relativas_usam_a_referencia_e_nao_hoje():
    """Importar um CSV antigo tem que reproduzir as datas da época da coleta."""
    antiga = date(2020, 1, 10)
    assert parse_published_date("Ontem", antiga) == date(2020, 1, 9)


def test_referencia_sai_do_nome_do_arquivo(tmp_path):
    arquivo = tmp_path / "vagas_20260731_174407.csv"
    arquivo.write_text("x", encoding="utf-8")
    assert reference_date_from_csv(arquivo) == date(2026, 7, 31)


def test_referencia_cai_para_mtime_sem_timestamp_no_nome(tmp_path):
    arquivo = tmp_path / "vagas_sem_stamp.csv"
    arquivo.write_text("x", encoding="utf-8")
    assert isinstance(reference_date_from_csv(arquivo), date)


COLUNAS = [
    "area", "seniority", "title", "company", "source", "location",
    "workplace_type", "published_date", "url", "skills", "area_score",
    "area_matches", "search_term", "external_id", "description",
]


def _escrever_csv(tmp_path, linhas, nome="vagas_20260731_174407.csv"):
    caminho = tmp_path / nome
    with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


def _linha(**kwargs):
    base = {c: "" for c in COLUNAS}
    base.update({
        "area": "Data", "seniority": "Júnior", "title": "Analista de Dados Jr",
        "company": "ACME", "source": "gupy", "external_id": "1",
        "published_date": "2026-07-20", "skills": "Python, SQL", "area_score": "12.0",
    })
    base.update(kwargs)
    return base


def test_importa_e_vincula_tecnologias(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha()])
    resultado = importar(csv_path, tmp_path / "t.db")

    assert resultado["criadas"] == 1
    assert resultado["total"] == 1

    with Session(make_engine(tmp_path / "t.db")) as db:
        vaga = db.scalar(select(Vaga))
        assert vaga.title == "Analista de Dados Jr"
        assert vaga.published_date == date(2026, 7, 20)
        assert sorted(t.nome for t in vaga.tecnologias) == ["Python", "SQL"]
        # O vocabulario inteiro de skills.yml e semeado.
        assert db.scalar(select(func.count()).select_from(Tecnologia)) > 100


def test_importacao_e_idempotente(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha(), _linha(external_id="2")])
    db_path = tmp_path / "t.db"

    primeira = importar(csv_path, db_path)
    assert (primeira["criadas"], primeira["atualizadas"]) == (2, 0)

    segunda = importar(csv_path, db_path)
    assert (segunda["criadas"], segunda["atualizadas"]) == (0, 2)
    assert segunda["total"] == 2


def test_reimportacao_atualiza_campos_alterados(tmp_path):
    db_path = tmp_path / "t.db"
    importar(_escrever_csv(tmp_path, [_linha(title="Título antigo")]), db_path)
    importar(_escrever_csv(tmp_path, [_linha(title="Título novo")]), db_path)

    with Session(make_engine(db_path)) as db:
        assert db.scalar(select(Vaga)).title == "Título novo"


def test_mesma_external_id_em_fontes_diferentes_sao_vagas_distintas(tmp_path):
    csv_path = _escrever_csv(
        tmp_path, [_linha(source="gupy"), _linha(source="vagas")]
    )
    assert importar(csv_path, tmp_path / "t.db")["total"] == 2


def test_data_relativa_resolvida_pelo_nome_do_csv(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha(published_date="Ontem")])
    importar(csv_path, tmp_path / "t.db")

    with Session(make_engine(tmp_path / "t.db")) as db:
        assert db.scalar(select(Vaga)).published_date == date(2026, 7, 30)


def test_linha_sem_identidade_e_ignorada(tmp_path):
    csv_path = _escrever_csv(tmp_path, [
        _linha(),
        _linha(external_id="", source="gupy"),
        _linha(external_id="9", title=""),
    ])
    assert importar(csv_path, tmp_path / "t.db")["total"] == 1


def test_tecnologia_fora_do_vocabulario_e_ignorada(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha(skills="Python, Fortran-77")])
    importar(csv_path, tmp_path / "t.db")

    with Session(make_engine(tmp_path / "t.db")) as db:
        assert [t.nome for t in db.scalar(select(Vaga)).tecnologias] == ["Python"]


def test_campos_vazios_viram_null(tmp_path):
    csv_path = _escrever_csv(tmp_path, [_linha(company="", location="", skills="")])
    importar(csv_path, tmp_path / "t.db")

    with Session(make_engine(tmp_path / "t.db")) as db:
        vaga = db.scalar(select(Vaga))
        assert vaga.company is None
        assert vaga.location is None
        assert vaga.tecnologias == []


def test_referencia_explicita_vence_o_nome_do_arquivo(tmp_path):
    """O snapshot versionado depende disso: no deploy o mtime é a data do clone."""
    csv_path = _escrever_csv(tmp_path, [_linha(published_date="Ontem")])
    importar(csv_path, tmp_path / "t.db", referencia=date(2020, 1, 10))

    with Session(make_engine(tmp_path / "t.db")) as db:
        assert db.scalar(select(Vaga)).published_date == date(2020, 1, 9)


def test_referencia_explicita_funciona_sem_timestamp_no_nome(tmp_path):
    csv_path = _escrever_csv(
        tmp_path, [_linha(published_date="Há 3 dias")], nome="vagas.csv"
    )
    importar(csv_path, tmp_path / "t.db", referencia=date(2026, 7, 31))

    with Session(make_engine(tmp_path / "t.db")) as db:
        assert db.scalar(select(Vaga)).published_date == date(2026, 7, 28)


def test_recriar_limpa_o_banco(tmp_path):
    db_path = tmp_path / "t.db"
    importar(_escrever_csv(tmp_path, [_linha(), _linha(external_id="2")]), db_path)
    resultado = importar(_escrever_csv(tmp_path, [_linha()]), db_path, recriar=True)
    assert resultado["total"] == 1
