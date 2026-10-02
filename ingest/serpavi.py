#!/usr/bin/env python3
"""SERPAVI / MIVAU — alquiler de referencia por municipio (2-oct-2026).

Fuente OFICIAL: Ministerio de Vivienda y Agenda Urbana (MIVAU), CSV público
`VDP001_01.csv` (SERPAVI: mediana de la cuantía de los contratos de alquiler, a
partir de fianzas Catastro/AEAT), último año disponible (2024). NO es precio de
oferta de portales, y NO es el scraper retirado en `a4b648d`.

Se lee de `via.db` (municipal-intel) la tabla `via_index`, columnas `oficial_*`,
que `via_mivau.py` rellena desde ese CSV. Solo filas con dato oficial (se
excluye el scraper de anuncios).

LÍMITES (documentados en la web): es la mediana de TODOS los contratos
(incluidos antiguos con renta congelada), por lo que suele ser MÁS BAJA que el
precio de un contrato nuevo; y el CSV es agregado, así que NO hay `n` por
municipio en la fuente (MIVAU solo publica donde hay datos suficientes).
"""
from __future__ import annotations

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
VIA = "/home/deploy/municipal-intel/dashboard/data/via/via.db"


def _con():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS serpavi(
        codigo_ine TEXT PRIMARY KEY, municipio TEXT, provincia TEXT,
        eur_m2 REAL, p25 REAL, p75 REAL, anio TEXT)""")
    return c


def ingest() -> int:
    c = _con()
    c.execute("DELETE FROM serpavi")
    v = sqlite3.connect(f"file:{VIA}?mode=ro", uri=True)
    v.row_factory = sqlite3.Row
    n = 0
    for r in v.execute("SELECT codigo_ine, municipio, provincia, oficial_eur_m2, "
                       "oficial_p25, oficial_p75, oficial_anio FROM via_index "
                       "WHERE oficial_eur_m2 IS NOT NULL"):
        c.execute("INSERT OR REPLACE INTO serpavi VALUES(?,?,?,?,?,?,?)",
                  (str(r["codigo_ine"] or ""), r["municipio"] or "",
                   (r["provincia"] or "").strip(), float(r["oficial_eur_m2"]),
                   r["oficial_p25"], r["oficial_p75"], str(r["oficial_anio"] or "")))
        n += 1
    c.commit()
    return n


def _ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def top(n=12):
    try:
        return _ro().execute("SELECT municipio, provincia, eur_m2 FROM serpavi "
                             "ORDER BY eur_m2 DESC LIMIT ?", (n,)).fetchall()
    except sqlite3.Error:
        return []


def bottom(n=12):
    try:
        return _ro().execute("SELECT municipio, provincia, eur_m2 FROM serpavi "
                             "ORDER BY eur_m2 ASC LIMIT ?", (n,)).fetchall()
    except sqlite3.Error:
        return []


def total_anio():
    try:
        r = _ro().execute("SELECT COUNT(*), MAX(anio) FROM serpavi").fetchone()
        return (r[0] or 0), (r[1] or "")
    except sqlite3.Error:
        return 0, ""


if __name__ == "__main__":
    print(f"[serpavi] municipios con dato oficial: {ingest()}")
