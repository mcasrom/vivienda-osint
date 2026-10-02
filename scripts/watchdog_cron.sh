#!/usr/bin/env bash
# Cron del watchdog RDL: comprueba cada 30 min si el Congreso publicó el acuerdo
# (convalidación/derogación) en el BOE.
# AUTO-APLICA (2-oct-2026): con --aplicar transcribe la Resolución OFICIAL del BOE
# al registro (normas.json) y regenera por staging (tests) — no es "decidir": es
# transcribir un hecho oficial con fuente. El aviso por Telegram se manda igual.
set -euo pipefail
cd /home/deploy/vivienda-osint
trap 'echo "[$(date -u +%F" "%T)] watchdog rc=$? (linea $LINENO)" >> logs/watchdog_rdl.log' EXIT
./venv/bin/python scripts/watchdog_rdl.py --aplicar >> logs/watchdog_rdl.log 2>&1