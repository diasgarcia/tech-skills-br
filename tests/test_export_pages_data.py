"""Testes para o gerador de dados estáticos e endpoints da API (scripts/export_pages_data.py)."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.export_pages_data import export_all_pages_data


def test_export_all_pages_data_cria_endpoints_validos():
    with TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        
        arquivos = export_all_pages_data(out_dir)
        
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
