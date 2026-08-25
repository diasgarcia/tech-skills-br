"""Testes para o gerador de dados estáticos e endpoints da API (scripts/export_pages_data.py)."""

import json
from pathlib import Path

from scripts.export_pages_data import export_all_pages_data
from scripts.import_csv import importar


def test_export_all_pages_data_cria_endpoints_validos(tmp_path: Path):
    db_file = tmp_path / "teste_pages.db"
    out_dir = tmp_path / "api_out"
    
    csv_file = Path(__file__).resolve().parent.parent / "seed" / "vagas.csv"
    if not csv_file.exists():
        csv_file = Path(__file__).resolve().parent / "seed" / "vagas.csv"

    if csv_file.exists():
        importar(csv_file, db_path=db_file)

    arquivos = export_all_pages_data(output_dir=out_dir, db_path=db_file)

    if csv_file.exists():
        assert "resumo" in arquivos
        assert "areas" in arquivos
        assert "tecnologias" in arquivos
        assert "vagas" in arquivos

        for k, p in arquivos.items():
            assert p.is_file()
            with open(p, encoding="utf-8") as f:
                dados = json.load(f)
                assert dados is not None

        with open(arquivos["resumo"], encoding="utf-8") as f:
            resumo = json.load(f)
            assert resumo["metadados"]["total_vagas"] > 0
            assert len(resumo["areas"]) > 0

        with open(arquivos["vagas"], encoding="utf-8") as f:
            vagas = json.load(f)
            assert isinstance(vagas, list)
            assert len(vagas) > 0
            assert "titulo" in vagas[0]

