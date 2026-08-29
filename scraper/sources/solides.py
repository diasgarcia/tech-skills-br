"""Coletor da Solides (ATS de vagas).

Endpoint usado: o mesmo que o front publico de https://vagas.solides.com.br
chama no browser, sem autenticacao:

    GET https://apigw.solides.com.br/jobs/v3/portal-vacancies-new

Descoberto decodificando o bundle JS do site (Network -> chamadas do proprio
frontend). O endpoint anterior (api.solides.jobs/vacancy/public/search) exige
token/API key e foi descartado.

Detalhes praticos descobertos testando o endpoint ao vivo:

- `occupationAreas=tecnologia` filtra por area de atuacao (3.795 vagas).
- `seniorities=junior` filtra por nivel (1.142 vagas, 115 paginas).
  Valores "estagio"/"trainee"/"aprendiz" NAO filtram de fato (estagio devolve
  0; os demais devolvem o conjunto sem filtro). Por isso estagio/trainee
  entram via busca textual `title=`.
- `title=<termo>` faz busca textual no titulo.
- `size` e ignorado: cada pagina devolve 10 vagas fixas.
- Pagina alem do fim devolve 200 com `data: []` (seguro para parar).
- A descricao ja vem completa em HTML na listagem (nao precisa enriquecer).
- A ordenacao da listagem e por data (pagina 1 = mais recentes).

Como o projeto so quer nivel de entrada, esta fonte usa os filtros nativos
de tecnologia + junior/estagio/trainee em vez de repetir os 40 termos de
busca do projeto -- mesmo padrao do ProgramaThor.
"""

from __future__ import annotations

import logging

from ..models import Job, normalize_workplace
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = "https://apigw.solides.com.br/jobs/v3/portal-vacancies-new"

# "termo" -> filtros nativos do portal para nivel de entrada.
#
# O filtro `title=` do portal casa por palavra: "estagio" NAO cobre
# "estagiario" (medido: 222 vs 159 vagas, com 45 exclusivas de
# "estagiario"). Por isso as duas variacoes viram filtros separados; a
# deduplicacao do pipeline junta as sobrepostas.
FILTROS_NIVEL_ENTRADA: dict[str, dict[str, str]] = {
    "Júnior": {"occupationAreas": "tecnologia", "seniorities": "junior"},
    "Estágio": {"occupationAreas": "tecnologia", "title": "estagio"},
    "Estagiário": {"occupationAreas": "tecnologia", "title": "estagiario"},
    "Trainee": {"occupationAreas": "tecnologia", "title": "trainee"},
    # O portal nao tem filtro nativo de aprendiz; title=aprendiz retorna
    # um conjunto frouxo (nao filtra de verdade). Coletamos mesmo assim e
    # o filtro de senioridade do pipeline corta o ruido.
    "Aprendiz": {"occupationAreas": "tecnologia", "title": "aprendiz"},
}

PAGE_SIZE = 10  # o endpoint ignora `size`; pagina fixa de 10 vagas


class SolidesSource(JobSource):
    name = "solides"
    label = "Solides"
    MAX_PAGES_PER_TERM = 200

    def fetch(self, terms: list[str]) -> list[Job]:
        """Ignora os termos do projeto e usa os filtros nativos do portal.

        A busca por `title=` casa so o titulo e e menos completa que o
        filtro de senioridade nativo; para o recorte de tecnologia +
        nivel de entrada, os filtros do portal entregam o dado com menos
        requests e sem ruido.
        """
        if terms:
            logger.debug(
                "[%s] termos ignorados; usando os filtros nativos %s",
                self.name, list(FILTROS_NIVEL_ENTRADA),
            )
        return super().fetch(list(FILTROS_NIVEL_ENTRADA))

    def fetch_term(self, term: str) -> list[Job]:
        """Coleta um filtro nativo (`term` e chave de FILTROS_NIVEL_ENTRADA)."""
        params = dict(FILTROS_NIVEL_ENTRADA.get(term, {"title": term}))

        jobs: list[Job] = []
        seen: set[str] = set()

        start_page = max(1, self.settings.start_page)
        end_page = max(start_page, self.page_limit())

        for page in range(start_page, end_page + 1):
            payload = self.session.get_json(
                API_URL, params={**params, "page": page}
            )
            if not payload:
                break

            batch = ((payload.get("data") or {}).get("data")) or []
            if not batch:
                break  # pagina alem do fim (200 com data vazio)

            new_in_page = 0
            for raw in batch:
                job = self._parse(raw, term)
                if job is None or job.external_id in seen:
                    continue
                seen.add(job.external_id)
                jobs.append(job)
                new_in_page += 1

            if new_in_page == 0:
                break  # API repetindo resultados; evita loop inutil

        return jobs

    def _parse(self, raw: dict, term: str) -> Job | None:
        job_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        if job_id is None or not title:
            return None

        city = ((raw.get("city") or {}).get("name") or "").strip()
        state = ((raw.get("state") or {}).get("name") or "").strip()
        location = ", ".join(part for part in (city, state) if part)

        created = (raw.get("createdAt") or "")[:10]
        if created and created < "2026-01-01":
            return None

        job_type = (raw.get("jobType") or "").strip()
        workplace = normalize_workplace(
            "remote" if raw.get("homeOffice") else job_type
        )

        return Job(
            source=self.name,
            external_id=str(job_id),
            title=title,
            company=raw.get("companyName") or "",
            url=raw.get("redirectLink") or "",
            description=raw.get("description") or "",
            location=location,
            workplace_type=workplace,
            published_date=created,
            search_term=term,
            # So confia no filtro nativo de junior (seniorities=junior).
            # Estagio/Trainee/Aprendiz vem de busca por titulo, que o
            # portal aplica de forma frouxa ("title=aprendiz" devolve
            # pleno e tech lead); o filtro de senioridade do pipeline
            # decide pelo titulo nesses casos.
            seniority=term if term == "Júnior" else "",
        )
