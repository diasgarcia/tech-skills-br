"""Exporta os dados consolidados do banco SQLite para a pasta `api/web/`.

Gera os endpoints estaticos JSON que alimentam o site e funcionam como uma API publica:
  - `api/web/resumo.json`      -> Metadados gerais, KPIs e distribuicoes
  - `api/web/vagas.json`       -> Lista consolidada de todas as vagas
  - `api/web/areas.json`       -> Ranking das areas tecnicas
  - `api/web/tecnologias.json`  -> Ranking de tecnologias citadas nos anuncios
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import func, select

from api.database import read_session
from api.models import Tecnologia, Vaga, vaga_tecnologia

from scraper.config import PROJECT_ROOT

PAGES_API_DIR = PROJECT_ROOT / "api" / "web"

logger = logging.getLogger(__name__)


def percentual(quantidade: int, base: int) -> float:
    """Protege a divisão sem alterar a quantidade publicada."""
    return round(100.0 * quantidade / base, 1) if base else 0.0


def export_all_pages_data(
    output_dir: Path | None = None, db_path: str | Path | None = None,
    *, generated_at: datetime | None = None,
) -> dict[str, Path]:
    """Exporta os endpoints; a data de atualização é a geração em UTC.

    O período refere-se exclusivamente às datas de publicação dos anúncios.
    Não é inferida uma data de coleta a partir desses campos.
    """
    out_dir = output_dir or PAGES_API_DIR
    gerado_em = generated_at or datetime.now(timezone.utc)
    if gerado_em.tzinfo is None:
        raise ValueError("generated_at deve incluir o fuso horário")
    gerado_em = gerado_em.astimezone(timezone.utc)

    out_dir.mkdir(parents=True, exist_ok=True)

    with read_session(db_path) as db:
        total_vagas = db.scalar(select(func.count(Vaga.id))) or 0

        if total_vagas == 0:
            logger.warning("Nenhuma vaga encontrada no banco para exportar.")


        total_empresas = db.scalar(
            select(func.count(func.distinct(Vaga.company))).where(Vaga.company.isnot(None))
        ) or 0

        data_min = db.scalar(
            select(func.min(Vaga.published_date)).where(Vaga.published_date.isnot(None))
        )
        data_max = db.scalar(
            select(func.max(Vaga.published_date)).where(Vaga.published_date.isnot(None))
        )

        area_rows = db.execute(
            select(Vaga.area, func.count(Vaga.id))
            .group_by(Vaga.area)
            .order_by(func.count(Vaga.id).desc())
        ).all()
        areas_payload = [
            {
                "area": a,
                "vagas": c,
                "percentual": percentual(c, total_vagas),
            }
            for a, c in area_rows
        ]

        # Todo o vocabulario, inclusive tecnologias sem nenhuma mencao.
        tech_rows = db.execute(
            select(
                Tecnologia.nome,
                Tecnologia.grupo,
                func.count(vaga_tecnologia.c.vaga_id).label("total_vagas")
            )
            .outerjoin(
                vaga_tecnologia,
                Tecnologia.id == vaga_tecnologia.c.tecnologia_id,
            )
            .group_by(Tecnologia.id, Tecnologia.nome, Tecnologia.grupo)
            .order_by(
                func.count(vaga_tecnologia.c.vaga_id).desc(), Tecnologia.nome
            )
        ).all()

        vagas_com_tech = db.scalar(
            select(func.count(func.distinct(vaga_tecnologia.c.vaga_id)))
        ) or 0

        tecnologias_payload = [
            {
                "posicao": idx + 1,
                "nome": nome,
                "grupo": grupo,
                "vagas": c,
                "percentual_total": percentual(c, total_vagas),
                "percentual_base_tech": percentual(c, vagas_com_tech),
            }
            for idx, (nome, grupo, c) in enumerate(tech_rows)
        ]

        workplace_rows = db.execute(
            select(Vaga.workplace_type, func.count(Vaga.id))
            .group_by(Vaga.workplace_type)
            .order_by(func.count(Vaga.id).desc())
        ).all()
        modalidades = [
            {"modalidade": m or "Não informado", "vagas": c, "percentual": percentual(c, total_vagas)}
            for m, c in workplace_rows
        ]

        regiao_rows = db.execute(
            select(Vaga.regiao, func.count(Vaga.id))
            .group_by(Vaga.regiao)
            .order_by(func.count(Vaga.id).desc())
        ).all()
        regioes = [
            {"regiao": r or "Não informado", "vagas": c, "percentual": percentual(c, total_vagas)}
            for r, c in regiao_rows
        ]

        polo_rows = db.execute(
            select(Vaga.polo, func.count(Vaga.id))
            .group_by(Vaga.polo)
            .order_by(func.count(Vaga.id).desc())
            .limit(15)
        ).all()
        polos = [
            {"polo": p or "Não informado", "vagas": c, "percentual": percentual(c, total_vagas)}
            for p, c in polo_rows
        ]

        skills_by_area = {}
        for area_info in areas_payload:
            area_name = area_info["area"]
            area_tech_rows = db.execute(
                select(
                    Tecnologia.nome,
                    Tecnologia.grupo,
                    func.count(Vaga.id).label("vagas")
                )
                .join(vaga_tecnologia, Tecnologia.id == vaga_tecnologia.c.tecnologia_id)
                .join(Vaga, Vaga.id == vaga_tecnologia.c.vaga_id)
                .where(Vaga.area == area_name)
                .group_by(Tecnologia.id, Tecnologia.nome, Tecnologia.grupo)
                .order_by(func.count(Vaga.id).desc())
            ).all()

            area_base_tech = db.scalar(
                select(func.count(func.distinct(Vaga.id)))
                .join(vaga_tecnologia, Vaga.id == vaga_tecnologia.c.vaga_id)
                .where(Vaga.area == area_name)
            ) or 0

            skills_by_area[area_name] = {
                "total_vagas": area_info["vagas"],
                "vagas_com_tech": area_base_tech,
                "skills": [
                    {
                        "nome": nome,
                        "grupo": grupo,
                        "vagas": c,
                        "percentual": percentual(c, area_base_tech),
                    }
                    for nome, grupo, c in area_tech_rows
                ]
            }

        resumo_payload = {
            "metadados": {
                "total_vagas": total_vagas,
                "total_empresas": total_empresas,
                "periodo": (
                    f"{data_min:%d/%m/%Y} a {data_max:%d/%m/%Y}"
                    if data_min and data_max else "Não informado"
                ),
                "data_atualizacao": gerado_em.strftime("%d/%m/%Y"),
                "gerado_em": gerado_em.isoformat(),
                "endpoints_disponiveis": [
                    "/api/resumo.json",
                    "/api/vagas.json",
                    "/api/areas.json",
                    "/api/tecnologias.json"
                ]
            },
            "areas": areas_payload,
            "modalidades": modalidades,
            "regioes": regioes,
            "polos": polos,
            "skills_by_area": skills_by_area,
        }


        vagas_db = db.execute(
            select(Vaga).order_by(Vaga.published_date.desc().nullslast(), Vaga.id.desc())
        ).scalars().all()

        vagas_payload = []
        for v in vagas_db:
            techs = sorted(t.nome for t in v.tecnologias)
            vagas_payload.append({
                "id": v.id,
                "titulo": v.title,
                "empresa": v.company or "Confidencial",
                "area": v.area,
                "senioridade": v.seniority or "Não informado",
                "localidade": v.location or "Não informado",
                "polo": v.polo,
                "regiao": v.regiao,
                "modalidade": v.workplace_type or "Não informado",
                "data_publicacao": v.published_date.strftime("%d/%m/%Y") if v.published_date else None,
                "fonte": v.source,
                "url": v.url,
                "tecnologias": techs
            })

        files = {
            "resumo": out_dir / "resumo.json",
            "areas": out_dir / "areas.json",
            "tecnologias": out_dir / "tecnologias.json",
            "vagas": out_dir / "vagas.json"
        }

        with open(files["resumo"], "w", encoding="utf-8") as f:
            json.dump(resumo_payload, f, ensure_ascii=False, indent=2)

        with open(files["areas"], "w", encoding="utf-8") as f:
            json.dump(areas_payload, f, ensure_ascii=False, indent=2)

        with open(files["tecnologias"], "w", encoding="utf-8") as f:
            json.dump(tecnologias_payload, f, ensure_ascii=False, indent=2)

        with open(files["vagas"], "w", encoding="utf-8") as f:
            json.dump(vagas_payload, f, ensure_ascii=False, indent=2)

        logger.info(f"Endpoints da API estática exportados em: {out_dir}")
        return files


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Exporta a API JSON estática para api/web/.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Diretório de saída.")
    parser.add_argument("--db", type=Path, default=None, help="Arquivo SQLite existente.")
    args = parser.parse_args()
    export_all_pages_data(args.output_dir, args.db)


if __name__ == "__main__":
    main()
