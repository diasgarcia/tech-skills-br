"""Testes da configuracao central: Settings e carregamento de .env."""

import os

from scraper.config import Settings, _load_dotenv


def test_settings_defaults_do_projeto():
    s = Settings()
    assert s.delay_seconds == 1.5
    assert s.page_size == 100
    assert s.max_pages_per_term == 15
    assert s.only_junior is True
    assert s.enrich_linkedin is True


def test_ensure_output_dir_cria_diretorio(tmp_path):
    s = Settings(output_dir=tmp_path / "saida")
    assert not (tmp_path / "saida").exists()
    assert s.ensure_output_dir() == tmp_path / "saida"
    assert (tmp_path / "saida").is_dir()


def test_load_dotenv_sem_arquivo_devolve_nada():
    assert _load_dotenv(tmp := __import__("pathlib").Path("nao/existe/.env")) is None


def test_load_dotenv_parseia_arquivo_sem_python_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'CHAVE_SIMPLES=valor1\n'
        'CHAVE_ASPAS="valor com espaco"\n'
        "# comentario ignorado\n",
        encoding="utf-8",
    )

    import builtins

    import_real = builtins.__import__

    def import_sem_dotenv(name, *args, **kwargs):
        if name == "dotenv":
            raise ImportError("python-dotenv nao instalado")
        return import_real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_sem_dotenv)
    monkeypatch.delenv("CHAVE_SIMPLES", raising=False)
    monkeypatch.delenv("CHAVE_ASPAS", raising=False)

    _load_dotenv(env)

    assert os.environ["CHAVE_SIMPLES"] == "valor1"
    assert os.environ["CHAVE_ASPAS"] == "valor com espaco"
