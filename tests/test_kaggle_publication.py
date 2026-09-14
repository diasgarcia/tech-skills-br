import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.snapshots import sha256
from scripts import export_kaggle as kaggle


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
