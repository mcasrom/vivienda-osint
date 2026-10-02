#!/usr/bin/env bash
# Cron diario Vivienda: ingesta (BOE/INE/CGPJ) + regenera. RAM ~0 (estático).
set -euo pipefail
cd /home/deploy/vivienda-osint
echo "[$(date -u +%F" "%T)] vivienda cron"
./venv/bin/python -m ingest.boe  >> logs/ingesta.log 2>&1 || echo "boe fallo" >> logs/ingesta.log
./venv/bin/python -m ingest.ine  >> logs/ingesta.log 2>&1 || echo "ine fallo" >> logs/ingesta.log
./venv/bin/python -m ingest.cgpj >> logs/ingesta.log 2>&1 || echo "cgpj fallo" >> logs/ingesta.log
./venv/bin/python gen/gen_vivienda.py >> logs/gen.log 2>&1
/usr/bin/python3 gen/gen_og.py >> logs/gen.log 2>&1
# contrato de datos: si la regeneración salió mal, que se oiga (no solo en el log)
./venv/bin/python tests/test_datos.py >> logs/test.log 2>&1 || echo "[$(date -u +%F" "%T)] test_datos FALLO" >> logs/gen.log
