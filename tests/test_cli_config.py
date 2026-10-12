from unittest.mock import Mock

import pytest

import main


@pytest.mark.parametrize("args", [
    ["--source-delay", "nao-existe", "1"],
    ["--source-delay", "gupy", "abc"],
    ["--source-delay", "gupy", "-1"],
    ["--source-delay", "gupy", "nan"],
    ["--delay", "-1"],
    ["--max-pages", "0"],
    ["--start-page", "0"],
    ["--page-size", "0"],
    ["--jobbol-days", "0"],
])
def test_configuracao_invalida_falha_antes_de_coletar(args, monkeypatch):
    collect = Mock()
    monkeypatch.setattr(main, "run", collect)

    with pytest.raises(SystemExit) as error:
        main.main(args)

    assert error.value.code == 2
    collect.assert_not_called()


def test_jobbol_pode_ser_selecionada_com_janela_maior():
    args = main.build_parser().parse_args(["--sources", "jobbol", "--jobbol-days", "365"])

    settings = main._settings_from_args(args, {})

    assert settings.sources == ["jobbol"]
    assert settings.jobbol_days_back == 365
