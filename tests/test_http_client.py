"""Testes do PoliteSession: delay, retry-config, tratamento de erros."""

import time
from unittest.mock import MagicMock

import pytest
import requests

from scraper.http_client import PoliteSession


@pytest.fixture
def polite():
    with PoliteSession(
        user_agent="test-agent", delay_seconds=0.0, max_retries=1, backoff_factor=0.0,
    ) as session:
        yield session


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


@pytest.mark.parametrize("impersonate", [None, "chrome"])
@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422, 501, 505])
def test_erros_definitivos_nao_sao_repetidos(impersonate, status):
    with PoliteSession(
        user_agent="t", delay_seconds=0, max_retries=3, backoff_factor=0,
        impersonate=impersonate,
    ) as session:
        session.session.get = MagicMock(return_value=MagicMock(status_code=status, text="erro"))

        result = session.get("https://example.com/job")

        assert result is None
        assert session.last_status_code == status
        assert session.session.get.call_count == 1
        assert session.request_count == session.attempt_count == 1


@pytest.mark.parametrize("impersonate", [None, "chrome"])
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retry_transitorio_tem_a_mesma_politica_nos_transportes(impersonate, status):
    with PoliteSession(
        user_agent="t", delay_seconds=0, max_retries=2, backoff_factor=0,
        impersonate=impersonate,
    ) as session:
        response = MagicMock(status_code=200)
        session.session.get = MagicMock(side_effect=[
            MagicMock(status_code=status, text="falha", headers={"Retry-After": "82800"}), response,
        ])

        result = session.get("https://example.com/job")

        assert result is response
        assert session.request_count == 1
        assert session.attempt_count == 2
        assert session.last_status_code == 200


@pytest.mark.parametrize("impersonate", [None, "chrome"])
def test_retry_de_rede_respeita_limite_e_nao_deixa_status_antigo(impersonate):
    with PoliteSession(
        user_agent="t", delay_seconds=0, max_retries=2, backoff_factor=0,
        impersonate=impersonate,
    ) as session:
        session.session.get = MagicMock(side_effect=[
            MagicMock(status_code=503, text="falha"), requests.Timeout(), requests.Timeout(),
        ])

        result = session.get("https://example.com/job")

        assert result is None
        assert session.last_status_code is None
        assert session.request_count == 1
        assert session.attempt_count == 3


def test_falha_nativa_cffi_pode_ser_repetida():
    from curl_cffi.requests.exceptions import Timeout

    with PoliteSession(
        user_agent="t", delay_seconds=0, max_retries=1, backoff_factor=0,
        impersonate="chrome",
    ) as session:
        response = MagicMock(status_code=200)
        session.session.get = MagicMock(side_effect=[Timeout("timeout"), response])

        result = session.get("https://example.com/job")

        assert result is response
        assert session.attempt_count == 2


@pytest.mark.parametrize("impersonate", [None, "chrome"])
def test_post_nao_repete_automaticamente_operacao_nao_idempotente(impersonate):
    with PoliteSession(
        user_agent="t", delay_seconds=0, max_retries=3, backoff_factor=0,
        impersonate=impersonate,
    ) as session:
        session.session.post = MagicMock(return_value=MagicMock(status_code=503, text="erro"))

        result = session.post("https://example.com/operation")

        assert result is None
        assert session.last_status_code == 503
        assert session.attempt_count == 1


def test_post_limpa_status_anterior_apos_falha_de_rede(polite):
    polite.last_status_code = 200
    polite.session.post = MagicMock(side_effect=requests.Timeout())

    result = polite.post("https://example.com/operation")

    assert result is None
    assert polite.last_status_code is None
    assert polite.attempt_count == 1


def test_get_aplica_delay_a_cada_tentativa_e_backoff_limitado(polite, monkeypatch):
    polite.backoff_factor = 0.5
    wait = MagicMock()
    sleep = MagicMock()
    monkeypatch.setattr(polite, "_wait_turn", wait)
    monkeypatch.setattr(time, "sleep", sleep)
    polite.session.get = MagicMock(side_effect=[
        MagicMock(status_code=429, text="erro", headers={"Retry-After": "82800"}),
        MagicMock(status_code=200),
    ])

    polite.get("https://example.com/job")

    assert wait.call_count == 2
    sleep.assert_called_once_with(0.5)
    assert polite.session.adapters["https://"].max_retries.total == 0
