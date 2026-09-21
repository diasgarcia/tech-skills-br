"""Remocao conservadora de vagas duplicadas.

As identidades fortes sao usadas primeiro: o id da fonte, a URL exata e o id
da vaga embutido no link. A comparacao por texto e apenas um fallback entre
fontes diferentes. Ela exige titulo e empresa compativeis, a mesma cidade e
datas de publicacao separadas por no maximo sete dias.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import unquote, urlsplit

from .models import Job, normalize

_RUIDO_EMPRESA = {
    "ltda", "sa", "eireli", "epp", "me", "mei", "inc", "llc", "corp",
    "group", "grupo", "company", "holding", "participacoes",
    "brasil", "brazil", "do", "da", "de", "dos", "das", "e", "em",
    "solucoes", "servicos", "sistemas", "tecnologia", "tecnologias",
    "informatica", "consultoria", "consultores", "associados",
    "confidencial", "empresa", "multinacional", "vagas",
    # Termos curtos genericos. Marcas reais de duas letras, como MV, FI e EY,
    # continuam disponiveis para identificar a empresa.
    "ti", "it", "rh", "co", "on", "br", "ia", "ai",
    "na", "no", "ao", "os", "as", "an", "of", "sp",
}

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
_DIGITOS_LONGOS = re.compile(r"\d{7,}")
_SEGMENTO_DIGITOS = re.compile(r"^\d{4,6}$")
_DIGITOS_INICIAIS = re.compile(r"^(\d{5,})-")
_TOKEN_COM_DIGITO = re.compile(r"^(?=[^\d]*\d)[A-Za-z0-9_=+%]{16,}$")
_SUFIXOS_COMPOSTOS = {"com", "net", "org", "gov", "edu", "adv", "eng", "esp", "ind"}

_SEPARADOR_LOCAL = re.compile(r"\s*(?:,|/|\s-\s)\s*", re.I)
_LOCAL_GENERICO = {
    "", "brasil", "brazil", "nacional", "todo brasil", "remoto", "remota",
    "home office", "nao informado",
}
_UF_POR_NOME = {
    "acre": "ac", "alagoas": "al", "amapa": "ap", "amazonas": "am",
    "bahia": "ba", "ceara": "ce", "distrito federal": "df",
    "espirito santo": "es", "goias": "go", "maranhao": "ma",
    "mato grosso": "mt", "mato grosso do sul": "ms", "minas gerais": "mg",
    "para": "pa", "paraiba": "pb", "parana": "pr", "pernambuco": "pe",
    "piaui": "pi", "rio de janeiro": "rj", "rio grande do norte": "rn",
    "rio grande do sul": "rs", "rondonia": "ro", "roraima": "rr",
    "santa catarina": "sc", "sao paulo": "sp", "sergipe": "se",
    "tocantins": "to",
}
_UFS = frozenset(_UF_POR_NOME.values())


def _identidade_empresa(nome: str) -> frozenset[str]:
    """Palavras que identificam a empresa, inclusive marcas de duas letras."""
    return frozenset(
        palavra
        for palavra in normalize(nome).split()
        if palavra not in _RUIDO_EMPRESA and len(palavra) >= 2
    )


def _mesma_empresa(a: str, b: str) -> bool:
    """Um nome e uma variacao do outro?"""
    palavras_a = _identidade_empresa(a)
    palavras_b = _identidade_empresa(b)
    if not palavras_a or not palavras_b:
        return False
    return palavras_a <= palavras_b or palavras_b <= palavras_a


def _dominio(netloc: str) -> str:
    host = netloc.lower().split("@")[-1].split(":")[0].strip(".")
    partes = [parte for parte in host.split(".") if parte]
    if len(partes) < 2:
        return ""
    if len(partes) >= 3 and len(partes[-1]) == 2 and partes[-2] in _SUFIXOS_COMPOSTOS:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def identidade_no_link(url: str | None) -> str:
    """Devolve o id da vaga carregado pelo link, quando ele e confiavel."""
    partes = urlsplit(url or "")
    if partes.scheme not in {"http", "https"}:
        return ""

    caminho = unquote(partes.path)
    if encontrado := _UUID.search(caminho):
        return f"uuid:{encontrado.group(0).lower()}"

    dominio = _dominio(partes.netloc)
    if not dominio:
        return ""

    segmentos = [segmento for segmento in caminho.split("/") if segmento]
    for segmento in segmentos:
        if _TOKEN_COM_DIGITO.match(segmento):
            return f"{dominio}:{segmento}"
    for segmento in segmentos:
        if _SEGMENTO_DIGITOS.match(segmento):
            return f"{dominio}:{segmento}"
    if encontrados := _DIGITOS_LONGOS.findall(caminho):
        return f"{dominio}:{max(encontrados, key=len)}"
    for segmento in segmentos:
        if encontrado := _DIGITOS_INICIAIS.match(segmento):
            return f"{dominio}:{encontrado.group(1)}"
    return ""


def _identidade_local(local: str | None) -> tuple[str, str] | None:
    bruto = (local or "").strip()
    if not bruto:
        return None

    primeira_parte = _SEPARADOR_LOCAL.split(bruto, maxsplit=1)[0]
    cidade = normalize(primeira_parte)
    cidade = re.sub(r"\s+e regiao$", "", cidade).strip()
    if cidade in _LOCAL_GENERICO:
        return None

    texto = normalize(bruto)
    uf = ""
    for nome, sigla in _UF_POR_NOME.items():
        if re.search(rf"\b{re.escape(nome)}\b", texto):
            uf = sigla
            break
    if not uf:
        palavras = set(texto.split())
        encontradas = palavras & _UFS
        if len(encontradas) == 1:
            uf = next(iter(encontradas))
    return cidade, uf


def _mesmo_local(a: str | None, b: str | None) -> bool:
    local_a = _identidade_local(a)
    local_b = _identidade_local(b)
    if local_a is None or local_b is None or local_a[0] != local_b[0]:
        return False
    return not (local_a[1] and local_b[1] and local_a[1] != local_b[1])


def _data_publicacao(valor: str | None) -> date | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    return None


def _datas_proximas(a: str | None, b: str | None, dias: int = 7) -> bool:
    data_a = _data_publicacao(a)
    data_b = _data_publicacao(b)
    return data_a is not None and data_b is not None and abs((data_a - data_b).days) <= dias


def _mesma_vaga_por_texto(a: Job, b: Job) -> bool:
    return (
        a.source != b.source
        and normalize(a.title) == normalize(b.title)
        and _mesma_empresa(a.company, b.company)
        and _mesmo_local(a.location, b.location)
        and _datas_proximas(a.published_date, b.published_date)
    )


def _melhor_descricao(atual: Job | None, candidata: Job) -> Job:
    if atual is None or len(candidata.description) > len(atual.description):
        if atual is not None:
            candidata.search_term = atual.search_term or candidata.search_term
        return candidata
    return atual


def deduplicate(jobs: list[Job]) -> tuple[list[Job], int]:
    """Devolve as vagas unicas e a quantidade removida."""
    por_fonte: dict[str, Job] = {}
    for job in jobs:
        por_fonte[job.source_key] = _melhor_descricao(por_fonte.get(job.source_key), job)

    por_url: dict[str, Job] = {}
    sem_url: list[Job] = []
    for job in por_fonte.values():
        url = (job.url or "").strip()
        if not url:
            sem_url.append(job)
            continue
        por_url[url] = _melhor_descricao(por_url.get(url), job)

    por_link: dict[str, Job] = {}
    sem_id_no_link: list[Job] = []
    for job in [*por_url.values(), *sem_url]:
        identidade = identidade_no_link(job.url)
        if not identidade:
            sem_id_no_link.append(job)
            continue
        por_link[identidade] = _melhor_descricao(por_link.get(identidade), job)

    por_titulo: dict[str, list[Job]] = {}
    for job in [*por_link.values(), *sem_id_no_link]:
        por_titulo.setdefault(normalize(job.title), []).append(job)

    unicas: list[Job] = []
    for grupo in por_titulo.values():
        representantes: list[Job] = []
        for job in grupo:
            for indice, escolhido in enumerate(representantes):
                if _mesma_vaga_por_texto(job, escolhido):
                    representantes[indice] = _melhor_descricao(escolhido, job)
                    break
            else:
                representantes.append(job)
        unicas.extend(representantes)

    return unicas, len(jobs) - len(unicas)
