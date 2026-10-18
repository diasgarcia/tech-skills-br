"""Testes para o gerador de dados estáticos e endpoints da API (scripts/export_pages_data.py)."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from api.database import init_db, make_engine
from api.models import Tecnologia, Vaga
from scripts.export_pages_data import export_all_pages_data
from scripts.import_csv import importar


def test_export_all_pages_data_cria_endpoints_validos(tmp_path: Path, csv_vagas_minimo):
    db_file = tmp_path / "teste_pages.db"
    out_dir = tmp_path / "api_out"
    importar(csv_vagas_minimo, db_path=db_file)

    arquivos = export_all_pages_data(output_dir=out_dir, db_path=db_file)
    conteudos = {
        chave: json.loads(path.read_text(encoding="utf-8"))
        for chave, path in arquivos.items()
    }
    resumo = conteudos["resumo"]
    vagas = conteudos["vagas"]

    assert {"resumo", "areas", "tecnologias", "vagas"}.issubset(arquivos)
    assert all(path.is_file() for path in arquivos.values())
    assert all(dados is not None for dados in conteudos.values())
    assert resumo["metadados"]["total_vagas"] > 0
    assert len(resumo["areas"]) > 0
    assert isinstance(vagas, list)
    assert len(vagas) > 0
    assert "titulo" in vagas[0]


def test_exportacao_preserva_zero_e_campos_nao_informados(tmp_path):
    db_path = tmp_path / "zero.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            db.add(Vaga(source="teste", external_id="001", title="Vaga", area="Backend"))
            db.add(Tecnologia(nome="Python", grupo="linguagens"))
            db.commit()
    finally:
        engine.dispose()
    generated_at = datetime(2026, 9, 13, 2, 30, tzinfo=timezone.utc)

    files = export_all_pages_data(tmp_path / "json", db_path, generated_at=generated_at)
    resumo = json.loads(files["resumo"].read_text(encoding="utf-8"))
    vagas = json.loads(files["vagas"].read_text(encoding="utf-8"))
    techs = json.loads(files["tecnologias"].read_text(encoding="utf-8"))

    assert resumo["skills_by_area"]["Backend"] == {
        "total_vagas": 1, "vagas_com_tech": 0, "skills": []
    }
    assert resumo["habilidade_entre_areas"] is None
    assert techs[0]["vagas"] == 0
    assert techs[0]["percentual_total"] == 0
    assert techs[0]["percentual_base_tech"] == 0
    assert vagas[0]["senioridade"] == "Não informado"
    assert vagas[0]["modalidade"] == "Não informado"
    assert vagas[0]["localidade"] == "Não informado"
    assert vagas[0]["data_publicacao"] is None
    assert resumo["metadados"]["periodo"] == "Não informado"
    assert resumo["metadados"]["data_atualizacao"] == "13/09/2026"
    assert resumo["metadados"]["gerado_em"] == "2026-09-13T02:30:00+00:00"


def test_exportacao_reduz_aviso_de_cidades_proximas(tmp_path):
    db_path = tmp_path / "localidade.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            db.add(Vaga(
                source="vagas",
                external_id="1",
                title="Assistente de Marketing",
                area="Suporte Técnico",
                location=(
                    "Praia Grande / SP A empresa aceita candidaturas de "
                    "Praia Grande e cidades próximas"
                ),
            ))
            db.commit()
    finally:
        engine.dispose()

    files = export_all_pages_data(tmp_path / "json", db_path)
    vagas = json.loads(files["vagas"].read_text(encoding="utf-8"))

    assert vagas[0]["localidade"] == "Praia Grande, SP e Região"


def test_exportacao_calcula_bases_e_nao_confunde_publicacao_com_geracao(tmp_path):
    db_path = tmp_path / "percentuais.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            python = Tecnologia(nome="Python", grupo="linguagens")
            db.add_all([
                Vaga(source="teste", external_id="1", title="Python", area="Backend",
                     published_date=date(2026, 1, 2), tecnologias=[python]),
                Vaga(source="teste", external_id="2", title="Outra", area="Backend"),
            ])
            db.commit()
    finally:
        engine.dispose()

    files = export_all_pages_data(
        tmp_path / "json", db_path,
        generated_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
    )
    resumo = json.loads(files["resumo"].read_text(encoding="utf-8"))
    tech = json.loads(files["tecnologias"].read_text(encoding="utf-8"))[0]

    assert resumo["metadados"]["periodo"] == "02/01/2026 a 02/01/2026"
    assert resumo["metadados"]["data_atualizacao"] == "13/09/2026"
    assert tech["percentual_total"] == 50.0
    assert tech["percentual_base_tech"] == 100.0
    assert resumo["skills_by_area"]["Backend"]["vagas_com_tech"] == 1
    assert resumo["skills_by_area"]["Backend"]["skills"][0]["percentual"] == 100.0


def test_exportacao_vazia_substitui_arquivos_sem_dados_obsoletos(tmp_path):
    db_path = tmp_path / "empty.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            db.add(Tecnologia(nome="Python", grupo="linguagens"))
            db.commit()
    finally:
        engine.dispose()
    out_dir = tmp_path / "json"
    out_dir.mkdir()
    (out_dir / "vagas.json").write_text('[{"id": 123}]', encoding="utf-8")

    files = export_all_pages_data(out_dir, db_path)
    resumo = json.loads(files["resumo"].read_text(encoding="utf-8"))
    tech = json.loads(files["tecnologias"].read_text(encoding="utf-8"))[0]

    assert len(files) == 4
    assert resumo["metadados"]["total_vagas"] == 0
    assert resumo["skills_by_area"] == {}
    assert resumo["habilidade_entre_areas"] is None
    assert json.loads(files["vagas"].read_text(encoding="utf-8")) == []
    assert json.loads(files["areas"].read_text(encoding="utf-8")) == []
    assert tech["percentual_total"] == 0
    assert tech["percentual_base_tech"] == 0


def test_presenca_entre_areas_nao_confunde_volume_com_media(tmp_path):
    db_path = tmp_path / "presenca.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            hardware = Tecnologia(nome="Hardware", grupo="suporte")
            ingles = Tecnologia(nome="Inglês", grupo="idiomas")
            db.add_all([
                Vaga(source="teste", external_id=str(index), title="Suporte", area="Suporte Técnico",
                     tecnologias=[hardware, ingles] if index < 2 else [hardware])
                for index in range(4)
            ])
            db.add_all([
                Vaga(source="teste", external_id="4", title="Dev", area="Backend", tecnologias=[ingles]),
                Vaga(source="teste", external_id="5", title="Sem skill", area="Frontend"),
            ])
            db.commit()
    finally:
        engine.dispose()

    files = export_all_pages_data(tmp_path / "json", db_path)
    resumo = json.loads(files["resumo"].read_text(encoding="utf-8"))
    techs = json.loads(files["tecnologias"].read_text(encoding="utf-8"))

    assert techs[0]["nome"] == "Hardware"
    assert resumo["habilidade_entre_areas"] == {
        "nome": "Inglês", "areas": 2, "total_areas": 3, "media_percentual": 50.0,
    }


def test_presenca_desempata_por_cobertura_e_nome(tmp_path):
    db_path = tmp_path / "empate.db"
    engine = make_engine(db_path)
    try:
        init_db(engine)
        with Session(engine) as db:
            concentrada = Tecnologia(nome="A concentrada", grupo="teste")
            espalhada = Tecnologia(nome="B espalhada", grupo="teste")
            empate = Tecnologia(nome="C espalhada", grupo="teste")
            db.add_all([
                Vaga(source="teste", external_id=f"{area}-{index}", title="Vaga", area=area,
                     tecnologias=([espalhada, empate] if index == 0 else []) +
                     ([concentrada] if area == "Backend" and index < 2 else []))
                for area in ("Backend", "Frontend") for index in range(4)
            ])
            db.commit()
    finally:
        engine.dispose()

    files = export_all_pages_data(tmp_path / "json", db_path)
    resumo = json.loads(files["resumo"].read_text(encoding="utf-8"))

    assert resumo["habilidade_entre_areas"] == {
        "nome": "B espalhada", "areas": 2, "total_areas": 2, "media_percentual": 25.0,
    }
