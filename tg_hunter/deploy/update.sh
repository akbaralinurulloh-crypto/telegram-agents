#!/usr/bin/env bash
# Serverda yangi kodni olib, agentni qayta ishga tushiradi (session, baza va .env saqlanadi).
set -euo pipefail
cd "$(dirname "$0")/.."
BRANCH="${BRANCH:-main}"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps
