#!/usr/bin/env python3
"""Historial de cambios de las series publicadas (auditoría, 3-oct-2026).

Compara el md5 de cada `web/data/<serie>.csv` con el guardado en
`data/dataset_hashes.json`; añade una entrada a `data/historial.json` **solo
cuando cambia** (fecha, serie, md5) y publica `web/data/changelog.json`.
Así un cambio de dato queda registrado y auditable.

Se llama desde `scripts/regen_publicar.sh` tras publicar (no desde el generador,
para que las corridas de staging/QA no ensucien el historial).
"""
import datetime
import glob
import hashlib
import json
import os

ROOT = "/home/deploy/vivienda-osint"
WEB = os.path.join(ROOT, "web", "data")
STATE = os.path.join(ROOT, "data", "dataset_hashes.json")
HIST = os.path.join(ROOT, "data", "historial.json")


def main():
    try:
        prev = json.load(open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    try:
        hist = json.load(open(HIST, encoding="utf-8"))
    except (OSError, ValueError):
        hist = []
    hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    nuevo, cambios = {}, 0
    for p in sorted(glob.glob(os.path.join(WEB, "*.csv"))):
        did = os.path.basename(p)[:-4]
        h = hashlib.md5(open(p, "rb").read()).hexdigest()
        nuevo[did] = h
        if prev.get(did) != h:
            hist.append({"fecha": hoy, "serie": did, "md5": h[:10]})
            cambios += 1
    json.dump(nuevo, open(STATE, "w", encoding="utf-8"))
    json.dump(hist[-2000:], open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(WEB, "changelog.json"), "w", encoding="utf-8") as f:
        json.dump({"generado": hoy, "cambios": hist[-60:]}, f, ensure_ascii=False, indent=1)
    print(f"[changelog] {len(nuevo)} series · {cambios} cambios ({hoy})")


if __name__ == "__main__":
    main()
