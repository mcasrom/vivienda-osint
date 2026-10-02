#!/usr/bin/env bash
# Cron del watchdog RDL: comprueba cada 30 min si el Congreso publicó el acuerdo
# (convalidación/derogación) y avisa por Telegram UNA vez. Log a watchdog_rdl.log.
# No aplica nada solo: para escribirlo en el registro hace falta --aplicar (decisión
# del dueño; el watchdog avisa, no decide).
set -euo pipefail
cd /home/deploy/vivienda-osint
trap 'echo "[$(date -u +%F" "%T)] watchdog rc=$? (linea $LINENO)" >> logs/watchdog_rdl.log' EXIT
./venv/bin/python scripts/watchdog_rdl.py >> logs/watchdog_rdl.log 2>&1