"""Testes para o gerador de dados estáticos e endpoints da API (scripts/export_pages_data.py)."""

import json
from pathlib import Path

from scripts.export_pages_data import export_all_pages_data
from scripts.import_csv import importar


def test_export_all_pages_data_cria_endpoints_validos(tmp_path: Path):
    db_file = tmp_path / "teste_pages.db"
    out_dir = tmp_path / "api_out"
    csv_file = Path(__file__).resolve().parent.parent / "seed" / "vagas.csv"
    importar(csv_file, db_path=db_file)

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
