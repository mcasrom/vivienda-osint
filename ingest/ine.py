"""Ingesta INE (datos abiertos wstempus):
  · IPVA (tabla 59056): Índice de Precios de Vivienda (compraventa) nacional.
  · IPV  (tabla 80270): precios por CCAA (variación anual, trimestral).
Guarda series en data/vivienda.db.
"""
from __future__ import annotations
import os, json, sqlite3, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
TABLAS = {"ipva": 59056, "ipv": 80270}


def _con():
    c = sqlite3.connect(DB)
    cols = [r[1] for r in c.execute("PRAGMA table_info(ine_serie)").fetchall()]
    if cols and cols != ["serie", "fecha", "etiqueta", "valor"]:
        c.execute("DROP TABLE ine_serie")
    c.execute("""CREATE TABLE IF NOT EXISTS ine_serie(
        serie TEXT, fecha TEXT, etiqueta TEXT, valor REAL, PRIMARY KEY(serie, fecha))""")
    return c


def _get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)"})
    return json.load(urllib.request.urlopen(req, timeout=45))


def _etq(x):
    a = x.get("Anyo")
    p = (x.get("T3_Periodo") or "").upper()
    # trimestral: T1..T4 -> letra Q
    if p in ("T1", "T2", "T3", "T4"):
        return f"{a} {p[1]}T"
    return str(a)


def ingest() -> int:
    c = _con()
    n = 0
    # IPVA (nacional: índice + variación anual)
    for s in _get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{TABLAS['ipva']}?nult=25&tip=AM"):
        nom = s.get("Nombre", "")
        key = ("ipva_indice" if nom.startswith("Total Nacional. Total. Índice")
               else "ipva_var_anual" if nom.startswith("Total Nacional. Total. Variación anual") else None)
        if not key:
            continue
        for x in s.get("Data", []):
            if x.get("Valor") is None:
                continue
            n += c.execute("INSERT OR REPLACE INTO ine_serie VALUES(?,?,?,?)",
                           (key, x.get("Fecha", "")[:10], _etq(x), float(x["Valor"]))).rowcount
    # IPV (compraventa, nacional general)
    for s in _get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{TABLAS['ipv']}?nult=12&tip=AM"):
        nom = s.get("Nombre", "")
        key = ("ipv_indice" if nom == "Nacional. General. Índice. "
               else "ipv_var_anual" if nom == "Nacional. General. Variación anual. "
               else "ipv_nueva_var" if nom == "Nacional. Vivienda nueva. Variación anual. "
               else "ipv_segunda_var" if nom == "Nacional. Vivienda de segunda mano. Variación anual. " else None)
        if not key:
            continue
        for x in s.get("Data", []):
            if x.get("Valor") is None:
                continue
            n += c.execute("INSERT OR REPLACE INTO ine_serie VALUES(?,?,?,?)",
                           (key, x.get("Fecha", "")[:10], _etq(x), float(x["Valor"]))).rowcount
    c.commit()
    return n


def ingest_eh() -> int:
    """EH (tabla 10740): ejecuciones hipotecarias de vivienda iniciadas, por CCAA (anual)."""
    c = _con()
    n = 0
    for s in _get("https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/10740?nult=6&tip=AM"):
        nom = s.get("Nombre", "")
        if "General. Número." not in nom:
            continue
        ccaa = nom.split(".")[0].strip()
        for x in s.get("Data", []):
            if x.get("Valor") is None:
                continue
            n += c.execute("INSERT OR REPLACE INTO ine_serie VALUES(?,?,?,?)",
                           ("eh:" + ccaa, str(x.get("Anyo")), ccaa, float(x["Valor"]))).rowcount
    c.commit()
    return n


def eh_ccaa(anyo=None):
    """[(ccaa, valor)] del último año disponible (o el indicado), ordenado desc."""
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    if anyo is None:
        anyo = c.execute("SELECT MAX(CAST(fecha AS INT)) FROM ine_serie WHERE serie LIKE 'eh:%'").fetchone()[0]
    rows = c.execute("SELECT etiqueta, valor FROM ine_serie WHERE serie LIKE 'eh:%' AND fecha=? "
                     "AND etiqueta<>'Total Nacional' ORDER BY valor DESC", (str(anyo),)).fetchall()
    total = c.execute("SELECT valor FROM ine_serie WHERE serie='eh:Total Nacional' AND fecha=?", (str(anyo),)).fetchone()
    return rows, anyo, (total[0] if total else None)


def ingest_vte() -> int:
    """VTE (tabla 46141): viviendas turísticas por CCAA (dato base) + % nacional."""
    c = _con()
    n = 0
    d = _get("https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/46141?nult=2&tip=A")
    for s in d:
        nom = s.get("Nombre", "")
        data = s.get("Data", [])
        if not data:
            continue
        x = max(data, key=lambda p: p.get("Fecha") or "")
        if x.get("Valor") is None:
            continue
        if "Viviendas turísticas. Dato base." in nom:
            ambito = nom.split(".")[0].strip()
            n += c.execute("INSERT OR REPLACE INTO ine_serie VALUES(?,?,?,?)",
                           ("vte:" + ambito, str(x.get("Anyo")), ambito, float(x["Valor"]))).rowcount
        elif nom.startswith("Total Nacional. Porcentaje de viviendas turísticas"):
            c.execute("INSERT OR REPLACE INTO ine_serie VALUES(?,?,?,?)",
                      ("vte_pct", str(x.get("Anyo")), "pct", float(x["Valor"])))
    c.commit()
    return n


def vte_ccaa():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    anyo = c.execute("SELECT MAX(fecha) FROM ine_serie WHERE serie LIKE 'vte:%'").fetchone()[0]
    rows = c.execute("SELECT etiqueta, valor FROM ine_serie WHERE serie LIKE 'vte:%' AND fecha=? "
                     "AND etiqueta<>'Total Nacional' ORDER BY valor DESC", (anyo,)).fetchall()
    tot = c.execute("SELECT valor FROM ine_serie WHERE serie='vte:Total Nacional' AND fecha=?", (anyo,)).fetchone()
    pct = c.execute("SELECT valor FROM ine_serie WHERE serie='vte_pct'").fetchone()
    return rows, anyo, (tot[0] if tot else None), (pct[0] if pct else None)


def eh_nacional():
    """[(año, valor)] de la serie nacional de ejecuciones hipotecarias."""
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        return c.execute("SELECT fecha, valor FROM ine_serie WHERE serie='eh:Total Nacional' ORDER BY fecha").fetchall()
    except Exception:
        return []


def serie(nombre: str):
    try:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        return c.execute("SELECT etiqueta, valor FROM ine_serie WHERE serie=? ORDER BY fecha", (nombre,)).fetchall()
    except Exception:
        return []


def ultimo(nombre: str):
    s = serie(nombre)
    return s[-1][1] if s else None


if __name__ == "__main__":
    print(f"[ine] puntos actualizados: {ingest()} · EH: {ingest_eh()} · VTE: {ingest_vte()}")
