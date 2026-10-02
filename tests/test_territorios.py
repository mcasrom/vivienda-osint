#!/usr/bin/env python3
"""Cobertura canónica de territorios (sin red, sin artefactos generados).

La tabla de `ingest/territorios.py` es la única fuente de nombres de CCAA de TODO
el observatorio. Aquí se comprueba que la propia tabla es coherente:
  - 19 CCAA, códigos 01-19 únicos, un solo orden (no hay dos nombres iguales);
  - el alias del CGPJ resuelve siempre a nombres canónicos y es 1:1 (17 + TOTAL);
  - canonico() redondea: etiqueta INE ya canónica → misma; CGPJ mayús → canónica;
    basura → None (se avisa en ingesta, nunca se descarta en silencio).
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest import territorios

FALLOS: list[str] = []


def check(ok, msg):
    if not ok:
        FALLOS.append(msg)


codigos = [c for c, _n in territorios.CCAA]
check(len(territorios.CCAA) == 19, f"19 CCAA esperadas, hay {len(territorios.CCAA)}")
check(len(set(codigos)) == 19, f"códigos INE duplicados: {codigos}")
check(codigos == [f"{i:02d}" for i in range(1, 20)], f"códigos no son 01..19: {codigos}")
check(len(territorios.NOMBRES) == 19, "NOMBRES no tiene 19 entradas")
check(len(set(territorios.NOMBRES)) == 19, "hay nombres canónicos duplicados")
check(set(territorios.NOMBRES) == set(territorios.NOMBRE.values()), "NOMBRE/NOMBRES desincronizados")

# alias del CGPJ
check(len(territorios.ALIAS_CGPJ) == 17,
      f"CGPJ publica 17 CCAA, hay {len(territorios.ALIAS_CGPJ)} aliases")
desconocidos = [v for v in territorios.ALIAS_CGPJ.values() if v not in territorios.NOMBRES]
check(not desconocidos, f"aliases que no son canónicos: {desconocidos}")
check(len(set(territorios.ALIAS_CGPJ.values())) == 17, "dos etiquetas CGPJ al mismo canónico")

# huecos declarados (hoy: CGPJ no publica Ceuta/Melilla en lanzamientos)
for did, huecos in territorios.HUECOS.items():
    for h, motivo in huecos:
        check(h in territorios.NOMBRES, f"{did}: hueco {h!r} no es un canónico")
        check(bool(motivo), f"{did}: hueco {h!r} sin motivo")
check(territorios.HUECOS.get("lanzamientos-ccaa") is not None,
      "lanzamientos-ccaa no declara sus huecos (Ceuta/Melilla)")

# canonico() — los tres casos que existen hoy
check(territorios.canonico("Andalucía") == "Andalucía", "canónico ya canónico se rompe")
check(territorios.canonico("andaluCÍA") == "Andalucía", "no normaliza CGPJ en mayúsculas")
check(territorios.canonico("MADRID, COMUNIDAD") == "Madrid, Comunidad de", "alias Madrid")
check(territorios.canonico("CEUTA") == "Ceuta",
      "Ceuta es un canónico del INE: su ausencia es un HUECO de datos, no un nombre")
check(territorios.canonico("") is None, "etiqueta vacía no debe dar canónico")
check(territorios.canonico("CUALQUIER COSA") is None, "basura → None")

# orden: comparar series entre sí exige el mismo orden canónico
pares = [(n, i) for i, n in enumerate(territorios.NOMBRES)]
check([k for k, _ in territorios.ordenar(pares)] == list(territorios.NOMBRES),
      "ordenar() rompe el orden canónico")

if FALLOS:
    print("FALLOS (%d):" % len(FALLOS), file=sys.stderr)
    for f in FALLOS:
        print("  -", f, file=sys.stderr)
    sys.exit(1)
print(f"OK · territorios: 19 CCAA · {len(territorios.ALIAS_CGPJ)} aliases · huecos lanzamientos "
      f"{[h for h,_m in territorios.HUECOS.get('lanzamientos-ccaa', ())]}")