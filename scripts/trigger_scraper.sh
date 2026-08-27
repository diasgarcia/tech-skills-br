#!/usr/bin/env bash
# Dispara a coleta diaria no GitHub Actions via API de dispatch.
#
# Usado pelos cron jobs do Render: o agendador nativo do GitHub tem
# atrasado/derrubado os crons, entao o Render vira o despertador e a
# coleta continua rodando inteira no Actions.
#
# Requer a variavel GH_TOKEN (PAT com permissao "Actions: write").
set -euo pipefail

if [ -z "${GH_TOKEN:-}" ]; then
  echo "GH_TOKEN nao definido. Configure o token no servico do Render." >&2
  exit 1
fi

curl -sS -f -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/diasgarcia/tech-skills-br/actions/workflows/daily_scraper.yml/dispatches \
  -d '{"ref":"main"}'

echo "Coleta disparada com sucesso."
