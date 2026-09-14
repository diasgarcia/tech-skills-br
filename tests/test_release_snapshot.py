"""Publicacao e recuperacao de snapshots com um cliente GitHub sem rede."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy.orm import Session

from api.database import init_db, make_engine
from api.models import Vaga
from api.snapshots import MANIFEST_NAME, sha256, verify_manifest
from scripts import release_snapshot


def create_database(path):
    engine = make_engine(path)
    init_db(engine)
    with Session(engine) as db:
        db.add(Vaga(source="teste", external_id="001", title="Python", area="Backend"))
        db.commit()
    engine.dispose()
    return path


@pytest.fixture
def remote_snapshot(tmp_path):
    db = create_database(tmp_path / "source.db")
    directory = tmp_path / "remote"
    release_snapshot.prepare_snapshot(db, directory, "0" * 64)
    return directory


class FakeGitHubRelease(release_snapshot.GitHubRelease):
    """Executa o contrato gh em memoria, inclusive downloads parciais."""

    def __init__(self, directory):
        super().__init__()
        self.assets = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.upload_attempted = False
        self.uploaded_manifest = None
        self.fail_upload = False
        self.fail_confirmation = False
        self.change_csv_on_confirmation = False

    def _run(self, *args):
        if args[0] == "view":
            if self.upload_attempted and self.fail_confirmation:
                raise OSError("Falha ao confirmar a publicacao")
            if self.upload_attempted and self.change_csv_on_confirmation:
                self.assets["vagas.csv"] += b"\n"
                manifest = json.loads(self.assets[MANIFEST_NAME])
                manifest["artifacts"]["vagas.csv"] = hashlib.sha256(self.assets["vagas.csv"]).hexdigest()
                self.assets[MANIFEST_NAME] = json.dumps(manifest).encode()
                self.change_csv_on_confirmation = False
            return json.dumps({"assets": [{"name": name} for name in self.assets]})
        if args[0] == "download":
            name = args[args.index("--pattern") + 1]
            directory = Path(args[args.index("--dir") + 1])
            (directory / name).write_bytes(self.assets[name])
            return ""
        if args[0] == "upload":
            self.upload_attempted = True
            files = [Path(arg) for arg in args[2:-1]]
            self.uploaded_manifest = json.loads(files[-1].read_text(encoding="utf-8"))
            for file in files:
                self.assets[file.name] = file.read_bytes()
                if self.fail_upload:
                    raise OSError("Falha apos envio parcial")
            return ""
        raise AssertionError(args)


def test_manifesto_identifica_os_arquivos_preparados(remote_snapshot):
    manifest = verify_manifest(remote_snapshot)

    assert manifest["snapshot_id"] == sha256(remote_snapshot / "vagas.db")
    assert manifest["artifacts"]["vagas.csv"] == sha256(remote_snapshot / "vagas.csv")
    assert manifest["parent_sha256"] == "0" * 64


@pytest.mark.parametrize("filename", ["vagas.db", "vagas.csv"])
def test_manifesto_recusa_hash_inconsistente(remote_snapshot, filename):
    with (remote_snapshot / filename).open("ab") as file:
        file.write(b"alterado")

    with pytest.raises(ValueError, match="hash divergente"):
        verify_manifest(remote_snapshot)


@pytest.mark.parametrize("replacement", [None, [], {"schema_version": 2}, {"schema_version": 1, "parent_sha256": "invalido"}])
def test_manifesto_malformado_e_recusado(remote_snapshot, replacement):
    (remote_snapshot / MANIFEST_NAME).write_text(json.dumps(replacement), encoding="utf-8")

    with pytest.raises(ValueError):
        verify_manifest(remote_snapshot)


def test_download_instala_apenas_base_verificada_e_estado(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    local = tmp_path / "local" / "vagas.db"
    state = tmp_path / "state" / "origin.json"

    release_snapshot.download_snapshot(client, local, state)

    assert local.read_bytes() == client.assets["vagas.db"]
    assert json.loads(state.read_text())["parent_sha256"] == sha256(local)
    assert not list(local.parent.glob(".vagas.db.*"))


def test_download_inconsistente_preserva_base_e_estado_anteriores(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    local = create_database(tmp_path / "local.db")
    state = tmp_path / "state.json"
    state.write_text("estado anterior", encoding="utf-8")
    original = local.read_bytes()
    client.assets["vagas.csv"] += b"alterado"

    with pytest.raises(ValueError, match="hash divergente"):
        release_snapshot.download_snapshot(client, local, state)

    assert local.read_bytes() == original
    assert state.read_text(encoding="utf-8") == "estado anterior"


def test_download_legado_exige_opt_in_e_registra_hash(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    del client.assets[MANIFEST_NAME]
    del client.assets["vagas.csv"]
    local = tmp_path / "local.db"
    state = tmp_path / "state.json"

    with pytest.raises(ValueError, match="allow-legacy"):
        release_snapshot.download_snapshot(client, local, state)
    release_snapshot.download_snapshot(client, local, state, allow_legacy=True)

    assert json.loads(state.read_text())["parent_sha256"] == sha256(local)


def test_download_legado_remove_somente_associacoes_orfas(tmp_path, remote_snapshot):
    with closing(sqlite3.connect(remote_snapshot / "vagas.db")) as db:
        tecnologia_id = db.execute(
            "INSERT INTO tecnologias (nome, grupo) VALUES ('Python', 'linguagens')"
        ).lastrowid
        db.execute(
            "INSERT INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (?, ?)",
            (999, tecnologia_id),
        )
        db.commit()
    client = FakeGitHubRelease(remote_snapshot)
    del client.assets[MANIFEST_NAME]
    del client.assets["vagas.csv"]
    local = tmp_path / "local.db"
    state = tmp_path / "state.json"

    release_snapshot.download_snapshot(client, local, state, allow_legacy=True)

    with closing(sqlite3.connect(local)) as db:
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        vagas = db.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
        tecnologias = db.execute("SELECT COUNT(*) FROM tecnologias").fetchone()[0]
        associacoes = db.execute("SELECT COUNT(*) FROM vaga_tecnologia").fetchone()[0]
    assert violations == []
    assert vagas == 1
    assert tecnologias == 1
    assert associacoes == 0
    assert json.loads(state.read_text())["parent_sha256"] == sha256(local)


def test_release_com_manifesto_nao_aceita_artefato_faltante_com_opt_in(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    del client.assets["vagas.csv"]

    with pytest.raises(ValueError, match="incompleta"):
        client.download(tmp_path / "download", allow_legacy=True)


def test_download_nao_substitui_banco_com_sidecar(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    local = create_database(tmp_path / "local.db")
    state = tmp_path / "state.json"
    Path(str(local) + "-wal").touch()
    original = local.read_bytes()

    with pytest.raises(ValueError, match="Feche as conexoes"):
        release_snapshot.download_snapshot(client, local, state)

    assert local.read_bytes() == original
    assert not state.exists()


def test_copia_atomica_preserva_destino_se_substituicao_falhar(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"novo")
    target.write_bytes(b"antigo")
    def fail_replace(*args):
        raise PermissionError("Arquivo em uso")
    monkeypatch.setattr(release_snapshot.os, "replace", fail_replace)

    with pytest.raises(PermissionError):
        release_snapshot._atomic_copy(source, target)

    assert target.read_bytes() == b"antigo"
    assert not list(tmp_path.glob(".target.*"))


def test_publicacao_confirma_backup_preparado_nao_bytes_da_origem(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    local = tmp_path / "local.db"
    state = tmp_path / "state.json"
    release_snapshot.download_snapshot(client, local, state)
    with closing(sqlite3.connect(local)) as db:
        db.execute("UPDATE vagas SET title = 'Python e SQL'")
        db.commit()
        db.execute("PRAGMA user_version = 42")
    local_bytes = local.read_bytes()
    old_parent = json.loads(state.read_text())["parent_sha256"]

    confirmed = release_snapshot.publish_snapshot(client, local, state)

    assert confirmed == client.uploaded_manifest["snapshot_id"]
    assert client.uploaded_manifest["parent_sha256"] == old_parent
    assert confirmed != sha256(local)
    assert local.read_bytes() == local_bytes
    assert json.loads(state.read_text())["parent_sha256"] == confirmed


def test_publicacao_recusa_base_antiga_antes_de_upload(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    local = create_database(tmp_path / "local.db")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"parent_sha256": "f" * 64}), encoding="utf-8")
    before = local.read_bytes(), state.read_bytes()

    with pytest.raises(ValueError, match="release mudou"):
        release_snapshot.publish_snapshot(client, local, state)

    assert client.upload_attempted is False
    assert (local.read_bytes(), state.read_bytes()) == before


@pytest.mark.parametrize("failure", ["fail_upload", "fail_confirmation", "change_csv_on_confirmation"])
def test_falha_na_publicacao_nao_avanca_estado_nem_altera_base_local(tmp_path, remote_snapshot, failure):
    client = FakeGitHubRelease(remote_snapshot)
    local = tmp_path / "local.db"
    state = tmp_path / "state.json"
    release_snapshot.download_snapshot(client, local, state)
    with closing(sqlite3.connect(local)) as db:
        db.execute("UPDATE vagas SET title = 'Vaga atualizada'")
        db.commit()
    before = local.read_bytes(), state.read_bytes()
    setattr(client, failure, True)

    with pytest.raises((OSError, ValueError)):
        release_snapshot.publish_snapshot(client, local, state)

    assert client.upload_attempted is True
    assert (local.read_bytes(), state.read_bytes()) == before
    recovery = local.parent / "snapshots" / client.uploaded_manifest["snapshot_id"]
    assert verify_manifest(recovery) == client.uploaded_manifest


def test_transicao_legada_publica_manifesto_e_exige_confirmacao_nova(tmp_path, remote_snapshot):
    client = FakeGitHubRelease(remote_snapshot)
    del client.assets[MANIFEST_NAME]
    local = tmp_path / "local.db"
    state = tmp_path / "state.json"
    release_snapshot.download_snapshot(client, local, state, allow_legacy=True)

    confirmed = release_snapshot.publish_snapshot(client, local, state, allow_legacy=True)

    assert MANIFEST_NAME in client.assets
    assert json.loads(client.assets[MANIFEST_NAME])["snapshot_id"] == confirmed


def test_prepare_recusa_destino_igual_ao_banco_origem(tmp_path):
    local = create_database(tmp_path / "vagas.db")
    before = local.read_bytes()

    with pytest.raises(ValueError, match="outro diretorio"):
        release_snapshot.prepare_snapshot(local, tmp_path, "0" * 64)

    assert local.read_bytes() == before


def test_prepare_inclui_commits_do_wal_e_exporta_o_mesmo_snapshot(tmp_path):
    local = create_database(tmp_path / "local.db")
    prepared = tmp_path / "prepared"
    with closing(sqlite3.connect(local)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE vagas SET title = 'Commit salvo no WAL'")
        writer.commit()

        manifest = release_snapshot.prepare_snapshot(local, prepared, "0" * 64)

        with closing(sqlite3.connect(prepared / "vagas.db")) as snapshot:
            title = snapshot.execute("SELECT title FROM vagas").fetchone()[0]
        assert title == "Commit salvo no WAL"
        assert "Commit salvo no WAL" in (prepared / "vagas.csv").read_text(encoding="utf-8-sig")
        assert manifest == verify_manifest(prepared)


def test_manifesto_recusa_relacao_orfa(tmp_path):
    local = create_database(tmp_path / "local.db")
    with closing(sqlite3.connect(local)) as writer:
        writer.execute("INSERT INTO vaga_tecnologia (vaga_id, tecnologia_id) VALUES (1, 999)")
        writer.commit()

    with pytest.raises(ValueError, match="relacoes orfas"):
        release_snapshot.prepare_snapshot(local, tmp_path / "prepared", "0" * 64)


def test_publicador_gh_tem_timeout(monkeypatch, tmp_path):
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return type("Result", (), {"stdout": "ok"})()
    monkeypatch.setattr(release_snapshot.subprocess, "run", fake_run)

    result = release_snapshot.GitHubRelease()._run("view", "latest")

    assert result == "ok"
    assert calls[0][0] == ["gh", "release", "view", "latest"]
    assert calls[0][1]["timeout"] == 180
    assert calls[0][1]["check"] is True
