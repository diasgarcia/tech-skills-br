"""Publica o Parquet validado no Hugging Face, na main ou em uma tag fixa."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.snapshots import MANIFEST_NAME, sha256, validate_sha256

DATASET_CARD = """---
language:
- pt
license: mit
pretty_name: Tech Skills Brasil
tags:
- brazil
- jobs
- labor-market
configs:
- config_name: default
  data_files:
  - split: vagas
    path: vagas.parquet
---

# Tech Skills Brasil

Esta base reúne anúncios de vagas de entrada em tecnologia no Brasil. Inclui vagas de estágio, aprendiz, trainee e nível júnior. Cada linha representa um anúncio. A coluna `skills` lista as habilidades identificadas no texto do anúncio.

A coleta consulta portais públicos de emprego. O projeto consolida os anúncios, classifica a área e extrai habilidades com um vocabulário de termos técnicos. A coleta roda três vezes por dia. A branch `main` mostra o snapshot mais recente. Tags com data preservam versões específicas.

Os dados descrevem os anúncios coletados. A cobertura varia por fonte, e alguns anúncios têm descrição incompleta ou modalidade ausente. O projeto documenta o escopo e os critérios de coleta na wiki.

- [Código e releases](https://github.com/diasgarcia/tech-skills-br)
- [Metodologia e limitações](https://github.com/diasgarcia/tech-skills-br/wiki)
- [Dataset no Kaggle](https://www.kaggle.com/datasets/rafaeldiasgarcia/tech-skills-br)
- [Painel](https://diasgarcia.github.io/tech-skills-br/)
"""
PARQUET_NAME = "vagas.parquet"
logger = logging.getLogger(__name__)


def snapshot_atual(snapshot_id: str) -> bool:
    validate_sha256(snapshot_id)
    with TemporaryDirectory(prefix="tech-skills-hf-manifest-") as directory:
        subprocess.run(
            [
                "gh", "release", "download", "latest", "--repo",
                os.getenv("GITHUB_REPOSITORY", "diasgarcia/tech-skills-br"),
                "--pattern", MANIFEST_NAME, "--dir", directory,
            ],
            cwd=PROJECT_ROOT, check=True, timeout=60,
        )
        atual = json.loads((Path(directory) / MANIFEST_NAME).read_text(encoding="utf-8"))["snapshot_id"]
    validate_sha256(atual)
    return snapshot_id == atual


def confirmar_arquivo(url: str, revision: str, expected: str) -> None:
    with requests.get(
        f"{url}/resolve/{revision}/{PARQUET_NAME}",
        headers={"Accept-Encoding": "identity"},
        stream=True,
        timeout=(10, 60),
    ) as response:
        response.raise_for_status()
        if hashlib.file_digest(response.raw, "sha256").hexdigest() != expected:
            raise RuntimeError("O Hugging Face retornou um Parquet diferente do arquivo local.")


def publicar(
    repo_id: str,
    parquet: Path,
    *,
    snapshot_id: str | None = None,
    tag: str | None = None,
    card: Path | None = None,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", repo_id):
        raise ValueError("Use o identificador HF_REPO_ID no formato usuario/dataset.")
    if tag and not re.fullmatch(r"v[0-9]{4}\.[0-9]{2}\.[0-9]{2}", tag):
        raise ValueError("Use uma tag de release no formato vAAAA.MM.DD.")
    if not os.getenv("HF_TOKEN"):
        raise RuntimeError("Configure o secret HF_TOKEN antes de publicar.")
    if tag is None and not snapshot_atual(snapshot_id or ""):
        logger.warning("Snapshot antigo ignorado no Hugging Face.")
        return

    expected = sha256(parquet)
    url = f"https://huggingface.co/datasets/{repo_id}"
    owner = repo_id.split("/", 1)[0]
    helper = (
        '!f() { if [ "$1" = get ]; then '
        f'printf "username={owner}\\npassword=%s\\n" "$HF_TOKEN"; '
        'fi; }; f'
    )
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
        "GIT_CONFIG_KEY_1": "credential.https://huggingface.co.helper",
        "GIT_CONFIG_VALUE_1": helper,
    }

    with TemporaryDirectory(prefix="tech-skills-hf-") as directory:
        worktree = Path(directory)

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=worktree, env=env, check=True,
                stdout=subprocess.PIPE, text=True, encoding="utf-8", timeout=180,
            ).stdout.strip()

        git("init", "--initial-branch=main")
        git("remote", "add", "origin", url)
        ref = f"refs/tags/{tag}" if tag else "refs/heads/main"
        remote = git("ls-remote", "--refs", "origin", ref)
        previous = remote.split()[0] if remote else ""
        if tag and previous:
            confirmar_arquivo(url, tag, expected)
            logger.info("Tag %s ja contem o mesmo Parquet, SHA-256 %s.", tag, expected)
            return
        if previous:
            git("fetch", "--no-tags", "origin", ref)
            git("checkout", "--detach", "FETCH_HEAD")
            if git("rev-parse", "HEAD") != previous:
                raise RuntimeError("A main do Hugging Face mudou durante a preparacao.")
            if git("rev-list", "--count", "HEAD") != "1":
                raise RuntimeError("A main do Hugging Face precisa partir de um unico commit.")

        git("lfs", "install", "--local")
        git("lfs", "track", PARQUET_NAME)
        shutil.copyfile(parquet, worktree / PARQUET_NAME)
        if card is None:
            (worktree / "README.md").write_text(DATASET_CARD, encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(card, worktree / "README.md")
        git("add", "--", ".gitattributes", "README.md", PARQUET_NAME)
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

        if not previous or git("diff", "--cached", "--name-only"):
            amend = ("--amend",) if previous else ()
            git("commit", *amend, "-m", f"Snapshot {tag or snapshot_id} · parquet sha256:{expected}")
            if tag:
                git("tag", tag)
                git("push", "origin", f"{ref}:{ref}")
            elif snapshot_atual(snapshot_id or ""):
                git("push", f"--force-with-lease={ref}:{previous}", "origin", f"HEAD:{ref}")
            else:
                logger.warning("Snapshot antigo ignorado no Hugging Face.")
                return

        revision = git("rev-parse", "HEAD")
        confirmar_arquivo(url, revision, expected)
        if git("ls-remote", "--refs", "origin", ref) != f"{revision}\t{ref}":
            raise RuntimeError("A referencia do Hugging Face mudou durante a confirmacao.")
        logger.info("Hugging Face confirmou %s (%s), SHA-256 %s.", tag or "main", revision, expected)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parquet", type=Path)
    parser.add_argument("--repo", default=os.getenv("HF_REPO_ID", "diasgarcia/tech-skills-br"))
    parser.add_argument("--card", type=Path)
    revision = parser.add_mutually_exclusive_group(required=True)
    revision.add_argument("--snapshot-id")
    revision.add_argument("--tag")
    args = parser.parse_args()
    publicar(args.repo, args.parquet, snapshot_id=args.snapshot_id, tag=args.tag, card=args.card)
