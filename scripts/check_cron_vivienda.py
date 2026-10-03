#!/usr/bin/env python3
"""Avisa por Telegram si el cron diario de vivienda NO ha corrido bien en >36 h.

Evita el fallo silencioso (regla 24): el cron publica cada día a las 06:15; si no
corre (o ninguna fuente se actualiza), nadie se entera. Este watchdog lo detecta
por la antigüedad de `data/frescura.json` y por si todas las fuentes están `ok=False`.

Cron sugerido:  0 8 * * *  .../scripts/check_cron_vivienda.py >> logs/check_cron.log 2>&1
"""
import json
import os
import subprocess
import time

ROOT = "/home/deploy/vivienda-osint"
FR = os.path.join(ROOT, "data", "frescura.json")
LIMITE_H = 36


def _avisar(msg):
    print("[check_cron] AVISO: " + msg)
    subprocess.run([os.path.join(ROOT, "venv/bin/python"),
                    os.path.join(ROOT, "scripts", "aviso.py"), msg], cwd=ROOT)


def main():
    if not os.path.exists(FR):
        _avisar("vivienda: no existe data/frescura.json (¿cron roto?)")
        return 0
    edad_h = (time.time() - os.path.getmtime(FR)) / 3600.0
    try:
        fuentes = json.load(open(FR, encoding="utf-8")).get("fuentes", {})
    except (OSError, ValueError):
        fuentes = {}
    mal = [k for k, v in fuentes.items() if not v.get("ok")]
    todas_mal = bool(fuentes) and len(mal) == len(fuentes)
    if edad_h > LIMITE_H or todas_mal:
        _avisar(f"vivienda: el cron no se ha actualizado bien ({edad_h:.0f} h desde la última "
                f"ingesta; fuentes sin ok: {', '.join(mal) or 'ninguna'}). Revisa logs/ingesta.log.")
    else:
        print(f"[check_cron] ok ({edad_h:.1f} h; sin ok: {', '.join(mal) or 'ninguna'})")
    return 0


if __name__ == "__main__":
    main()
