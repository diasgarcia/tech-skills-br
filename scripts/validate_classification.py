"""Prepara uma amostra cega e avalia rotulos humanos, sem rede ou escrita no banco."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.classifier import AreaClassifier
from scraper.dedupe import _mesma_empresa
from scraper.models import normalize
from scraper.seniority import SeniorityFilter
from scraper.skills import SkillExtractor

SPLITS = ("development", "validation", "test")
NO_SENIORITY = "Não identificada no título"
KNOWN_CASES = ROOT / "docs" / "validacao" / "casos-conhecidos.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as file:
        return [json.loads(line) for line in file if line.strip()]


def provenance() -> dict:
    paths = sorted((ROOT / "scraper").glob("*.py"))
    paths += sorted((ROOT / "scraper" / "rules").glob("*.yml"))
    paths += [Path(__file__), KNOWN_CASES]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True,
    )
    return {
        "commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in paths},
    }


def read_database(path: Path) -> list[dict]:
    # mode=ro tambem impede criar um banco vazio quando o caminho esta errado.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT source, external_id, title, coalesce(description, '') AS description, "
            "coalesce(company, '') AS company, coalesce(url, '') AS url, "
            "published_date, created_at FROM vagas ORDER BY source, external_id"
        )]
    finally:
        connection.close()


def group_cases(rows: list[dict]) -> list[list[dict]]:
    """Agrupa URLs, descricoes iguais e titulo/empresa compativeis, transitivamente."""
    parent = list(range(len(rows)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    exact = {}
    titles = defaultdict(list)
    for i, row in enumerate(rows):
        keys = [("identity", row["source"], row["external_id"])]
        if row["url"].strip():
            keys.append(("url", row["url"].strip()))
        description = normalize(row["description"])
        if len(description) >= 100:
            keys.append(("description", description))
        for key in keys:
            if key in exact:
                parent[root(i)] = root(exact[key])
            else:
                exact[key] = i
        title = normalize(row["title"])
        for j in titles[title]:
            if _mesma_empresa(row["company"], rows[j]["company"]):
                parent[root(i)] = root(j)
        titles[title].append(i)
    grouped = defaultdict(list)
    for i, row in enumerate(rows):
        grouped[root(i)].append(row)
    return list(grouped.values())


def select_cases(rows: list[dict], known_ids: set[str], size: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    known, unseen = [], []
    for group in group_cases(rows):
        known_group = any(str(row["external_id"]) in known_ids for row in group)
        candidates = [row for row in group if str(row["external_id"]) in known_ids] if known_group else group
        row = dict(rng.choice(candidates))
        row["related_ids"] = sorted(f'{r["source"]}:{r["external_id"]}' for r in group)
        row["known_case"] = known_group
        (known if known_group else unseen).append(row)
    if size < 5 or size > len(known) + len(unseen):
        raise ValueError("Escolha pelo menos 5 casos e no maximo o total de grupos disponiveis.")
    dev_size = size - 2 * (size // 5)
    if len(known) > dev_size:
        raise ValueError("Aumente a amostra: os casos conhecidos devem caber no desenvolvimento.")
    rng.shuffle(unseen)
    selected = known + unseen[:size - len(known)]
    for i, row in enumerate(selected):
        row["case_id"] = f'{row["source"]}:{row["external_id"]}'
        row["split"] = "development" if i < dev_size else (
            "validation" if i < dev_size + size // 5 else "test"
        )
    return selected


def prepare(db: Path, output: Path, size: int, seed: int, known_path: Path) -> dict:
    if output.exists():
        raise ValueError("A pasta ja existe. Preserve a amostra congelada e use outra pasta.")
    known = load_json(known_path)
    rows = read_database(db)
    cases = select_cases(rows, set(known["external_ids"]), size, seed)
    labels = {
        "areas": AreaClassifier.from_file().area_names,
        "seniority": list(SeniorityFilter.from_file().include) + [NO_SENIORITY],
        "skills": sorted(SkillExtractor.from_file().skills),
    }
    output.mkdir(parents=True)
    save_json(output / "labels.json", labels)
    for split in SPLITS:
        save_json(output / f"cases-{split}.json", [c for c in cases if c["split"] == split])
        with (output / f"annotations-{split}.jsonl").open("x", encoding="utf-8") as file:
            for row in cases:
                if row["split"] == split:
                    annotation = {
                        "case_id": row["case_id"], "reviewer": "", "method": "",
                        "seen_during_rule_tuning": True if row["known_case"] else None,
                        "is_tech": None, "area": None, "seniority_title": None,
                        "skills": None, "skills_outside_taxonomy": [], "notes": "",
                    }
                    file.write(json.dumps(annotation, ensure_ascii=False) + "\n")
    manifest = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed, "database_rows": len(rows), "sample_size": len(cases),
        "sampling": "Um anuncio aleatorio por grupo; sorteio de grupos, com casos conhecidos no desenvolvimento.",
        "scope": "Anuncios retidos no banco local; nao estima recall dos filtros sobre anuncios descartados.",
        "holdout_status": "Provisorio: exige confirmacao humana de ausencia de uso no ajuste de regras.",
        "split_counts": dict(Counter(row["split"] for row in cases)),
        "source_counts": {split: dict(Counter(r["source"] for r in cases if r["split"] == split)) for split in SPLITS},
        "known_cases_sha256": digest(known_path), "provenance": provenance(),
        "frozen_sha256": {name: digest(output / name) for name in ("labels.json", *(f"cases-{s}.json" for s in SPLITS))},
    }
    save_json(output / "manifest.json", manifest)
    return manifest


def prf(tp: int, fp: int, fn: int) -> dict:
    return {
        "tp": tp, "fp": fp, "fn": fn, "support": tp + fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
    }


def multilabel_metrics(truth: list[set], predicted: list[set]) -> dict:
    if len(truth) != len(predicted) or not truth:
        raise ValueError("A avaliacao precisa de pares nao vazios de respostas e previsoes.")
    labels = sorted(set().union(*truth, *predicted))
    per_label = {}
    for label in labels:
        tp = sum(label in a and label in b for a, b in zip(truth, predicted))
        fp = sum(label not in a and label in b for a, b in zip(truth, predicted))
        fn = sum(label in a and label not in b for a, b in zip(truth, predicted))
        per_label[label] = prf(tp, fp, fn)
    micro = prf(*(sum(m[key] for m in per_label.values()) for key in ("tp", "fp", "fn")))
    return {
        "n": len(truth), "exact_match": sum(a == b for a, b in zip(truth, predicted)) / len(truth),
        "micro": micro,
        "macro_f1": sum(m["f1"] for m in per_label.values()) / len(labels) if labels else None,
        "per_label": per_label,
    }


def classification_metrics(truth: list[str], predicted: list[str]) -> dict:
    result = multilabel_metrics([{x} for x in truth], [{x} for x in predicted])
    labels = sorted(set(truth) | set(predicted))
    matrix = {a: {b: 0 for b in labels} for a in labels}
    for a, b in zip(truth, predicted):
        matrix[a][b] += 1
    result.update(accuracy=result["exact_match"], confusion_matrix=matrix)
    return result


def validate_annotations(cases: list[dict], annotations: list[dict], labels: dict, split: str) -> dict:
    by_id = {a["case_id"]: a for a in annotations}
    if len(by_id) != len(annotations) or set(by_id) != {c["case_id"] for c in cases}:
        raise ValueError("As anotacoes devem conter exatamente os IDs da particao, sem repeticoes.")
    for row in cases:
        a = by_id[row["case_id"]]
        if not isinstance(a.get("reviewer"), str) or not a["reviewer"].strip() or a.get("method") != "human":
            raise ValueError(f'{row["case_id"]}: informe reviewer e method=human apos revisao humana.')
        if type(a.get("seen_during_rule_tuning")) is not bool or type(a.get("is_tech")) is not bool:
            raise ValueError(f'{row["case_id"]}: preencha is_tech e seen_during_rule_tuning com true/false.')
        if split != "development" and (row["known_case"] or a["seen_during_rule_tuning"]):
            raise ValueError("Caso usado em ajuste de regras no holdout. Retire esta amostra de uso final.")
        if a.get("area") not in (labels["areas"] if a["is_tech"] else [""]):
            raise ValueError(f'{row["case_id"]}: area invalida; use nome canonico ou vazio para nao tech.')
        if a.get("seniority_title") not in labels["seniority"]:
            raise ValueError(f'{row["case_id"]}: seniority_title invalida.')
        for key in ("skills", "skills_outside_taxonomy"):
            values = a.get(key)
            if not isinstance(values, list) or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in values):
                raise ValueError(f'{row["case_id"]}: {key} deve ser uma lista explicita, inclusive quando vazia.')
            if len(values) != len(set(values)):
                raise ValueError(f'{row["case_id"]}: skill repetida.')
        if set(a["skills"]) - set(labels["skills"]):
            raise ValueError(f'{row["case_id"]}: skill desconhecida; use skills_outside_taxonomy.')
        if set(a["skills_outside_taxonomy"]) & set(labels["skills"]):
            raise ValueError(f'{row["case_id"]}: skill do vocabulario na lista externa.')
    return by_id


def evaluate(pack: Path, annotations: Path, split: str, final_test: bool = False) -> dict:
    if split not in SPLITS:
        raise ValueError("Particao desconhecida.")
    if split == "test" and not final_test:
        raise ValueError("Teste reservado. Use --final-test somente apos encerrar os ajustes.")
    if split == "test" and (pack / "test-opened.json").exists():
        raise ValueError("O teste desta amostra ja foi aberto. Consulte o resultado salvo.")
    manifest = load_json(pack / "manifest.json")
    for name, expected in manifest["frozen_sha256"].items():
        if digest(pack / name) != expected:
            raise ValueError("Amostra ou vocabulario alterado depois do congelamento.")
    cases = load_json(pack / f"cases-{split}.json")
    labels = load_json(pack / "labels.json")
    gold = validate_annotations(cases, load_jsonl(annotations), labels, split)
    clf, seniority, extractor = AreaClassifier.from_file(), SeniorityFilter.from_file(), SkillExtractor.from_file()
    predictions = {
        c["case_id"]: {
            "is_tech": clf.is_tech(c["title"], c["description"]),
            "area": clf.classify(c["title"], c["description"]).area,
            "seniority_title": seniority.label(c["title"]) or NO_SENIORITY,
            "skills": extractor.extract(c["title"], c["description"]),
        } for c in cases
    }
    ids = [c["case_id"] for c in cases]
    tech_ids = [i for i in ids if gold[i]["is_tech"]]
    metrics = {
        "is_tech_retained_sample": classification_metrics(
            [str(gold[i]["is_tech"]) for i in ids], [str(predictions[i]["is_tech"]) for i in ids]),
        "area_on_human_tech": classification_metrics(
            [gold[i]["area"] for i in tech_ids], [predictions[i]["area"] for i in tech_ids]) if tech_ids else None,
        "seniority_title_only": classification_metrics(
            [gold[i]["seniority_title"] for i in ids], [predictions[i]["seniority_title"] for i in ids]),
        "skills": multilabel_metrics(
            [set(gold[i]["skills"] + gold[i]["skills_outside_taxonomy"]) for i in ids],
            [set(predictions[i]["skills"]) for i in ids]),
    }
    return {
        "created_at": datetime.now(timezone.utc).isoformat(), "split": split,
        "manifest_sha256": digest(pack / "manifest.json"), "annotations_sha256": digest(annotations),
        "reviewers": sorted({a["reviewer"].strip() for a in gold.values()}),
        "provenance": provenance(), "parameters": {"title_boost": clf.title_boost, "min_score": clf.min_score},
        "metrics": metrics, "predictions": predictions,
        "outside_taxonomy_mentions": sum(len(a["skills_outside_taxonomy"]) for a in gold.values()),
        "limitations": [manifest["scope"],
            "Senioridade avalia apenas o titulo; nao valida o campo nativo da fonte nem o filtro completo.",
            "Amostra agrupada e historica; independencia depende da revisao dos casos ja observados.",
            "Zero divisao em precision/recall/F1 resulta em 0; macro usa rotulos presentes no gold ou na previsao.",
            "Revisores distintos nao implicam dupla anotacao independente ou concordancia medida."],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--db", type=Path, default=ROOT / "data" / "vagas.db")
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--size", type=int, default=300)
    prep.add_argument("--seed", type=int, default=20260912)
    prep.add_argument("--known-cases", type=Path, default=KNOWN_CASES)
    score = commands.add_parser("evaluate")
    score.add_argument("--pack", type=Path, required=True)
    score.add_argument("--annotations", type=Path, required=True)
    score.add_argument("--split", choices=SPLITS, default="validation")
    score.add_argument("--final-test", action="store_true")
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.db, args.output, args.size, args.seed, args.known_cases)
            print(json.dumps({"folder": str(args.output), "counts": result["split_counts"]}, ensure_ascii=False))
        else:
            if args.output.exists():
                raise ValueError("O resultado ja existe. Use outro arquivo para preservar o historico.")
            result = evaluate(args.pack, args.annotations, args.split, args.final_test)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.split == "test":
                save_json(args.pack / "test-opened.json", result)
            save_json(args.output, result)
            print(f"Resultado salvo em {args.output}")
        return 0
    except (ValueError, OSError, KeyError, sqlite3.Error) as error:
        parser.exit(2, f"Erro: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
