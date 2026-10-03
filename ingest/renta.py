#!/usr/bin/env python3
"""Ingesta INE — Atlas de Distribución de Renta de los Hogares (ADRH), por municipio.

Fuente: INE, «Indicadores de renta media y mediana» (operación ADRH), descarga masiva
CSV por tabla: https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/<tabla>.csv
El CSV trae el municipio como «02001 Abengibre» (código INE + nombre) y el indicador
(«Renta neta media por hogar» / «... por persona»), con el periodo (año).

El ADRH está partido en ~540 tablas (por provincia y grupo); el mapa provincia→tabla
se cachea en `data/adrh_tablas.json` (lo genera un discovery; ver `_descubrir`).
Es dato ANUAL: no entra en el cron diario (se reingiere cuando el INE lo publica).

Guarda en `data/vivienda.db` la tabla `renta_municipio(codigo_ine, municipio, periodo,
renta_hogar, renta_persona)`.
"""
from __future__ import annotations
import csv
import io
import json
import os
import sqlite3
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
MAP = os.path.join(ROOT, "data", "adrh_tablas.json")
BASE = "https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/%s.csv"
UA = {"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)"}
IND_COL = "Indicadores de renta media y mediana"
IND_HOGAR = "Renta neta media por hogar"
IND_PERSONA = "Renta neta media por persona"


def _con():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS renta_municipio(
        codigo_ine TEXT PRIMARY KEY, municipio TEXT, periodo TEXT,
        renta_hogar REAL, renta_persona REAL)""")
    return c


def _num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _csv(tid):
    req = urllib.request.Request(BASE % tid, headers=UA)
    return urllib.request.urlopen(req, timeout=90).read().decode("utf-8-sig", "ignore")


def ingest() -> tuple[int, str]:
    tablas = json.load(open(MAP, encoding="utf-8")).get("tablas") or {}
    if not tablas:
        raise RuntimeError(f"mapa vacío: {MAP}")
    from concurrent.futures import ThreadPoolExecutor
    tids = list(tablas.values())
    with ThreadPoolExecutor(max_workers=8) as ex:
        textos = list(ex.map(_csv, tids))
    # codigo -> {"municipio", ind -> (periodo, valor)}
    acc: dict[str, dict] = {}
    for txt in textos:
        for row in csv.DictReader(io.StringIO(txt), delimiter=";"):
            ind = (row.get(IND_COL) or "").strip()
            if ind not in (IND_HOGAR, IND_PERSONA):
                continue
            code = (row.get("Municipios") or "").strip()
            if not code or not code[:5].isdigit():
                continue
            if (row.get("Distritos") or "").strip() or (row.get("Secciones") or "").strip():
                continue  # fila de distrito/sección, no de municipio
            codigo = code[:5]
            per = (row.get("Periodo") or "").strip()
            val = _num(row.get("Total"))
            if val is None:
                continue
            d = acc.setdefault(codigo, {"municipio": code.split(" ", 1)[1] if " " in code else code})
            prev = d.get(ind)
            if prev is None or per >= prev[0]:
                d[ind] = (per, val)
    c = _con()
    c.execute("DELETE FROM renta_municipio")
    n = 0
    per_ult = ""
    for codigo, d in acc.items():
        h = d.get(IND_HOGAR)
        p = d.get(IND_PERSONA)
        if not h and not p:
            continue
        per = (h or p)[0]
        per_ult = max(per_ult, per)
        c.execute("INSERT OR REPLACE INTO renta_municipio VALUES(?,?,?,?,?)",
                  (codigo, d["municipio"], per, h[1] if h else None, p[1] if p else None))
        n += 1
    c.commit()
    return n, per_ult


def cruce_serpavi():
    """Cruza la renta por municipio con el alquiler de referencia SERPAVI (por código INE).

    Devuelve [(codigo, municipio, provincia, per_renta, renta_hogar, eur_m2, anio_serpavi,
    alquiler_80m2, esfuerzo_pct), ...] ordenado por esfuerzo desc.
    """
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    renta = {r[0]: (r[1], r[2]) for r in
             c.execute("SELECT codigo_ine, renta_hogar, periodo FROM renta_municipio")}
    out = []
    for cod, mun, prov, eur, anio in c.execute(
            "SELECT codigo_ine, municipio, provincia, eur_m2, anio FROM serpavi"):
        rr = renta.get(cod)
        if not rr or not rr[0] or not eur:
            continue
        renta_h, per = rr
        alq = eur * 80                       # piso de referencia de 80 m²
        esf = alq * 12 / renta_h * 100        # % de la renta anual del hogar
        out.append((cod, mun, prov, per, renta_h, eur, anio, round(alq, 1), round(esf, 1)))
    out.sort(key=lambda r: -r[8])
    return out


if __name__ == "__main__":
    n, per = ingest()
    cr = cruce_serpavi()
    print(f"[renta] {n} municipios · último año {per} · cruce SERPAVI {len(cr)} municipios")
    for r in cr[:3]:
        print(f"  {r[1]} ({r[2]}): renta {r[4]:.0f} € · alquiler 80m² {r[7]:.0f} €/mes · {r[8]:.1f} %")
