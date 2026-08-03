import pytest

from scraper.models import Job
from scraper.skills import (
    SkillExtractor,
    attach_skills,
    jobs_with_skills_by_area,
    normalize_tech,
    overall_skill_counts,
    skills_by_area,
)


@pytest.fixture(scope="module")
def ext():
    return SkillExtractor.from_file()


def test_normalize_tech_preserva_cerquilha_e_mais():
    assert normalize_tech("C# e C++") == "c# e c++"
    assert normalize_tech("Node.js") == "node js"
    assert normalize_tech("Programação Ágil") == "programacao agil"


def test_extrai_linguagens_e_frameworks(ext):
    found = ext.extract("Desenvolvedor Júnior", "Vaga com Python, Django e PostgreSQL.")
    assert {"Python", "Django", "PostgreSQL"} <= set(found)


def test_c_sharp_nao_vira_c_solto(ext):
    # "C#" nao pode ser reduzido a "c" e casar com qualquer letra c do texto.
    assert "C#" in ext.extract("Dev .NET", "Experiência com C# e SQL Server.")
    assert "C#" not in ext.extract("Analista", "Turno c de segunda a sexta.")


def test_nao_casa_dentro_de_outra_palavra(ext):
    found = ext.extract("Vaga em Goiânia", "Atuação presencial.")
    assert "Go" not in found
    java_only = ext.extract("Dev", "Stack JavaScript no front.")
    assert "JavaScript" in java_only
    assert "Java" not in java_only


def test_sem_texto_devolve_lista_vazia(ext):
    assert ext.extract("") == []
    assert ext.extract("Analista Júnior", "") == []


def test_resultado_sem_repeticao_e_ordenado(ext):
    found = ext.extract("Dev Python", "Python, python e mais Python. Também AWS.")
    assert found == sorted(found)
    assert found.count("Python") == 1


def test_attach_skills_preenche_o_campo():
    jobs = [Job(source="t", external_id="1", title="Dev Jr",
                description="Rotina com Java, Spring e Docker.")]
    attach_skills(jobs)
    assert {"Java", "Spring", "Docker"} <= set(jobs[0].skills)


def test_skills_by_area_agrupa_e_ordena():
    jobs = [
        Job(source="t", external_id="1", title="a", area="Data", skills=["SQL", "Python"]),
        Job(source="t", external_id="2", title="b", area="Data", skills=["SQL"]),
        Job(source="t", external_id="3", title="c", area="Backend", skills=["Java"]),
    ]
    result = skills_by_area(jobs)
    assert result["Data"][0] == ("SQL", 2)
    assert result["Backend"] == [("Java", 1)]


def test_skills_by_area_ignora_area_sem_skills():
    jobs = [Job(source="t", external_id="1", title="a", area="QA", skills=[])]
    assert "QA" not in skills_by_area(jobs)


def test_jobs_with_skills_by_area():
    """Base dos percentuais: nem toda vaga informa tecnologia."""
    jobs = [
        Job(source="t", external_id="1", title="a", area="Data", skills=["SQL"]),
        Job(source="t", external_id="2", title="b", area="Data", skills=[]),
        Job(source="t", external_id="3", title="c", area="Data", skills=["Python"]),
        Job(source="t", external_id="4", title="d", area="Backend", skills=[]),
    ]
    base = jobs_with_skills_by_area(jobs)
    assert base["Data"] == 2  # e não 3
    assert "Backend" not in base  # nenhuma vaga informa tecnologia


def test_jobs_with_skills_by_area_lista_vazia():
    assert jobs_with_skills_by_area([]) == {}


def test_overall_skill_counts():
    jobs = [
        Job(source="t", external_id="1", title="a", skills=["SQL", "Python"]),
        Job(source="t", external_id="2", title="b", skills=["SQL"]),
    ]
    assert overall_skill_counts(jobs)[0] == ("SQL", 2)


def test_skills_vao_para_o_csv_como_texto():
    job = Job(source="t", external_id="1", title="a", skills=["SQL", "Python"])
    assert job.to_row()["skills"] == "SQL, Python"
