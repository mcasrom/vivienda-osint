"""Test del watchdog del RDL: clasificación de la resolución del Congreso.

No toca la red: ejercita la lógica sobre los dos precedentes reales ya publicados
en el BOE (convalidación y derogación) y el control negativo.
"""
from __future__ import annotations
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location("w", os.path.join(ROOT, "scripts", "watchdog_rdl.py"))
w = importlib.util.module_from_spec(spec)
sys.modules["w"] = w
spec.loader.exec_module(w)

FALLOS: list[str] = []


def check(ok, msg):
    if not ok:
        FALLOS.append(msg)


# --- 1. los dos precedentes reales se clasifican igual que en el BOE ------------
CONVALIDA = ("Resolución de 30 de marzo de 2023, del Congreso de los Diputados, por la que "
             "se ordena la publicación del Acuerdo de convalidación del Real Decreto-ley "
             "2/2023, de 16 de marzo")
DEROGA = ("Resolución de 26 de febrero de 2026, del Congreso de los Diputados, por la que "
          "se ordena la publicación del Acuerdo de derogación del Real Decreto-ley "
          "2/2026, de 3 de febrero")

r = w.match_resolucion(CONVALIDA, "2/2023")
check(r is not None and r["estado"] == "convalidada", f"convalidación no detectada: {r}")
r = w.match_resolucion(DEROGA, "2/2026")
check(r is not None and r["estado"] == "derogada", f"derogación no detectada: {r}")

# --- 2. falsos positivos que deben descartarse (composición, no regex suelta) ---
check(w.match_resolucion("Acuerdo de convalidación del presupuesto", "2/2023") is None,
      "acepta un acuerdo sin RDL")
check(w.match_resolucion("Resolución de la Mesa del Congreso", "2/2023") is None,
      "acepta un órgano que no es el Pleno")
check(w.match_resolucion(CONVALIDA, "3/2023") is None, "no distingue el nº de RDL")
check(w.match_resolucion(CONVALIDA, "2/2024") is None, "no distingue el año del RDL")

# --- 3. helpers (causa raíz de los HTTPError silenciosos) -----------------------
sys.path.insert(0, ROOT)
from ingest.boe import _es_domingo  # noqa: E402
from datetime import date  # noqa: E402
check(not _es_domingo(date(2026, 10, 2)), "viernes como domingo")
check(_es_domingo(date(2026, 10, 4)), "domingo no detectado")

if FALLOS:
    print("\n".join("  - " + f for f in FALLOS))
    sys.exit(1)
print(f"OK · watchdog-rdl: 2 precedentes + 4 controles negativos · {len(FALLOS)} fallos")