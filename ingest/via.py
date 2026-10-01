"""Reutiliza DATOS de municipal-intel (via.db): precios de alquiler por municipio.

Comparte datos (librería), NO ejecución: este microservicio es estático.
"""
from __future__ import annotations
import sqlite3

VIA = "/home/deploy/municipal-intel/dashboard/data/via/via.db"


def _ro(path: str):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def resumen():
    try:
        c = _ro(VIA)
        fecha = c.execute("SELECT MAX(fecha) FROM via_index").fetchone()[0]
        rows = c.execute(
            "SELECT municipio, provincia, eur_m2_mediana, alq_mediana_80m2, slug, codigo_ine "
            "FROM via_index WHERE fecha=? AND eur_m2_mediana IS NOT NULL "
            "ORDER BY eur_m2_mediana DESC", (fecha,)).fetchall()
        n = len(rows)
        med = rows[n // 2][2] if rows else None
        return {"fecha": fecha, "rows": rows, "n": n, "mediana": med}
    except Exception as e:  # noqa: BLE001
        print(f"[via] sin datos ({e})", flush=True)
        return {"fecha": None, "rows": [], "n": 0, "mediana": None}
