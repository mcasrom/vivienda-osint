"""Ingesta INE: IPVA (Índice de Precios de Vivienda). Serie nacional (índice + variación anual).

Fuente: INE wstempus (datos abiertos). Guarda en data/vivienda.db.
"""
from __future__ import annotations
import os, json, sqlite3, urllib.request

TABLA = 59056  # IPVA: índices nacionales y por CCAA
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")


def _con():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS ine_serie(
        serie TEXT, anyo INTEGER, valor REAL, PRIMARY KEY(serie, anyo))""")
    return c


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)"})
    return json.load(urllib.request.urlopen(req, timeout=40))


def ingest() -> int:
    d = _get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{TABLA}?nult=25&tip=AM")
    c = _con()
    n = 0
    for s in d:
        nom = s.get("Nombre", "")
        if nom.startswith("Total Nacional. Total. Índice"):
            serie = "ipva_indice"
        elif nom.startswith("Total Nacional. Total. Variación anual"):
            serie = "ipva_var_anual"
        else:
            continue
        for x in s.get("Data", []):
            v = x.get("Valor")
            a = x.get("Anyo")
            if v is None or a is None:
                continue
            cur = c.execute("INSERT OR REPLACE INTO ine_serie(serie,anyo,valor) VALUES(?,?,?)", (serie, int(a), float(v)))
            n += cur.rowcount
    c.commit()
    return n


def serie(nombre: str):
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        return c.execute("SELECT anyo, valor FROM ine_serie WHERE serie=? ORDER BY anyo", (nombre,)).fetchall()
    except Exception:
        return []


if __name__ == "__main__":
    print(f"[ine] puntos actualizados: {ingest()}")
