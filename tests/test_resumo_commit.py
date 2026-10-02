import argparse
from contextlib import closing
from datetime import date

import pytest

from api.database import connect_sqlite, init_db
from scripts.resumo_commit import main, resumir


def _banco(tmp_path, timestamps):
    path = tmp_path / "vagas.db"
    init_db(db_path=path)
    with closing(connect_sqlite(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO vagas (source, external_id, title, area, description, "
            "enrich_encerrada, created_at, updated_at, published_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "gupy" if index % 2 else "linkedin", str(index), "Desenvolvedor Junior",
                    "Backend", "", 0, timestamp, "2026-10-01 23:00:00", "2026-10-01",
                )
                for index, timestamp in enumerate(timestamps, 1)
            ],
        )
    return path


def _args(path, **changes):
    values = dict(
        db=path, brutas=100, elegiveis=10, novas=1, atualizadas=9,
        log=None, summary_json=None, dia=date(2026, 10, 1),
    )
    values.update(changes)
    return argparse.Namespace(**values)


def test_resumo_diario_inclui_todas_as_rodadas_e_respeita_brasilia(tmp_path):
    path = _banco(tmp_path, [
        "2026-10-01 02:59:59",
        "2026-10-01 03:00:00",
        "2026-10-01 12:16:05",
        "2026-10-01 17:16:05",
        "2026-10-01 22:16:05",
        "2026-10-02 02:59:59",
        "2026-10-02 03:00:00",
    ])
    before = path.read_bytes()

    text = resumir(_args(path))

    assert text.splitlines()[0] == "- Novas no dia (01/10/2026, Brasilia): 5 vagas"
    assert "- Coleta da ultima rodada: 100 brutas | 10 elegiveis" in text
    assert "- Importacao da ultima rodada: 1 novas | 9 atualizadas" in text
    assert "- Base: 7 vagas" in text
    assert path.read_bytes() == before


def test_vaga_antiga_atualizada_ou_publicada_no_dia_nao_conta_como_nova(tmp_path):
    path = _banco(tmp_path, ["2026-09-30 12:00:00", "2026-10-01 12:00:00"])
    with closing(connect_sqlite(path)) as conn, conn:
        conn.execute("UPDATE vagas SET description = 'Descricao atualizada' WHERE external_id = '1'")

    text = resumir(_args(path, novas=0, atualizadas=2))

    assert "- Novas no dia (01/10/2026, Brasilia): 1 vaga" in text
    assert "- Importacao da ultima rodada: 0 novas | 2 atualizadas" in text


def test_resumo_diario_mostra_zero_quando_nao_entraram_vagas(tmp_path):
    path = _banco(tmp_path, [])

    text = resumir(_args(path, novas=0, atualizadas=0))

    assert "- Novas no dia (01/10/2026, Brasilia): 0 vagas" in text


def test_resumo_sem_dia_preserva_formato_das_execucoes_manuais(tmp_path):
    path = _banco(tmp_path, ["2026-10-01 12:00:00"])

    text = resumir(_args(path, dia=None))

    assert "Novas no dia" not in text
    assert "- Coleta: 100 brutas | 10 elegiveis" in text
    assert "- Importacao: 1 novas | 9 atualizadas" in text


def test_cli_recebe_data_do_workflow_sem_depender_do_dia_atual(tmp_path, capsys):
    path = _banco(tmp_path, ["2026-10-01 12:00:00", "2026-10-02 12:00:00"])

    exit_code = main(["--db", str(path), "--dia", "2026-10-01"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("- Novas no dia (01/10/2026, Brasilia): 1 vaga")


def test_cli_recusa_data_invalida_sem_criar_banco(tmp_path):
    path = tmp_path / "inexistente.db"

    with pytest.raises(SystemExit) as error:
        main(["--db", str(path), "--dia", "2026-02-30"])

    assert error.value.code == 2
    assert not path.exists()
