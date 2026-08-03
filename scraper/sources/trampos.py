"""Coletor do Trampos.co.

O site e uma SPA em Ember: o HTML entregue traz so um `<noscript>` de fallback,
sem link nem id por vaga. O que serve e a API JSON que o app consome, publica e
sem autenticacao, descoberta inspecionando a aba Network:

    GET https://trampos.co/api/v2/opportunities?tr=<termo>&page=<n>

Parametros (nomes nada obvios, mapeados por tentativa contra a API):
  `tr`   busca textual -- cobre titulo e descricao. E o unico filtro de texto
         que funciona: `q`, `s`, `category` e afins sao ignorados.
  `lc`   localizacao (texto).
  `page` paginacao; o envelope traz `pagination.total_pages`.

Particularidades que o codigo trata:

- O portal e **misto**: publica vagas de Comunicacao e de TI no mesmo lugar.
  A categoria nativa (`category_name`) entra na descricao para o portao de
  relevancia do projeto poder decidir.
- `hybrid` vem sempre; `home_office` as vezes vem nulo.
- A listagem **nao traz a descricao da vaga nem a cidade**. Existe uma
  `company.description`, mas ela descreve a EMPRESA -- usa-la para classificar
  faria qualquer vaga de uma empresa de tecnologia parecer vaga de tecnologia.
  Por isso so entram fatos da propria vaga.
"""

from __future__ import annotations

import logging

from ..models import HIBRIDO, PRESENCIAL, REMOTO, Job
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = "https://trampos.co/api/v2/opportunities"
SITE_URL = "https://trampos.co"

# `type_slug` que ja indica nivel de entrada, sem depender do titulo.
TIPOS_DE_ENTRADA = {"estagio": "Estágio"}


class TramposSource(JobSource):
    name = "trampos"
    label = "Trampos.co"

    def fetch_term(self, term: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()

        for page in range(1, self.settings.max_pages_per_term + 1):
            payload = self.session.get_json(API_URL, params={"tr": term, "page": page})
            if not payload:
                break

            batch = payload.get("opportunities") or []
            if not batch:
                break

            for raw in batch:
                job = self._parse(raw, term)
                if job is None or job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)

            paginacao = payload.get("pagination") or {}
            total_pages = paginacao.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                break

        return jobs

    def _parse(self, raw: dict, term: str) -> Job | None:
        job_id = raw.get("id")
        title = (raw.get("name") or "").strip()
        if job_id is None or not title:
            return None

        empresa = raw.get("custom_company_name") or ""
        if not empresa:
            empresa = ((raw.get("company") or {}).get("name") or "").strip()

        return Job(
            source=self.name,
            external_id=str(job_id),
            title=title,
            company=empresa,
            url=self._url_da_vaga(raw),
            description=self._descricao(raw),
            location="",  # a listagem nao traz cidade
            workplace_type=self._modalidade(raw),
            published_date=(raw.get("published_at") or "")[:10],
            search_term=term,
            seniority=TIPOS_DE_ENTRADA.get(raw.get("type_slug") or "", ""),
        )

    @staticmethod
    def _url_da_vaga(raw: dict) -> str:
        """A API nao devolve a URL da vaga, mas as de compartilhamento contem ela."""
        for chave in ("email_share_url", "whatsapp_share_url"):
            url = raw.get(chave) or ""
            if "/share/" in url:
                return url.split("/share/")[0]
        slug = (raw.get("name") or "").strip()
        return f"{SITE_URL}/oportunidades/{raw.get('id')}" if slug else SITE_URL

    @staticmethod
    def _modalidade(raw: dict) -> str:
        """`home_office` pode vir nulo; `hybrid` vem sempre.

        Quando nenhuma das duas marca, o portal esta dizendo que a vaga e
        presencial -- remoto e hibrido sao os casos que ele sinaliza.
        """
        if raw.get("home_office"):
            return REMOTO
        if raw.get("hybrid"):
            return HIBRIDO
        return PRESENCIAL

    @staticmethod
    def _descricao(raw: dict) -> str:
        """Fatos da vaga. NAO usa `company.description`, que fala da empresa."""
        partes: list[str] = []
        if raw.get("category_name"):
            partes.append(f"Categoria: {raw['category_name']}.")
        if raw.get("type_name"):
            partes.append(f"Tipo: {raw['type_name']}.")
        salario = (raw.get("salary") or "").strip()
        if salario and salario.upper() != "NÃO DIVULGADA":
            partes.append(f"Salário: {salario}.")
        return " ".join(partes)
