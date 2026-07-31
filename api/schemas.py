"""Schemas Pydantic (respostas da API).

A API e somente leitura: os dados vem do pipeline de raspagem, entao nao ha
schema de escrita.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _TecnologiasComoNomes(BaseModel):
    """Serializa a relacao de tecnologias como uma lista simples de nomes.

    No banco `Vaga.tecnologias` e uma lista de objetos `Tecnologia`; na resposta
    da API interessa so `["Python", "SQL"]`.
    """

    @field_validator("tecnologias", mode="before", check_fields=False)
    @classmethod
    def _apenas_nomes(cls, value):
        if value is None:
            return []
        return sorted(getattr(item, "nome", item) for item in value)


class TecnologiaResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str = Field(examples=["Python"])
    grupo: str = Field(examples=["linguagens"])


class VagaOut(_TecnologiasComoNomes):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str = Field(description="Portal de origem.", examples=["gupy"])
    external_id: str = Field(description="Id da vaga no portal de origem.")
    title: str
    company: str | None = None
    area: str = Field(examples=["Data"])
    seniority: str | None = Field(default=None, examples=["Júnior"])
    location: str | None = None
    workplace_type: str | None = Field(default=None, examples=["Remoto"])
    published_date: date | None = Field(
        default=None,
        description="Data de publicação normalizada. Nula quando o portal não informa.",
    )
    url: str | None = None
    description: str | None = None
    area_score: float | None = None
    area_matches: str | None = Field(
        default=None,
        description="Keywords que dispararam a classificação, para auditoria.",
    )
    search_term: str | None = None
    tecnologias: list[str] = Field(default_factory=list, examples=[["Python", "SQL"]])
    created_at: datetime
    updated_at: datetime


class VagaResumo(_TecnologiasComoNomes):
    """Versao enxuta usada na listagem -- sem a descricao inteira."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    title: str
    company: str | None = None
    area: str
    seniority: str | None = None
    location: str | None = None
    workplace_type: str | None = None
    published_date: date | None = None
    url: str | None = None
    tecnologias: list[str] = Field(default_factory=list)


class VagaPage(BaseModel):
    """Envelope da listagem paginada."""

    total: int = Field(description="Total de vagas que casam com os filtros.")
    limit: int
    offset: int
    items: list[VagaResumo]


class AreaOut(BaseModel):
    area: str = Field(examples=["Suporte/Infra"])
    vagas: int = Field(description="Quantidade de vagas classificadas nesta área.")
    percentual: float = Field(description="Percentual sobre o total de vagas.")


class TecnologiaOut(BaseModel):
    nome: str = Field(examples=["Python"])
    grupo: str = Field(examples=["linguagens"])
    vagas: int = Field(description="Quantidade de vagas que citam esta tecnologia.")


class Erro(BaseModel):
    detail: str
