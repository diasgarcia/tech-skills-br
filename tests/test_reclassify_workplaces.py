import sqlite3

from api.database import init_db
from scripts.reclassify_workplaces import reclassify_linkedin_workplaces


def test_reclassificacao_remove_palpite_presencial_e_preserva_rotulo(tmp_path):
    db_path = tmp_path / "vagas.db"
    init_db(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO vagas (
                source, external_id, title, company, area, location,
                workplace_type, workplace_declared, description, enrich_encerrada
            ) VALUES ('linkedin', ?, ?, 'ACME', 'Backend', 'São Paulo, SP', ?, ?, ?, 0)
            """,
            [
                ("1", "Dev Júnior", "Presencial", 0, "Desenvolvimento de APIs."),
                ("2", "Dev Júnior", "Híbrido", 1, "Vaga remota."),
            ],
        )

    result = reclassify_linkedin_workplaces(db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT external_id, workplace_type FROM vagas ORDER BY external_id"
        ).fetchall()
    assert result == {"analyzed": 2, "changed": 1}
    assert rows == [("1", "Não informado"), ("2", "Híbrido")]


def test_reclassificacao_aplica_modalidade_curada(tmp_path):
    db_path = tmp_path / "vagas.db"
    init_db(db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO vagas (
                source, external_id, title, company, area, location,
                workplace_type, workplace_declared, description, enrich_encerrada
            ) VALUES (
                'linkedin', '4469639853', 'Assistente de TI', 'RDANILLO',
                'Suporte Técnico', 'Cuiabá, MT', 'Remoto', 0,
                'Suporte remoto e presencial aos colaboradores.', 0
            )
            """
        )

    result = reclassify_linkedin_workplaces(db_path)

    with sqlite3.connect(db_path) as conn:
        workplace, declared = conn.execute(
            "SELECT workplace_type, workplace_declared FROM vagas"
        ).fetchone()
    assert result == {"analyzed": 1, "changed": 1}
    assert workplace == "Presencial"
    assert declared == 1
