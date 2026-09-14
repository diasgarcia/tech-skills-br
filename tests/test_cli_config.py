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
])
def test_configuracao_invalida_falha_antes_de_coletar(args, monkeypatch):
    collect = Mock()
    monkeypatch.setattr(main, "run", collect)

    with pytest.raises(SystemExit) as error:
        main.main(args)

    assert error.value.code == 2
    collect.assert_not_called()
