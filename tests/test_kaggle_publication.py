import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.snapshots import sha256
from scripts import export_kaggle as kaggle


AVISO_VERSAO = (
    "Warning: Looks like you're using an outdated `kaggle` version "
    "(installed: 2.2.4), please consider upgrading to the latest version (2.2.5)"
)
STATUS = {"status": "ready", "current_version_number": 178}


@pytest.mark.parametrize(
    "stdout",
    [
        json.dumps(STATUS),
        json.dumps(STATUS, indent=2),
        AVISO_VERSAO + "\n" + json.dumps(STATUS),
        "\n" + AVISO_VERSAO + "\nWarning: outro aviso do cliente\n" + json.dumps(STATUS, indent=2) + "\n",
    ],
)
def test_status_dataset_aceita_json_com_avisos_antes_da_resposta(monkeypatch, stdout):
    command = Mock(return_value=SimpleNamespace(returncode=0, stdout=stdout, stderr=""))
    monkeypatch.setattr(kaggle.subprocess, "run", command)

    result = kaggle._status_dataset()

    assert result == STATUS
    command.assert_called_once_with(
        ["kaggle", "datasets", "status", kaggle.HANDLE, "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )


def test_status_dataset_registra_aviso_do_cliente(monkeypatch, caplog):
    response = SimpleNamespace(returncode=0, stdout=AVISO_VERSAO + "\n" + json.dumps(STATUS), stderr="")
    monkeypatch.setattr(kaggle.subprocess, "run", Mock(return_value=response))

    result = kaggle._status_dataset()

    assert result == STATUS
    assert AVISO_VERSAO in caplog.text


@pytest.mark.parametrize(
    "stdout",
    [
        "", "resposta invalida", "{", "[]", "null",
        AVISO_VERSAO,
        AVISO_VERSAO + '\n{"status":',
        "Error: acesso negado\n" + json.dumps(STATUS),
        json.dumps(STATUS) + "\n" + json.dumps(STATUS),
    ],
)
def test_status_dataset_nao_aceita_resposta_invalida(monkeypatch, stdout):
    response = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    monkeypatch.setattr(kaggle.subprocess, "run", Mock(return_value=response))

    result = kaggle._status_dataset()

    assert result is None


def test_status_dataset_nao_ignora_falha_do_comando(monkeypatch, caplog):
    response = SimpleNamespace(returncode=1, stdout=json.dumps(STATUS), stderr="acesso negado")
    monkeypatch.setattr(kaggle.subprocess, "run", Mock(return_value=response))

    result = kaggle._status_dataset()

    assert result is None
    assert "acesso negado" in caplog.text


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    path = tmp_path / "vagas.parquet"
    path.write_bytes(b"snapshot de teste")
    monkeypatch.setenv("KAGGLE_API_TOKEN", "token-apenas-do-teste")
    monkeypatch.setattr(kaggle, "exportar", lambda *args: (path, 5))
    monkeypatch.setattr(kaggle, "_status_dataset", lambda: {"current_version_number": 10})
    monkeypatch.setattr(kaggle, "_ESPERAS_CONFIRMACAO", (0,))
    monkeypatch.setattr(kaggle, "_reaplicar_metadata", Mock())
    client = SimpleNamespace(dataset_upload=Mock(), dataset_download=Mock())
    monkeypatch.setitem(sys.modules, "kagglehub", client)
    return path, client


def test_versao_alheia_nao_confirma_envio(publisher, monkeypatch):
    path, _ = publisher
    monkeypatch.setattr(kaggle, "_arquivo_confirmado", lambda version, expected: False)

    result = kaggle._aguardar_confirmacao(9, sha256(path))

    assert result is False


def test_confirmacao_baixa_versao_exata_e_confere_arquivo(publisher):
    path, client = publisher
    client.dataset_download.return_value = str(path)

    result = kaggle._arquivo_confirmado(12, sha256(path))

    assert result is True
    assert client.dataset_download.call_args.args == (f"{kaggle.HANDLE}/versions/12",)
    assert client.dataset_download.call_args.kwargs["path"] == "vagas.parquet"


def test_repeticao_nao_cria_versao_duplicada(publisher, monkeypatch):
    _, client = publisher
    monkeypatch.setattr(kaggle, "_arquivo_confirmado", lambda *args: True)

    kaggle.subir()

    client.dataset_upload.assert_not_called()


def test_upload_com_resposta_perdida_so_confirma_o_mesmo_parquet(publisher, monkeypatch):
    _, client = publisher
    client.dataset_upload.side_effect = TimeoutError("resposta perdida")
    monkeypatch.setattr(kaggle, "_arquivo_confirmado", lambda *args: False)
    confirm = Mock(return_value=True)
    monkeypatch.setattr(kaggle, "_aguardar_confirmacao", confirm)

    kaggle.subir()

    assert client.dataset_upload.call_count == 1
    assert confirm.call_count == 1


def test_resposta_sucesso_tambem_exige_confirmacao(publisher, monkeypatch):
    _, client = publisher
    monkeypatch.setattr(kaggle, "_arquivo_confirmado", lambda *args: False)
    monkeypatch.setattr(kaggle, "_aguardar_confirmacao", lambda *args: False)

    with pytest.raises(RuntimeError, match="mesmo Parquet"):
        kaggle.subir()

    assert client.dataset_upload.call_count == 1


def test_status_indisponivel_nao_inicia_upload(publisher, monkeypatch):
    _, client = publisher
    monkeypatch.setattr(kaggle, "_status_dataset", lambda: None)

    with pytest.raises(RuntimeError, match="Status"):
        kaggle.subir()

    client.dataset_upload.assert_not_called()
