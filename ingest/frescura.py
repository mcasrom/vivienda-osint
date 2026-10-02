#!/usr/bin/env python3
"""Estado de frescura por fuente (F2, 2-oct-2026).

El cron marca aquí, tras CADA ingesta, si la fuente se actualizó bien o falló.
El generador lo lee para (a) pintar el bloque «Estado de datos» de la portada y
(b) añadir la edad de nuestro dato a `latest.json`. Motivo: hasta ahora el cron
hacía `ingest X || echo "X fallo"` y **un fallo de fuente no se veía en la web**
(seguía sirviendo datos viejos como si fueran de hoy).

Diseño:
  - `marcar(fuente, ok, detalle)`: actualiza `data/frescura.json` (escritura
    atómica con os.replace). Si `ok`, fija `actualizado`=hoy; si falla, conserva
    la última fecha válida en `ultima_ok`.
  - `estado()`: devuelve por fuente {nombre, ok, actualizado, ultima_ok,
    edad_dias, detalle}, recalculando `edad_dias` (hoy - actualizado).
  - Función pura salvo la E/S del JSON; CLI para el cron:
        python -m ingest.frescura --fuente ine --ok
        python -m ingest.frescura --fuente cgpj --fallo --detalle "rc=1"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIDE = os.path.join(ROOT, "data", "frescura.json")

# Orden de presentación y nombre legible de cada fuente.
FUENTES = (("ine", "INE"), ("ipc", "INE · IPC"), ("cgpj", "CGPJ"), ("boe", "BOE"))
NOMBRE = dict(FUENTES)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def leer() -> dict:
    try:
        with open(SIDE, encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            d.setdefault("fuentes", {})
            return d
    except (OSError, ValueError) as e:
        print(f"[frescura] no se pudo leer {SIDE}: {e}", file=sys.stderr)
    return {"generado": None, "fuentes": {}}


def guardar(d: dict) -> None:
    os.makedirs(os.path.dirname(SIDE), exist_ok=True)
    tmp = SIDE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, SIDE)          # atómico: nunca deja el JSON a medias


def marcar(fuente: str, ok: bool, detalle: str = "", ref: str | None = None) -> dict:
    if fuente not in NOMBRE:
        raise ValueError(f"fuente desconocida: {fuente!r} (usa {sorted(NOMBRE)})")
    d = leer()
    f = d.setdefault("fuentes", {})
    prev = f.get(fuente, {}) or {}
    hoy = date.today().isoformat()
    entrada = dict(prev)
    entrada["ok"] = bool(ok)
    entrada["detalle"] = detalle or ""
    entrada["ts"] = _now()
    if ok:
        entrada["actualizado"] = hoy
        entrada["ultima_ok"] = hoy
    else:
        # Conserva la última fecha válida; actualizado no se mueve.
        entrada["actualizado"] = prev.get("actualizado")
        entrada["ultima_ok"] = prev.get("ultima_ok")
    if ref:
        entrada["ref"] = ref
    f[fuente] = entrada
    d["generado"] = _now()
    guardar(d)
    return entrada


def estado() -> dict:
    """Por fuente: nombre, ok, actualizado, ultima_ok, edad_dias, detalle."""
    d = leer()
    fuentes = d.get("fuentes") or {}
    hoy = date.today()
    out = {}
    for k, nombre in FUENTES:
        e = dict(fuentes.get(k) or {})
        act = e.get("actualizado")
        try:
            e["edad_dias"] = (hoy - date.fromisoformat(act)).days if act else None
        except (TypeError, ValueError):
            e["edad_dias"] = None
        e.setdefault("ok", None)
        e.setdefault("detalle", "")
        e["nombre"] = nombre
        out[k] = e
    return out


def _main() -> int:
    ap = argparse.ArgumentParser(description="Estado de frescura por fuente.")
    ap.add_argument("--fuente", required=True, choices=[k for k, _ in FUENTES])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ok", action="store_true", help="la ingesta de hoy fue correcta")
    g.add_argument("--fallo", action="store_true", help="la ingesta de hoy falló")
    ap.add_argument("--detalle", default="", help="texto libre (p.ej. rc=1)")
    ap.add_argument("--ref", default=None, help="periodo de referencia del dato")
    a = ap.parse_args()
    e = marcar(a.fuente, ok=not a.fallo, detalle=a.detalle, ref=a.ref)
    print(f"[frescura] {a.fuente}: ok={e['ok']} actualizado={e.get('actualizado')} "
          f"edad={estado()[a.fuente]['edad_dias']}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
