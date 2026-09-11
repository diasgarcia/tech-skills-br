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
    jobs = _jobs()

    ranking = build_ranking(jobs)

    assert ranking[0]["area"] == "Backend"
    assert ranking[0]["vagas"] == 2
    assert ranking[0]["posicao"] == 1
    assert ranking[0]["percentual"] == 66.7
    assert ranking[1]["area"] == "Data"


def test_build_ranking_lista_vazia():
    ranking = build_ranking([])

    assert ranking == []


def test_export_all_sem_graficos(tmp_path):
    jobs = _jobs()
    meta = {"sources": ["Gupy"], "terms_count": 1}

    files = export_all(jobs, tmp_path, meta=meta, with_charts=False)
    valid_files = [path.exists() and path.stat().st_size > 0 for path in files.values()]
    with open(files["jobs_csv"], encoding="utf-8-sig", newline="") as fh:
        fieldnames = csv.DictReader(fh).fieldnames or []

    assert set(files) == {"jobs_csv", "ranking_csv", "skills_csv", "report_md"}
    assert all(valid_files)
    assert "skills" in fieldnames


def test_export_all_com_graficos(tmp_path):
    jobs = _jobs()
    meta = {"sources": ["Gupy"], "terms_count": 1}

    files = export_all(jobs, tmp_path, meta=meta)
    with open(files["jobs_csv"], encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(files["ranking_csv"], encoding="utf-8-sig", newline="") as fh:
        ranking = list(csv.DictReader(fh))
    report = files["report_md"].read_text(encoding="utf-8")

    assert "chart_areas" in files
    assert files["chart_areas"].suffix == ".png"
    assert files["chart_areas"].stat().st_size > 0
    assert len(rows) == 3
    assert {r["area"] for r in rows} == {"Backend", "Data"}
    assert ranking[0]["area"] == "Backend"
    assert ranking[0]["vagas"] == "2"
    assert "Ranking de areas" in report
    assert "Backend" in report
