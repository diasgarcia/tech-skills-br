"""Cliente HTTP educado: User-Agent identificavel, delay entre requests e retry."""

from __future__ import annotations

import logging
import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class PoliteSession:
    """Wrapper sobre `requests.Session` que espaca as chamadas e tenta de novo em falhas.

    - Retry (com backoff exponencial) em 429/5xx transitorios e erros de conexao.
    - Delay minimo entre requests, com jitter para nao criar um padrao robotico.
    - Devolve `None` ao esgotar falhas de rede/HTTP; erros de programacao propagam.
    """

    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 1.5,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        impersonate: str | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._last_request_at = 0.0
        self.request_count = 0
        self.attempt_count = 0
        self.last_status_code: int | None = None
        self._network_errors = (requests.RequestException,)

        cabecalhos = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8,application/json;q=0.5",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
        }

        self._cffi = impersonate is not None
        if self._cffi:
            # Modo navegador: curl_cffi imita o fingerprint TLS do Chrome,
            # o que derruba o bot-check do Cloudflare em sites como o
            # Vagas.com (o requests puro era flagado e tomava 429/403).
            from curl_cffi import requests as cffi_requests

            self._network_errors += (cffi_requests.RequestsError,)
            self.session = cffi_requests.Session(impersonate=impersonate)
            self.session.headers.update(cabecalhos)
            return

        self.session = requests.Session()
        self.session.headers.update(cabecalhos)

        # Uma unica politica para os dois transportes. O adaptador nao repete
        # por conta propria, evitando multiplicar silenciosamente tentativas.
        retry = Retry(total=0, respect_retry_after_header=False)
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=4)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining + random.uniform(0, 0.4))
        self._last_request_at = time.monotonic()

    def _request(self, method: str, url: str, **kwargs) -> requests.Response | None:
        """Uma chamada logica; cada tentativa respeita delay e politica comum.

        `request_count` mantem a contagem historica de chamadas logicas.
        `attempt_count` inclui repeticoes feitas aqui, nao redirecionamentos
        internos do transporte. Retry-After nao altera o limite de espera.
        """
        kwargs.setdefault("timeout", self.timeout_seconds)
        self.request_count += 1
        self.last_status_code = None
        send = getattr(self.session, method)
        # POST pode ter efeito mesmo quando a resposta se perde. Sem contrato
        # de idempotencia, o cliente nao repete essa operacao automaticamente.
        retry_limit = self.max_retries if method == "get" else 0
        for attempt in range(retry_limit + 1):
            self._wait_turn()
            self.attempt_count += 1
            self.last_status_code = None
            try:
                response = send(url, **kwargs)
            except self._network_errors as exc:
                if attempt >= retry_limit:
                    logger.warning("Falha de rede em %s: %s", url, exc)
                    return None
            else:
                self.last_status_code = response.status_code
                if response.status_code < 400:
                    return response
                if response.status_code not in RETRYABLE_STATUSES or attempt >= retry_limit:
                    logger.warning(
                        "HTTP %s em %s (params=%s, resp=%s)",
                        response.status_code, url, kwargs.get("params"), response.text[:200],
                    )
                    return None
            backoff = self.backoff_factor * (2**attempt)
            if backoff > 0:
                time.sleep(backoff)
        return None

    def get(self, url: str, **kwargs) -> requests.Response | None:
        """GET com delay + retry. Devolve `None` em caso de falha definitiva."""
        return self._request("get", url, **kwargs)

    def get_json(self, url: str, **kwargs) -> dict | list | None:
        response = self.get(url, **kwargs)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("Resposta nao-JSON em %s (content-type=%s)", url,
                           response.headers.get("content-type"))
            return None

    def post(self, url: str, **kwargs) -> requests.Response | None:
        """POST com delay, sem retry automatico de operacao nao idempotente."""
        return self._request("post", url, **kwargs)


    def post_json(self, url: str, **kwargs) -> dict | list | None:
        response = self.post(url, **kwargs)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("Resposta nao-JSON em %s (content-type=%s)", url,
                           response.headers.get("content-type"))
            return None

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "PoliteSession":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
