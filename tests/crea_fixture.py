#!/usr/bin/env python3
"""Genera data/vivienda.db de FIXTURE determinista para la CI (y para probar en local).

Propósito: que la CI pueda ejecutar el contrato de datos completo (incluidos los
checks que hoy se omiten porque «web/ y la DB no están en git»). Con esta DB
sintética y `gen_vivienda.py --out web_tmp` + `test_datos.py --web-dir web_tmp` la
CI valida de verdad: CSV↔HTML (§8-9), tarjetas↔latest.json (§10) y el comparador
regional (§11).

Los valores son arbitrarios pero COHERENTES con lo que el generador y el test
esperan (tendencias dentro del vocabulario, 19 CCAA en EH/VUT, 17 en lanzamientos
con Ceuta/Melilla como huecos declarados, IPV región = código 14). No es producción.
"""
from __future__ import annotations
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import territorios  # noqa: E402

DB = os.path.join(ROOT, "data", "vivienda.db")


def _con():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS boe(
        id TEXT PRIMARY KEY, fecha TEXT, titulo TEXT, url TEXT, departamento TEXT,
        seccion TEXT, ambito TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS ine_serie(
        serie TEXT, fecha TEXT, etiqueta TEXT, valor REAL, PRIMARY KEY(serie, fecha))""")
    c.execute("""CREATE TABLE IF NOT EXISTS lanzamientos(
        ambito TEXT, periodo TEXT, valor REAL, PRIMARY KEY(ambito, periodo))""")
    c.execute("DELETE FROM boe")
    c.execute("DELETE FROM ine_serie")
    c.execute("DELETE FROM lanzamientos")
    return c


def main() -> int:
    c = _con()

    # --- boe: las dos normas registradas en data/normas.json + una extra ---------
    normas = [
        ("BOE-A-2026-20266", "2026-09-30",
         "Real Decreto-ley 26/2026, de 29 de septiembre, por el que se adoptan medidas "
         "urgentes para la protección de la función social de la vivienda y la ampliación "
         "de la oferta de vivienda asequible.",
         "https://www.boe.es/buscar/act.php?id=BOE-A-2026-20266", "Jefatura del Estado"),
        ("BOE-A-2026-20385", "2026-10-01",
         "Real Decreto-ley 27/2026, de 29 de septiembre, por el que se adoptan medidas "
         "urgentes para reforzar la estabilidad de los contratos de arrendamiento de "
         "vivienda habitual.",
         "https://www.boe.es/buscar/act.php?id=BOE-A-2026-20385", "Jefatura del Estado"),
        ("BOE-A-2026-20471", "2026-10-02",
         "Real Decreto 765/2026, de 30 de septiembre, por el que se regula la concesión "
         "directa de subvenciones en materia de vivienda.",
         "https://www.boe.es/buscar/act.php?id=BOE-A-2026-20471", "Ministerio de Vivienda"),
    ]
    for id_, fecha, titulo, url, dept in normas:
        c.execute("INSERT OR REPLACE INTO boe(id,fecha,titulo,url,departamento,seccion,ambito) "
                  "VALUES(?,?,?,?,?,?,?)", (id_, fecha, titulo, url, dept, "1", "estatal"))

    # --- IPV nacional + región Murcia (código 14) para el comparador -------------
    ipv = [("2025-10-01", "2025 4T", 11.8), ("2026-01-01", "2026 1T", 12.2)]
    for serie, pts in (("ipv_var_anual", ipv),
                       ("ipv_var_anual:14", [("2025-10-01", "2025 4T", 13.9),
                                             ("2026-01-01", "2026 1T", 14.4)])):
        for fecha, etq, v in pts:
            c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES(?,?,?,?)",
                      (serie, fecha, etq, v))
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('ipv_nueva_var','2026-01-01','2026 1T',10.1)")
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('ipv_segunda_var','2026-01-01','2026 1T',13.0)")
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('ipv_indice','2026-01-01','2026 1T',120.0)")

    # --- IPVA (alquiler, índice anual): variación + índice -----------------------
    for fecha, etq, v in (("2024-01-01", "2024", 5.5), ("2025-01-01", "2025", 6.0)):
        c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('ipva_var_anual',?,?,?)",
                  (fecha, etq, v))
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('ipva_indice','2025-01-01','2025',109.0)")

    # --- EH: Total Nacional (2 años, tendencia bajando) + 19 CCAA del año último --
    for fecha, v in (("2024", 15000.0), ("2025", 14000.0)):
        c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) "
                  "VALUES('eh:Total Nacional',?,?,?)", (fecha, "Total Nacional", v))
    anyo_eh = "2025"
    for i, nombre in enumerate(territorios.NOMBRES):     # 19 canónicas
        c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('eh:'||?,?,?,?)",
                  (nombre, anyo_eh, nombre, 900.0 - i * 37.0))

    # --- VUT: Total Nacional + % y las 19 CCAA del año ---------------------------
    anyo_vut = "2025"
    vut_nac = 320000.0
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('vte:Total Nacional',?,?,?)",
              (anyo_vut, "Total Nacional", vut_nac))
    c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('vte_pct',?,?,?)",
              (anyo_vut, "pct", 1.24))
    for i, nombre in enumerate(territorios.NOMBRES):
        c.execute("INSERT INTO ine_serie(serie,fecha,etiqueta,valor) VALUES('vte:'||?,?,?,?)",
                  (nombre, anyo_vut, nombre, 20000.0 + i * 1000.0))

    # --- Lanzamientos (CGPJ): cronología TOTAL + 17 CCAA del último trimestre -----
    totales = [("25-T3", 3800.0), ("25-T4", 3900.0), ("26-T1", 4000.0)]
    for periodo, v in totales:
        c.execute("INSERT INTO lanzamientos(ambito,periodo,valor) VALUES('TOTAL',?,?)", (periodo, v))
    per_lz = "26-T1"
    for i, nombre in enumerate(territorios.NOMBRES):
        if nombre in ("Ceuta", "Melilla"):      # huecos declarados en territorios.HUECOS
            continue
        c.execute("INSERT INTO lanzamientos(ambito,periodo,valor) VALUES(?,?,?)",
                  (nombre, per_lz, 600.0 - i * 23.0))

    c.commit()
    print(f"[fixture] data/vivienda.db sintética generada: {len(normas)} boe · "
          f"{20 + 19 + 4} serie INE · {sum(len(t) for t in (totales,)) + 17} lanzamientos")
    return 0


if __name__ == "__main__":
    sys.exit(main())