"""Exporta os dados consolidados do banco SQLite para a pasta `.github/pages/api/`.

Gera os endpoints estáticos JSON que alimentam o site e funcionam como uma API pública:
  - `.github/pages/api/resumo.json`      -> Metadados gerais, KPIs e distribuições
  - `.github/pages/api/vagas.json`       -> Lista consolidada de todas as vagas
  - `.github/pages/api/areas.json`       -> Ranking das áreas técnicas
  - `.github/pages/api/tecnologias.json`  -> Ranking de tecnologias demandadas
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.database import init_db, make_engine
from api.models import Tecnologia, Vaga, vaga_tecnologia

from scraper.config import PROJECT_ROOT

PAGES_API_DIR = PROJECT_ROOT / ".github" / "pages" / "api"

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
logger = logging.getLogger(__name__)


def export_all_pages_data(
    output_dir: Path | None = None, db_path: str | Path | None = None
) -> dict[str, Path]:
    """Exporta todos os endpoints JSON para `.github/pages/api/`."""
    out_dir = output_dir or PAGES_API_DIR

    out_dir.mkdir(parents=True, exist_ok=True)

    eng = make_engine(db_path)
    init_db(eng)
    with Session(eng) as db:
        total_vagas = db.scalar(select(func.count(Vaga.id))) or 0

        if total_vagas == 0:
            logger.warning("Nenhuma vaga encontrada no banco para exportar.")
            return {}


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
                "percentual": round(100.0 * c / total_vagas, 1),
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
        ) or total_vagas

        tecnologias_payload = [
            {
                "posicao": idx + 1,
                "nome": nome,
                "grupo": grupo,
                "vagas": c,
                "percentual_total": round(100.0 * c / total_vagas, 1),
                "percentual_base_tech": round(100.0 * c / vagas_com_tech, 1),
            }
            for idx, (nome, grupo, c) in enumerate(tech_rows)
        ]

        workplace_rows = db.execute(
            select(Vaga.workplace_type, func.count(Vaga.id))
            .group_by(Vaga.workplace_type)
            .order_by(func.count(Vaga.id).desc())
        ).all()
        modalidades = [
            {"modalidade": m or "Não informado", "vagas": c, "percentual": round(100.0 * c / total_vagas, 1)}
            for m, c in workplace_rows
        ]

        regiao_rows = db.execute(
            select(Vaga.regiao, func.count(Vaga.id))
            .group_by(Vaga.regiao)
            .order_by(func.count(Vaga.id).desc())
        ).all()
        regioes = [
            {"regiao": r or "Não informado", "vagas": c, "percentual": round(100.0 * c / total_vagas, 1)}
            for r, c in regiao_rows
        ]

        polo_rows = db.execute(
            select(Vaga.polo, func.count(Vaga.id))
            .group_by(Vaga.polo)
            .order_by(func.count(Vaga.id).desc())
            .limit(15)
        ).all()
        polos = [
            {"polo": p or "Não informado", "vagas": c, "percentual": round(100.0 * c / total_vagas, 1)}
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
            ) or 1

            skills_by_area[area_name] = {
                "total_vagas": area_info["vagas"],
                "vagas_com_tech": area_base_tech,
                "skills": [
                    {
                        "nome": nome,
                        "grupo": grupo,
                        "vagas": c,
                        "percentual": round(100.0 * c / area_base_tech, 1),
                    }
                    for nome, grupo, c in area_tech_rows
                ]
            }

        resumo_payload = {
            "metadados": {
                "total_vagas": total_vagas,
                "total_empresas": total_empresas,
                "periodo": f"{data_min.strftime('%d/%m/%Y') if data_min else '2022'} a {data_max.strftime('%d/%m/%Y') if data_max else '2026'}",
                "data_atualizacao": data_max.strftime("%d/%m/%Y") if data_max else "2026-08-25",
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
            techs = [t.nome for t in v.tecnologias]
            vagas_payload.append({
                "id": v.id,
                "titulo": v.title,
                "empresa": v.company or "Confidencial",
                "area": v.area,
                "senioridade": v.seniority or "Júnior",
                "localidade": v.location or "Brasil",
                "polo": v.polo,
                "regiao": v.regiao,
                "modalidade": v.workplace_type or "Presencial",
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
    parser = argparse.ArgumentParser(description="Exporta a API JSON estática para docs/api/.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Diretório de saída.")
    args = parser.parse_args()
    export_all_pages_data(args.output_dir)


if __name__ == "__main__":
    main()
