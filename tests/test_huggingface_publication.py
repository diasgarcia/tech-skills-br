import shutil
import subprocess

import pytest

from api.snapshots import sha256
from scripts import publish_huggingface as hf


REPO_ID = "test/tech-skills-br"
SNAPSHOT = "a" * 64


def test_publicacao_preserva_um_commit_na_main_e_o_parquet_da_tag(tmp_path, monkeypatch):
    if shutil.which("git") is None or subprocess.run(["git", "lfs", "version"], capture_output=True).returncode:
        pytest.skip("Git LFS indisponível para validar a publicação do Parquet.")

    remote = tmp_path / "remote.git"
    config = tmp_path / "gitconfig"
    url = f"https://huggingface.co/datasets/{REPO_ID}"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True)
    subprocess.run(["git", "config", "--file", str(config), f"url.{remote.as_uri()}.insteadOf", url], check=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("HF_TOKEN", "token-de-teste")
    monkeypatch.setattr(hf, "snapshot_atual", lambda _: True)

    def git(*args):
        return subprocess.check_output(["git", "--git-dir", str(remote), *args], text=True).strip()

    def confirmar_arquivo(_url, revision, expected):
        pointer = git("show", f"{revision}:vagas.parquet")
        assert f"oid sha256:{expected}" in pointer.splitlines()
        assert sha256(remote / "lfs" / "objects" / expected[:2] / expected[2:4] / expected) == expected

    monkeypatch.setattr(hf, "confirmar_arquivo", confirmar_arquivo)
    parquet = tmp_path / "vagas.parquet"
    parquet.write_bytes(b"snapshot atual")
    hf.publicar(REPO_ID, parquet, snapshot_id=SNAPSHOT)
    initial_main = git("rev-parse", "main")

    parquet.write_bytes(b"snapshot historico")
    hf.publicar(REPO_ID, parquet, tag="v2026.10.27")
    tag_commit = git("rev-parse", "v2026.10.27")
    tag_hash = sha256(parquet)

    parquet.write_bytes(b"snapshot seguinte")
    hf.publicar(REPO_ID, parquet, snapshot_id="b" * 64)
    updated_main = git("rev-parse", "main")
    hf.publicar(REPO_ID, parquet, snapshot_id="b" * 64)

    assert updated_main != initial_main
    assert git("rev-list", "--count", "main") == "1"
    assert git("rev-parse", "main") == updated_main
    assert git("rev-parse", "v2026.10.27") == tag_commit
    confirmar_arquivo(url, tag_commit, tag_hash)
    with pytest.raises(AssertionError):
        hf.publicar(REPO_ID, parquet, tag="v2026.10.27")

    checks = iter((True, False))
    monkeypatch.setattr(hf, "snapshot_atual", lambda _: next(checks))
    parquet.write_bytes(b"snapshot obsoleto")
    hf.publicar(REPO_ID, parquet, snapshot_id=SNAPSHOT)
    assert git("rev-parse", "main") == updated_main
