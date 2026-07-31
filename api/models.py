"""Tabelas do banco (SQLAlchemy 2.0).

Uma vaga guarda os mesmos campos que o CSV do scraper produz, com duas
diferencas:

  - `id` inteiro, gerado pelo banco, porque o CSV nao tem chave propria e a API
    precisa de uma URL estavel (`/vagas/{id}`). A identidade real da vaga
    continua sendo o par (source, external_id), que e UNIQUE.
  - as tecnologias saem da string "Excel, Python, SQL" e viram uma relacao
    muitos-para-muitos, que e o que permite filtrar e contar de verdade.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

vaga_tecnologia = Table(
    "vaga_tecnologia",
    Base.metadata,
    Column("vaga_id", ForeignKey("vagas.id", ondelete="CASCADE"), primary_key=True),
    Column("tecnologia_id", ForeignKey("tecnologias.id", ondelete="CASCADE"),
           primary_key=True),
)


class Tecnologia(Base):
    __tablename__ = "tecnologias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    grupo: Mapped[str] = mapped_column(String(40), nullable=False)

    vagas: Mapped[list["Vaga"]] = relationship(
        secondary=vaga_tecnologia, back_populates="tecnologias"
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<Tecnologia {self.nome}>"


class Vaga(Base):
    __tablename__ = "vagas"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_vaga_source_external_id"),
        Index("ix_vagas_area", "area"),
        Index("ix_vagas_workplace_type", "workplace_type"),
        Index("ix_vagas_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(40), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(40), nullable=False)
    seniority: Mapped[str | None] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(200))
    workplace_type: Mapped[str | None] = mapped_column(String(20))
    published_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    area_score: Mapped[float | None] = mapped_column(Float)
    area_matches: Mapped[str | None] = mapped_column(Text)
    search_term: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tecnologias: Mapped[list[Tecnologia]] = relationship(
        secondary=vaga_tecnologia, back_populates="vagas", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover - conveniencia no shell
        return f"<Vaga {self.id} {self.title[:40]!r}>"
