"""Testes do snapshot relacional e analitico publicado no Kaggle."""

from __future__ import annotations

import sqlite3

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.export_kaggle import exportar


def _criar_banco(caminho) -> None:
    conn = sqlite3.connect(caminho)
    with conn:
        conn.executescript(
            """
            CREATE TABLE vagas (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                area TEXT NOT NULL,
                seniority TEXT,
                workplace_type TEXT,
                location TEXT,
                regiao TEXT,
                polo TEXT,
                published_date DATE,
                description TEXT,
                url TEXT,
                search_term TEXT,
                enrich_encerrada BOOLEAN NOT NULL
            );
            CREATE TABLE tecnologias (
                id INTEGER PRIMARY KEY,
                nome TEXT NOT NULL,
                grupo TEXT NOT NULL
            );
            CREATE TABLE vaga_tecnologia (
                vaga_id INTEGER NOT NULL,
                tecnologia_id INTEGER NOT NULL,
                PRIMARY KEY (vaga_id, tecnologia_id)
            );

            INSERT INTO vagas VALUES
                (1, 'gupy', 'abc-1', 'Dev Junior', 'ACME', 'Backend',
                 'Júnior', 'Remoto', 'Brasil', 'Remoto Nacional', 'Remoto',
                 '2026-09-10', 'Trabalhar com Python e Docker.',
                 'https://example.com/1', 'desenvolvedor junior', 1),
                (2, 'linkedin', '002', 'Estágio em TI', 'Exemplo',
                 'Suporte Técnico', 'Estágio', 'Presencial', 'São Paulo, SP',
                 'Sudeste', 'São Paulo', NULL, NULL,
                 'https://example.com/2', 'estagio ti', 0);

            INSERT INTO tecnologias VALUES
                (10, 'Python', 'linguagens'),
                (20, 'Docker', 'cloud_devops');
            INSERT INTO vaga_tecnologia VALUES (1, 10), (1, 20);
            """
        )
    conn.close()


def test_exporta_tabelas_relacionais_e_visao_analitica(tmp_path):
    db_path = tmp_path / "vagas.db"
    export_dir = tmp_path / "kaggle"
    _criar_banco(db_path)

    caminho_principal, total = exportar(db_path=db_path, export_dir=export_dir)

    assert total == 2
    assert caminho_principal == export_dir / "vagas.parquet"
    assert {path.name for path in export_dir.glob("*.parquet")} == {
        "vagas.parquet",
        "tecnologias.parquet",
        "vaga_tecnologia.parquet",
        "analise_skills.parquet",
    }

    vagas = pd.read_parquet(export_dir / "vagas.parquet")
    tecnologias = pd.read_parquet(export_dir / "tecnologias.parquet")
    relacionamentos = pd.read_parquet(export_dir / "vaga_tecnologia.parquet")
    analise = pd.read_parquet(export_dir / "analise_skills.parquet")

    assert len(vagas) == 2
    assert vagas.loc[vagas["id"] == 1, "skills"].item() == "Docker; Python"
    assert pd.isna(vagas.loc[vagas["id"] == 2, "skills"].item())
    assert tecnologias[["id", "nome", "grupo"]].shape == (2, 3)
    assert len(relacionamentos) == 2
    assert len(analise) == len(relacionamentos)
    assert list(analise.columns[:4]) == [
        "skill", "categoria_skill", "source", "area",
    ]
    assert "url" in analise.columns
    assert "description" not in analise.columns

    assert set(relacionamentos["vaga_id"]) <= set(vagas["id"])
    assert set(relacionamentos["tecnologia_id"]) <= set(tecnologias["id"])
    assert set(analise["vaga_id"]) == {1}
    assert set(analise["url"]) == {"https://example.com/1"}


def test_exporta_tipos_semanticos_no_parquet(tmp_path):
    db_path = tmp_path / "vagas.db"
    export_dir = tmp_path / "kaggle"
    _criar_banco(db_path)
    exportar(db_path=db_path, export_dir=export_dir)

    vagas = pq.read_schema(export_dir / "vagas.parquet")
    analise = pq.read_schema(export_dir / "analise_skills.parquet")

    assert pa.types.is_string(vagas.field("skills").type) or pa.types.is_large_string(
        vagas.field("skills").type
    )
    assert pa.types.is_date32(vagas.field("published_date").type)
    assert pa.types.is_boolean(vagas.field("enrich_encerrada").type)
    assert pa.types.is_dictionary(vagas.field("source").type)
    assert pa.types.is_dictionary(analise.field("skill").type)
    assert pa.types.is_date32(analise.field("published_date").type)
    assert pa.types.is_int64(analise.field("vaga_id").type)
