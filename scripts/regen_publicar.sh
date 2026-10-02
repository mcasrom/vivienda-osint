#!/usr/bin/env bash
# Publica con PUERTA de staging: genera en web_tmp/, valida el contrato de datos
# contra web_tmp/ y solo intercambia a web/ si los tests pasan. Si fallan, no se
# toca web/ (la web queda con la última versión buena) y se avisa por Telegram.
# Respuesta al análisis externo: se publica DESPUÉS de comprobar, no antes.
set -euo pipefail
cd /home/deploy/vivienda-osint
echo "[$(date -u +%F" "%T)] regen_publicar: inicio"
rm -rf web_tmp
./venv/bin/python gen/gen_vivienda.py --out web_tmp >> logs/gen.log 2>&1
/usr/bin/python3 gen/gen_og.py --out web_tmp >> logs/gen.log 2>&1
if ./venv/bin/python tests/test_datos.py --web-dir web_tmp >> logs/test.log 2>&1; then
    # puerta superada: intercambio. Salvo fallo extremo (mv), quedamos con la buena.
    if [ -d web ]; then mv web web.vieja; fi
    mv web_tmp web
    rm -rf web.vieja
    echo "[$(date -u +%F" "%T)] regen_publicar: publicada (tests OK sobre web_tmp)"
else
    echo "[$(date -u +%F" "%T)] regen_publicar: tests FALLARON sobre web_tmp — no se publica" >> logs/test.log
    rm -rf web_tmp
    ./venv/bin/python scripts/aviso.py "vivienda: la regeneración falló los tests (web sin cambios). Revisa logs/test.log y logs/gen.log." >> logs/test.log 2>&1 || true
    exit 1
fi