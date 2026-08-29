"""Avalia a contribuicao marginal de uma nova fonte de vagas.

Compara o conjunto unico da base atual (seed/vagas.csv) com o conjunto
unico apos adicionar o CSV da fonte nova:

    baseline = dedupe(seed atual)
    combinado = dedupe(seed atual + CSV da nova fonte)
    novas unicas = len(combinado) - len(baseline)

Nao basta contar vagas da fonte que sobreviveram ao dedupe: em uma
duplicata, o algoritmo preserva a ocorrencia com a descricao mais longa,
independentemente da fonte.

Uso:
    python scripts/evaluate_source.py --csv output/vagas_AAAAMMDD_HHMMSS.csv

O CSV da fonte vem de uma rodada piloto:
    python main.py --sources <fonte> --max-pages 2
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SEED_CSV = PROJECT_ROOT / "seed" / "vagas.csv"

NIVEIS_ENTRADA = {"Júnior", "Estágio", "Trainee", "Aprendiz"}


def _ler_jobs(csv_path: Path) -> list:
    from scraper.models import Job

    jobs: list[Job] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh):
            skills = [
                s.strip()
                for s in (linha.get("skills") or "").split(",")
                if s.strip()
            ]
            jobs.append(
                Job(
                    source=linha.get("source") or "",
                    external_id=linha.get("external_id") or "",
                    title=linha.get("title") or "",
                    company=linha.get("company") or "",
                    url=linha.get("url") or "",
                    description=linha.get("description") or "",
                    location=linha.get("location") or "",
                    workplace_type=linha.get("workplace_type") or "",
                    published_date=linha.get("published_date") or "",
                    search_term=linha.get("search_term") or "",
                    area=linha.get("area") or "",
                    seniority=linha.get("seniority") or "",
                    skills=skills,
                    regiao=linha.get("regiao") or "",
                    polo=linha.get("polo") or "",
                )
            )
    return jobs


def avaliar(csv_fonte: Path, fonte: str | None = None) -> dict:
    from scraper.dedupe import deduplicate

    seed_jobs = _ler_jobs(SEED_CSV)
    fonte_jobs = _ler_jobs(csv_fonte)

    if fonte:
        fonte_jobs = [j for j in fonte_jobs if j.source == fonte]
    coletadas = len(fonte_jobs)
    elegiveis = [j for j in fonte_jobs if j.seniority in NIVEIS_ENTRADA]

    baseline, _ = deduplicate(seed_jobs)
    combinado, _ = deduplicate(seed_jobs + fonte_jobs)

    novas_unicas = max(0, len(combinado) - len(baseline))
    elegivel_n = len(elegiveis)
    marginal = round(100 * novas_unicas / elegivel_n, 1) if elegivel_n else 0.0

    def pct(pred) -> float:
        return round(100 * sum(1 for j in fonte_jobs if pred(j)) / coletadas, 1) if coletadas else 0.0

    return {
        "fonte": fonte or csv_fonte.stem,
        "coletadas": coletadas,
        "elegiveis": elegivel_n,
        "baseline": len(baseline),
        "combinado": len(combinado),
        "novas_unicas": novas_unicas,
        "sobreposicao": max(0, coletadas - novas_unicas),
        "marginal": marginal,
        "com_descricao": pct(lambda j: bool(j.description.strip())),
        "com_localizacao": pct(lambda j: bool(j.location.strip())),
        "com_skills": pct(lambda j: bool(j.skills)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Avalia a contribuicao marginal de uma nova fonte."
    )
    parser.add_argument("--csv", type=Path, required=True,
                        help="CSV da rodada piloto da fonte nova.")
    parser.add_argument("--fonte", default=None,
                        help="Filtrar o CSV por fonte (ex.: solides).")
    args = parser.parse_args(argv)

    r = avaliar(args.csv, args.fonte)

    print(f"\nFonte: {r['fonte']}")
    print(f"Coletadas:               {r['coletadas']}")
    print(f"Elegíveis entry-level:   {r['elegiveis']}")
    print(f"Vagas únicas baseline: {r['baseline']}")
    print(f"Vagas únicas combinado: {r['combinado']}")
    print(f"Novas únicas:            {r['novas_unicas']}")
    print(f"Sobreposição estimada:   {r['sobreposicao']}")
    print(f"Contribuição marginal:   {r['marginal']}%")
    print(f"Com descrição:           {r['com_descricao']}%")
    print(f"Com localização:         {r['com_localizacao']}%")
    print(f"Com skills detectadas:   {r['com_skills']}%")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
