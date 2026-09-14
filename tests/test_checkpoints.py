import csv
from dataclasses import fields

import pytest

import scraper.checkpoints as checkpoints
import scraper.pipeline as pipeline
from scraper.checkpoints import CheckpointError, JobCheckpoint, checkpoint_receipts
from scraper.config import Settings
from scraper.export import export_jobs_csv
from scraper.models import Job


def _job(source="abler", external_id="007", **overrides):
    return Job(
        source=source, external_id=external_id,
        title="Desenvolvedor Python Júnior", company="ACME",
        url=f"https://example.com/{external_id}", description="Requisitos: Python e SQL.",
        **overrides,
    )


def test_checkpoint_preserva_campos_e_ids_textuais(tmp_path):
    job = _job(skills=["SQL", "Nome, com virgula"], area_score=4.2)
    job.description = "Texto com &lt;literal&gt; e <exemplo> ja normalizado."
    checkpoint = JobCheckpoint(tmp_path / "partial.csv", "abler")

    checkpoint.save([job, job])
    restored = checkpoint.load()

    assert restored == [job]
    assert restored[0].external_id == "007"


def test_le_checkpoint_legado_completo(tmp_path):
    job = _job(skills=["SQL", "Python"])
    path = tmp_path / "partial.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[field.name for field in fields(Job)])
        writer.writeheader()
        writer.writerow(job.to_row())

    restored = JobCheckpoint(path, "abler").load()

    assert restored == [job]


@pytest.mark.parametrize("content", ["", "external_id,title\n7,incompleta\n", '"nao termina'])
def test_checkpoint_invalido_e_preservado_para_revisao(tmp_path, content):
    path = tmp_path / "partial.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(CheckpointError, match="arquivo preservado"):
        JobCheckpoint(path, "abler").load()

    assert path.read_text(encoding="utf-8") == content


def test_falha_na_gravacao_preserva_checkpoint_anterior(tmp_path, monkeypatch):
    checkpoint = JobCheckpoint(tmp_path / "partial.csv", "abler")
    original = _job()
    checkpoint.save([original])

    def fail_replace(*args):
        raise OSError("falha simulada antes da substituicao")

    monkeypatch.setattr(checkpoints.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulada"):
        checkpoint.save([original, _job(external_id="8")])

    assert checkpoint.load() == [original]
    assert list(tmp_path.iterdir()) == [checkpoint.path]


def test_confirmacao_nao_apaga_checkpoint_modificado_apos_captura(tmp_path):
    original = _job()
    checkpoint = JobCheckpoint(tmp_path / "abler_partial.csv", "abler")
    checkpoint.save([original])
    receipt, = checkpoint_receipts([original], tmp_path)
    checkpoint.save([original, _job(external_id="8")])

    confirmed = receipt.confirm()

    assert confirmed is False
    assert len(checkpoint.load()) == 2


def test_nao_confirma_fonte_ausente_ou_checkpoint_recebido_parcialmente(tmp_path):
    original = _job()
    checkpoint = JobCheckpoint(tmp_path / "abler_partial.csv", "abler")
    checkpoint.save([original, _job(external_id="8")])

    absent = checkpoint_receipts([_job(source="recrutei")], tmp_path)
    partial = checkpoint_receipts([original], tmp_path)

    assert absent == []
    assert partial == []
    assert checkpoint.path.exists()


@pytest.mark.parametrize("source", ["abler", "recrutei"])
def test_pipeline_confirma_checkpoint_somente_depois_de_exportar(tmp_path, monkeypatch, source):
    original = _job(source=source)
    checkpoint = JobCheckpoint(tmp_path / f"{source}_partial.csv", source)
    checkpoint.save([original])
    monkeypatch.setattr(pipeline, "collect", lambda settings: (checkpoint.load(), [], 0))
    export = pipeline.export_all

    def checked_export(*args):
        assert checkpoint.path.exists()
        return export(*args)

    monkeypatch.setattr(pipeline, "export_all", checked_export)
    settings = Settings(output_dir=tmp_path, sources=[source], enrich_linkedin=False)

    result = pipeline.run(settings)
    with result.files["jobs_csv"].open(encoding="utf-8-sig", newline="") as stream:
        exported = list(csv.DictReader(stream))

    assert len(exported) == 1
    assert exported[0]["external_id"] == "007"
    assert not checkpoint.path.exists()


@pytest.mark.parametrize("source", ["abler", "recrutei"])
def test_falha_na_exportacao_mantem_dados_para_retomar(tmp_path, monkeypatch, source):
    original = _job(source=source)
    checkpoint = JobCheckpoint(tmp_path / f"{source}_partial.csv", source)
    checkpoint.save([original])
    monkeypatch.setattr(pipeline, "collect", lambda settings: (checkpoint.load(), [], 0))

    def failed_export(*args):
        raise OSError("disco indisponivel")

    monkeypatch.setattr(pipeline, "export_all", failed_export)
    settings = Settings(output_dir=tmp_path, sources=[source], enrich_linkedin=False)

    with pytest.raises(OSError, match="disco indisponivel"):
        pipeline.run(settings)

    assert checkpoint.load() == [original]


def test_csv_final_nao_fica_parcial_em_falha(tmp_path, monkeypatch):
    original = _job()
    path = export_jobs_csv([original], tmp_path, stamp="fixo")
    before = path.read_bytes()

    def fail_row():
        raise ValueError("registro invalido")

    monkeypatch.setattr(original, "to_row", fail_row)

    with pytest.raises(ValueError, match="registro invalido"):
        export_jobs_csv([original], tmp_path, stamp="fixo")

    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
