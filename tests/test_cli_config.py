from unittest.mock import Mock

import pytest

import main
from scraper.config import Settings
from scraper.models import Job
from scraper.pipeline import PipelineResult


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


@pytest.mark.parametrize("rule,source,expected", [
    ("source_empty", "infojobs", 0),
    ("sharp_drop", "infojobs", 0),
    ("invalid_workplace", None, 1),
    ("unknown_rule", "infojobs", 1),
    ("sharp_drop", None, 1),
])
def test_cli_so_bloqueia_alertas_que_nao_sao_anomalias_de_fonte(rule, source, expected, capsys):
    result = PipelineResult(
        jobs=[Job(source="gupy", external_id="1", title="Desenvolvedor Junior")],
        ranking=[],
        meta={
            "quality_gate": True,
            "quality_alerts": [{"rule": rule, "source": source, "severity": "high", "message": "Anomalia"}],
        },
    )

    exit_code = main._print_result(result, Settings())

    assert exit_code == expected
    assert "ERRO: Anomalia" in capsys.readouterr().out
