#!/usr/bin/env bash
# Cron diario Vivienda: ingesta (BOE/INE/CGPJ) + regenera con PUERTA de staging.
# Importante: la BD nunca vive bajo web/ (el build la borra en el swap) y la
# publicación solo ocurre si los tests pasan contra web_tmp. RAM ~0 (estático).
set -euo pipefail
cd /home/deploy/vivienda-osint
echo "[$(date -u +%F" "%T)] vivienda cron"
./venv/bin/python -m ingest.boe  >> logs/ingesta.log 2>&1 || echo "boe fallo" >> logs/ingesta.log
./venv/bin/python -m ingest.ine  >> logs/ingesta.log 2>&1 || echo "ine fallo" >> logs/ingesta.log
./venv/bin/python -m ingest.cgpj >> logs/ingesta.log 2>&1 || echo "cgpj fallo" >> logs/ingesta.log
# generar + validar + publicar (web_tmp -> web solo si los tests pasan)
./scripts/regen_publicar.sh >> logs/ingesta.log 2>&1 || echo "[$(date -u +%F" "%T)] regen_publicar rc=$?" >> logs/ingesta.log
# contrato de datos también sobre la web ya publicada (doble comprobación del día)
./venv/bin/python tests/test_datos.py >> logs/test.log 2>&1 || echo "[$(date -u +%F" "%T)] test_datos (web/ publicada) FALLO" >> logs/ingesta.log