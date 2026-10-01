#!/usr/bin/env bash
# Cron diario Vivienda: ingesta + regenera solo si hay cambios. RAM ~0 (estático).
set -euo pipefail
cd /home/deploy/vivienda-osint
echo "[$(date -u +%F' '%T)] vivienda cron"
./venv/bin/python -m ingest.boe >> logs/ingesta.log 2>&1
./venv/bin/python gen/gen_vivienda.py >> logs/gen.log 2>&1
