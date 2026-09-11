"""Testes do PoliteSession: delay, retry-config, tratamento de erros."""

import time
from unittest.mock import MagicMock

import pytest
import requests

from scraper.http_client import PoliteSession


@pytest.fixture
def polite():
    return PoliteSession(user_agent="test-agent", delay_seconds=0.0, max_retries=1)


def test_get_bem_sucedido_devolve_resposta(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    polite.session.get = MagicMock(return_value=resposta)

    result = polite.get("https://exemplo.com/vaga")

    assert result is resposta
    assert polite.request_count == 1
    assert polite.last_status_code == 200


def test_get_erro_http_guarda_o_status(polite):
    resposta = MagicMock()
    resposta.status_code = 404
    resposta.text = "nao encontrado"
    polite.session.get = MagicMock(return_value=resposta)

    result = polite.get("https://exemplo.com/vaga")

    assert result is None
    assert polite.last_status_code == 404


def test_get_repassa_timeout_padrao(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    polite.session.get = MagicMock(return_value=resposta)

    polite.get("https://exemplo.com/vaga")

    polite.session.get.assert_called_once_with(
        "https://exemplo.com/vaga", timeout=polite.timeout_seconds
    )


def test_retry_nao_respeita_retry_after_sem_teto(polite):
    # Cloudflare ja respondeu 429 com Retry-After de 23h: dormir tudo isso
    # travaria a coleta inteira. O backoff exponencial proprio ja espaca.
    adapter = polite.session.adapters["https://"]

    respects_retry_after = adapter.max_retries.respect_retry_after_header

    assert respects_retry_after is False


def test_get_com_impersonate_usa_sessao_cffi():
    sessao = PoliteSession(user_agent="t", delay_seconds=0.0, impersonate="chrome")
    resposta = MagicMock()
    resposta.status_code = 200
    sessao.session.get = MagicMock(return_value=resposta)

    result = sessao.get("https://exemplo.com/vaga")

    assert sessao._cffi is True
    assert result is resposta
    assert sessao.last_status_code == 200


def test_get_cffi_tenta_de_novo_em_429(monkeypatch):
    sessao = PoliteSession(
        user_agent="t", delay_seconds=0.0, max_retries=2,
        backoff_factor=0.0, impersonate="chrome",
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    respostas = iter([MagicMock(status_code=429, text="x"), MagicMock(status_code=200)])
    sessao.session.get = MagicMock(side_effect=lambda *a, **k: next(respostas))

    result = sessao.get("https://exemplo.com/vaga")

    assert result.status_code == 200
    assert sessao.session.get.call_count == 2


def test_get_devolve_none_em_falha_de_rede(polite):
    polite.session.get = MagicMock(
        side_effect=requests.RequestException("conexao recusada")
    )

    result = polite.get("https://exemplo.com/vaga")

    assert result is None
    assert polite.request_count == 1


def test_get_devolve_none_em_erro_http(polite):
    resposta = MagicMock()
    resposta.status_code = 500
    resposta.text = "erro interno"
    polite.session.get = MagicMock(return_value=resposta)

    result = polite.get("https://exemplo.com/vaga")

    assert result is None


def test_get_json_parseia_payload(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = {"data": [1, 2]}
    polite.session.get = MagicMock(return_value=resposta)

    result = polite.get_json("https://exemplo.com/api")

    assert result == {"data": [1, 2]}


def test_get_json_devolve_none_para_resposta_nao_json(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.side_effect = ValueError("nao e json")
    polite.session.get = MagicMock(return_value=resposta)

    result = polite.get_json("https://exemplo.com/api")

    assert result is None


def test_post_bem_sucedido_devolve_resposta(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    polite.session.post = MagicMock(return_value=resposta)

    result = polite.post("https://exemplo.com/form", json={"a": 1})

    assert result is resposta
    polite.session.post.assert_called_once_with(
        "https://exemplo.com/form", json={"a": 1}, timeout=polite.timeout_seconds
    )


def test_post_devolve_none_em_erro_http(polite):
    resposta = MagicMock()
    resposta.status_code = 429
    resposta.text = "rate limit"
    polite.session.post = MagicMock(return_value=resposta)

    result = polite.post("https://exemplo.com/form")

    assert result is None


def test_post_json_parseia_payload(polite):
    resposta = MagicMock()
    resposta.status_code = 200
    resposta.json.return_value = {"ok": True}
    polite.session.post = MagicMock(return_value=resposta)

    result = polite.post_json("https://exemplo.com/form")

    assert result == {"ok": True}


def test_wait_turn_espera_quando_chamado_rapido_demais(polite, monkeypatch):
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)
    polite.delay_seconds = 1.0
    polite._last_request_at = time.monotonic()

    polite._wait_turn()

    assert sleep.called


def test_wait_turn_nao_espera_apos_o_delay(polite, monkeypatch):
    sleep = MagicMock()
    monkeypatch.setattr(time, "sleep", sleep)
    polite.delay_seconds = 1.0
    polite._last_request_at = time.monotonic() - 5.0

    polite._wait_turn()

    assert not sleep.called


def test_context_manager_fecha_sessao():
    session = PoliteSession(user_agent="test-agent", delay_seconds=0.0)

    with session:
        fechar = session.session.close = MagicMock()

    fechar.assert_called_once()
