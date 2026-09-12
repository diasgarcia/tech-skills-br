"""Contratos da amostragem cega, protecao do teste e metricas da avaliacao."""

import json
from pathlib import Path
import sqlite3

import pytest

from scripts import validate_classification as validation


def job(i, **overrides):
    row = {
        "source": "gupy", "external_id": str(i), "title": f"Cargo {i}",
        "company": f"Empresa {i}", "description": "", "url": f"https://example.org/{i}",
    }
    return row | overrides


@pytest.fixture
def pack(tmp_path):
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "CREATE TABLE vagas (source TEXT, external_id TEXT, title TEXT, description TEXT, "
            "company TEXT, url TEXT, published_date TEXT, created_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO vagas VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
            [("gupy", str(i), "Desenvolvedor Python Júnior", "Usar Python.", f"Marca{i}", f"https://example.org/{i}") for i in range(10)],
        )
    known = tmp_path / "known.json"
    validation.save_json(known, {"external_ids": ["0"]})
    folder = tmp_path / "pack"
    validation.prepare(db, folder, 10, 42, known)
    return folder


def annotate(pack, split="validation", **overrides):
    rows = validation.load_jsonl(pack / f"annotations-{split}.jsonl")
    for row in rows:
        row.update({
            "reviewer": "Revisor de teste", "method": "human", "seen_during_rule_tuning": False,
            "is_tech": True, "area": "Backend", "seniority_title": "Júnior",
            "skills": ["Python"], "skills_outside_taxonomy": [],
        } | overrides)
    path = pack / f"completed-{split}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return path


def test_metricas_multiclasse_com_erros_conhecidos():
    truth, predicted = ["A", "A", "B", "C"], ["A", "B", "B", "B"]

    result = validation.classification_metrics(truth, predicted)

    assert result["accuracy"] == 0.5
    assert result["per_label"]["A"]["precision"] == 1
    assert result["per_label"]["A"]["recall"] == 0.5
    assert result["per_label"]["B"]["f1"] == 0.5
    assert result["macro_f1"] == pytest.approx(7 / 18)
    assert result["confusion_matrix"]["C"]["B"] == 1
    assert result["micro"]["f1"] == 0.5


def test_skills_contam_omissao_falso_positivo_e_listas_vazias():
    truth = [{"Python", "SQL"}, set(), {"Skill nova"}]
    predicted = [{"Python", "Java"}, set(), set()]

    result = validation.multilabel_metrics(truth, predicted)

    assert result["exact_match"] == pytest.approx(1 / 3)
    assert result["micro"]["precision"] == 0.5
    assert result["micro"]["recall"] == pytest.approx(1 / 3)
    assert result["micro"]["f1"] == 0.4
    assert result["per_label"]["Skill nova"]["fn"] == 1


def test_sem_skills_nao_inventa_f1_perfeito():
    result = validation.multilabel_metrics([set()], [set()])

    assert result["exact_match"] == 1
    assert result["micro"]["f1"] == 0
    assert result["macro_f1"] is None


def test_agrupamento_transitivo_impede_copias_em_particoes_diferentes():
    rows = [
        job(1, title="Analista", company="Minsait"),
        job(2, title="ANALISTA", company="Minsait Indra Company"),
        job(3, url="https://example.org/2"),
        job(4),
    ]

    groups = validation.group_cases(rows)

    assert sorted(len(g) for g in groups) == [1, 3]


def test_descricao_republicada_agrupa_mesmo_com_titulo_diferente():
    description = "Atividades e requisitos especificos deste anuncio. " * 4
    rows = [job(1, description=description), job(2, description=description.upper())]

    groups = validation.group_cases(rows)

    assert len(groups) == 1


def test_sorteio_reproduzivel_e_caso_conhecido_fica_no_desenvolvimento():
    rows = [job(i) for i in range(30)]

    first = validation.select_cases(rows, {"29"}, 20, 73)
    second = validation.select_cases(rows, {"29"}, 20, 73)

    assert first == second
    assert next(c for c in first if c["external_id"] == "29")["split"] == "development"
    assert len({c["case_id"] for c in first}) == 20
    assert [sum(c["split"] == split for c in first) for split in validation.SPLITS] == [12, 4, 4]


def test_preparacao_cega_preserva_texto_e_nao_preanota(pack):
    cases = validation.load_json(pack / "cases-validation.json")
    annotations = validation.load_jsonl(pack / "annotations-validation.jsonl")
    manifest = validation.load_json(pack / "manifest.json")

    assert len(cases) == 2
    assert all(c["description"] == "Usar Python." for c in cases)
    assert not {"area", "skills", "seniority", "predictions"} & cases[0].keys()
    assert all(a["skills"] is None and a["is_tech"] is None for a in annotations)
    assert manifest["split_counts"] == {"development": 6, "validation": 2, "test": 2}
    assert "scraper/rules/skills.yml" in manifest["provenance"]["sha256"]


def test_banco_inexistente_nao_e_criado(tmp_path):
    path = tmp_path / "missing.db"

    with pytest.raises(sqlite3.OperationalError):
        validation.read_database(path)

    assert not path.exists()


def test_pasta_congelada_nao_e_sobrescrita(pack):
    with pytest.raises(ValueError, match="pasta ja existe"):
        validation.prepare(Path("unused"), pack, 10, 42, Path("unused"))


def test_formulario_incompleto_nao_gera_metricas(pack):
    with pytest.raises(ValueError, match="reviewer"):
        validation.evaluate(pack, pack / "annotations-validation.jsonl", "validation")


@pytest.mark.parametrize("overrides, message", [
    ({"seen_during_rule_tuning": True}, "Caso usado"),
    ({"skills": None}, "lista explicita"),
    ({"skills": ["Pythom"]}, "skill desconhecida"),
    ({"method": "AI"}, "method=human"),
    ({"is_tech": "true"}, "true/false"),
    ({"area": "Inventada"}, "area invalida"),
])
def test_recusa_referencia_invalida(pack, overrides, message):
    annotations = annotate(pack, **overrides)

    with pytest.raises(ValueError, match=message):
        validation.evaluate(pack, annotations, "validation")


def test_recusa_amostra_modificada(pack):
    path = pack / "cases-validation.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="congelamento"):
        validation.evaluate(pack, pack / "annotations-validation.jsonl", "validation")


def test_recusa_ids_repetidos_e_subamostra_selecionada(pack):
    cases = validation.load_json(pack / "cases-validation.json")
    labels = validation.load_json(pack / "labels.json")
    rows = validation.load_jsonl(annotate(pack))

    with pytest.raises(ValueError, match="exatamente os IDs"):
        validation.validate_annotations(cases, [rows[0], rows[0]], labels, "validation")
    with pytest.raises(ValueError, match="exatamente os IDs"):
        validation.validate_annotations(cases, rows[:1], labels, "validation")


def test_avaliacao_offline_conta_skills_fora_do_vocabulario(pack):
    annotations = annotate(pack, skills_outside_taxonomy=["Skill nova"])

    result = validation.evaluate(pack, annotations, "validation")

    assert result["metrics"]["seniority_title_only"]["accuracy"] == 1
    assert result["metrics"]["skills"]["per_label"]["Skill nova"]["fn"] == 2
    assert result["metrics"]["skills"]["micro"]["recall"] == 0.5
    assert result["parameters"] == {"title_boost": 3.0, "min_score": 3.0}
    assert result["outside_taxonomy_mentions"] == 2


def test_teste_final_exige_abertura_explicita_e_preserva_resultado(pack):
    annotations = annotate(pack, "test")
    result_path = pack / "final.json"
    arguments = ["evaluate", "--pack", str(pack), "--annotations", str(annotations),
                 "--split", "test", "--output", str(result_path)]

    with pytest.raises(SystemExit) as error:
        validation.main(arguments)
    exit_code = validation.main(arguments + ["--final-test"])
    saved = validation.load_json(result_path)
    with pytest.raises(ValueError, match="ja foi aberto"):
        validation.evaluate(pack, annotations, "test", final_test=True)

    assert error.value.code == 2
    assert exit_code == 0
    assert validation.load_json(pack / "test-opened.json") == saved
