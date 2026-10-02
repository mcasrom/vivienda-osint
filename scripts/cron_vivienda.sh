#!/usr/bin/env bash
# Cron diario Vivienda: ingesta (BOE/INE/CGPJ) + regenera con PUERTA de staging.
# Importante: la BD nunca vive bajo web/ (el build la borra en el swap) y la
# publicación solo ocurre si los tests pasan contra web_tmp. RAM ~0 (estático).
set -euo pipefail
cd /home/deploy/vivienda-osint
echo "[$(date -u +%F" "%T)] vivienda cron"
# Ingesta por fuente: se captura el rc REAL de cada una y se registra su estado
# en data/frescura.json (F2). Antes `cmd || echo "X fallo"` dejaba el fallo solo
# en el log: la web seguía sirviendo datos viejos como si fueran de hoy.
for fuente in boe ine ipc cgpj; do
  if ./venv/bin/python -m "ingest.$fuente" >> logs/ingesta.log 2>&1; then
    ./venv/bin/python -m ingest.frescura --fuente "$fuente" --ok >> logs/ingesta.log 2>&1 \
      || echo "[$(date -u +%F" "%T)] frescura $fuente --ok fallo" >> logs/ingesta.log
  else
    rc=$?
    echo "[$(date -u +%F" "%T)] $fuente fallo (rc=$rc)" >> logs/ingesta.log
    ./venv/bin/python -m ingest.frescura --fuente "$fuente" --fallo --detalle "rc=$rc" \
      >> logs/ingesta.log 2>&1 || true
  fi
done
# generar + validar + publicar (web_tmp -> web solo si los tests pasan)
./scripts/regen_publicar.sh >> logs/ingesta.log 2>&1 || echo "[$(date -u +%F" "%T)] regen_publicar rc=$?" >> logs/ingesta.log
# contrato de datos también sobre la web ya publicada (doble comprobación del día)
./venv/bin/python tests/test_datos.py >> logs/test.log 2>&1 || echo "[$(date -u +%F" "%T)] test_datos (web/ publicada) FALLO" >> logs/ingesta.log