import csv

from scraper.export import build_ranking, export_all
from scraper.models import Job


def _jobs():
    return [
        Job(source="gupy", external_id="1", title="Dev Backend Jr",
            company="ACME", area="Backend", seniority="Júnior"),
        Job(source="gupy", external_id="2", title="Dev Backend Jr 2",
            company="Globex", area="Backend", seniority="Júnior"),
        Job(source="vagas", external_id="3", title="Analista de Dados Jr",
            company="Initech", area="Data", seniority="Júnior"),
    ]


def test_build_ranking_ordena_por_quantidade():
    ranking = build_ranking(_jobs())
    assert ranking[0]["area"] == "Backend"
    assert ranking[0]["vagas"] == 2
    assert ranking[0]["posicao"] == 1
    assert ranking[0]["percentual"] == 66.7
    assert ranking[1]["area"] == "Data"


def test_build_ranking_lista_vazia():
    assert build_ranking([]) == []


def test_export_all_sem_graficos(tmp_path):
    files = export_all(_jobs(), tmp_path, meta={"sources": ["Gupy"], "terms_count": 1},
                       with_charts=False)
    assert set(files) == {"jobs_csv", "ranking_csv", "skills_csv", "report_md"}
    for path in files.values():
        assert path.exists() and path.stat().st_size > 0

    with open(files["jobs_csv"], encoding="utf-8-sig", newline="") as fh:
        assert "skills" in (csv.DictReader(fh).fieldnames or [])


def test_export_all_com_graficos(tmp_path):
    files = export_all(_jobs(), tmp_path, meta={"sources": ["Gupy"], "terms_count": 1})
    # O grafico de areas sempre sai; o de skills depende de volume por area.
    assert "chart_areas" in files
    assert files["chart_areas"].suffix == ".png"
    assert files["chart_areas"].stat().st_size > 0

    with open(files["jobs_csv"], encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 3
    assert {r["area"] for r in rows} == {"Backend", "Data"}

    with open(files["ranking_csv"], encoding="utf-8-sig", newline="") as fh:
        ranking = list(csv.DictReader(fh))
    assert ranking[0]["area"] == "Backend"
    assert ranking[0]["vagas"] == "2"

    report = files["report_md"].read_text(encoding="utf-8")
    assert "Ranking de areas" in report
    assert "Backend" in report
