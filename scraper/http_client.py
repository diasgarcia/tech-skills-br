"""Cliente HTTP educado: User-Agent identificavel, delay entre requests e retry."""

from __future__ import annotations

import logging
import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class PoliteSession:
    """Wrapper sobre `requests.Session` que espaca as chamadas e tenta de novo em falhas.

    - Retry automatico (com backoff exponencial) em 429/5xx e erros de conexao.
    - Delay minimo entre requests, com jitter para nao criar um padrao robotico.
    - Nunca levanta excecao para o chamador: devolve `None` quando desiste.
    """

    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 1.5,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self._last_request_at = 0.0
        self.request_count = 0
        self.last_status_code: int | None = None

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8,application/json;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
            }
        )

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
            # Sem teto, um Retry-After grande travaria a coleta: o Cloudflare
            # ja respondeu 429 com Retry-After de 23h. O backoff exponencial
            # proprio (acima) ja espaca os retries de forma segura.
            respect_retry_after_header=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=4)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining + random.uniform(0, 0.4))
        self._last_request_at = time.monotonic()

    def get(self, url: str, **kwargs) -> requests.Response | None:
        """GET com delay + retry. Devolve `None` em caso de falha definitiva."""
        self._wait_turn()
        kwargs.setdefault("timeout", self.timeout_seconds)
        self.request_count += 1
        self.last_status_code = None
        try:
            response = self.session.get(url, **kwargs)
        except requests.RequestException as exc:
            logger.warning("Falha de rede em %s: %s", url, exc)
            return None

        self.last_status_code = response.status_code
        if response.status_code >= 400:
            logger.warning(
                "HTTP %s em %s (params=%s, resp=%s)",
                response.status_code,
                url,
                kwargs.get("params"),
                response.text[:200],
            )
            return None
        return response

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
        """POST com delay + retry. Devolve `None` em caso de falha definitiva."""
        self._wait_turn()
        kwargs.setdefault("timeout", self.timeout_seconds)
        self.request_count += 1
        try:
            response = self.session.post(url, **kwargs)
        except requests.RequestException as exc:
            logger.warning("Falha de rede em %s: %s", url, exc)
            return None

        if response.status_code >= 400:
            logger.warning(
                "HTTP %s em %s (json=%s, resp=%s)",
                response.status_code,
                url,
                kwargs.get("json"),
                response.text[:200],
            )
            return None
        return response


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
