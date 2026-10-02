#!/usr/bin/env python3
"""Ingesta IPC residencial (INE wstempus, base 2025 / ECOICOP ver.2). F1, 2-oct-2026.

Lee por código de serie (`DATOS_SERIE`) la variación anual, el índice y la
ponderación de los componentes del grupo 04 (Vivienda, agua, electricidad, gas y
otros combustibles) y los guarda en `data/vivienda.db` (tabla `ipc_serie`).

Por qué: el observatorio medía el mercado inmobiliario (IPV/IPVA/lanzamientos/
ejecuciones/VUT) pero no la formación del **coste residencial** (qué encarece
vivir en una vivienda). El grupo 04 pesa ~12,26 % del IPC de 2026.

Cuidado (documentado en el propio tile): un **índice** no es un **precio**, y el
grupo 04 **no** es el coste total del hogar (no incluye alimentación, transporte,
etc.). La base 2025 arranca en ene-2026: NO se cruza con la base 2021 sin la
serie enlazada del INE; aquí solo se usa la variación anual publicada.
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")

# componente -> (etiqueta, cod_var_anual, cod_indice, cod_ponderacion)
# Códigos verificados contra servicios.ine.es/wstempus (2-oct-2026).
COMPONENTES = {
    "general":       ("IPC general",                "IPC290750", "IPC290751", None),
    "vivienda":      ("Vivienda (grupo 04)",        "IPC290762", "IPC290763", "IPC331939"),
    "alquiler":      ("Alquiler de vivienda",       "IPC291806", "IPC291807", "IPC332200"),
    "electricidad":  ("Electricidad",               "IPC291482", "IPC291483", "IPC332119"),
    "gas":           ("Gas natural",                "IPC291842", None,        "IPC332209"),
    "combustibles":  ("Combustibles líquidos",      "IPC291486", None,        "IPC332120"),
    "agua":          ("Agua (suministro en red)",   "IPC291826", None,        "IPC332205"),
    "mantenimiento": ("Mantenimiento y reparación", "IPC291822", None,        "IPC332204"),
    "comunitarios":  ("Gastos comunitarios",        "IPC291838", None,        "IPC332208"),
}
# Componentes que forman el grupo 04, para la contribución a su variación.
RESIDENCIALES = ("alquiler", "electricidad", "gas", "combustibles",
                 "agua", "mantenimiento", "comunitarios")
TIPOS = ("var_anual", "indice", "ponderacion")


def _con():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS ipc_serie(
        componente TEXT, tipo TEXT, fecha TEXT, valor REAL, PRIMARY KEY(componente, tipo, fecha))""")
    return c


def _get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)"})
    return json.load(urllib.request.urlopen(req, timeout=45))


def _datos(cod: str, nult: int):
    d = _get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{cod}?nult={nult}")
    return d if isinstance(d, list) else [d]


def _fecha(x) -> str:
    """Fecha ISO del punto. INE devuelve `Fecha` como epoch (ms) para estas
    series, así que se construye desde `Anyo` + `FK_Periodo` (mes 1-12)."""
    try:
        a = int(x.get("Anyo"))
    except (TypeError, ValueError):
        return ""
    try:
        p = int(x.get("FK_Periodo"))
    except (TypeError, ValueError):
        return str(a)
    return f"{a}-{p:02d}-01" if 1 <= p <= 12 else str(a)


def ingest() -> int:
    c = _con()
    c.execute("DELETE FROM ipc_serie")   # reingesta autoritativa (re-fetch completo)
    n = 0
    for comp, (_etq, cvar, cidx, cpond) in COMPONENTES.items():
        for tipo, cod in (("var_anual", cvar), ("indice", cidx), ("ponderacion", cpond)):
            if not cod:
                continue
            nult = 1 if tipo == "ponderacion" else 25
            for s in _datos(cod, nult):
                for x in s.get("Data", []):
                    val = x.get("Valor")
                    if val is None:
                        continue
                    fecha = _fecha(x)
                    if not fecha:
                        continue
                    n += c.execute("INSERT OR REPLACE INTO ipc_serie VALUES(?,?,?,?)",
                                   (comp, tipo, fecha, float(val))).rowcount
    c.commit()
    return n


# --- lecturas ---------------------------------------------------------------
def _ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def serie(comp: str, tipo: str = "var_anual"):
    """[(fecha, valor)] ordenado por fecha."""
    try:
        return _ro().execute("SELECT fecha, valor FROM ipc_serie WHERE componente=? AND tipo=? "
                             "ORDER BY fecha", (comp, tipo)).fetchall()
    except sqlite3.Error:
        return []


def ultimo(comp: str, tipo: str = "var_anual"):
    s = serie(comp, tipo)
    return (s[-1][1], s[-1][0]) if s else (None, None)


def ponderacion(comp: str):
    s = serie(comp, "ponderacion")
    return s[-1][1] if s else None


def contribucion():
    """[(etiqueta, pp)] de cada componente residencial a la variación del grupo 04.

    pp_i = var_anual_i * (peso_i / peso_grupo04). Se normaliza por el peso del
    grupo (no por la suma de los incluidos) para que el Σ de las pp ≈ la variación
    del grupo publicada; el resto hasta esa cifra se agrega como «Resto del grupo».
    """
    grupo_w = ponderacion("vivienda")
    gvar, _ = ultimo("vivienda", "var_anual")
    pesos, vars_ = {}, {}
    for comp in RESIDENCIALES:
        p = ponderacion(comp)
        v, _ = ultimo(comp, "var_anual")
        if p is not None and v is not None:
            pesos[comp] = p
            vars_[comp] = v
    tot = grupo_w or sum(pesos.values())
    if not tot:
        return []
    filas = [(COMPONENTES[c][0], round(vars_[c] * pesos[c] / tot, 2)) for c in pesos]
    filas.sort(key=lambda t: -t[1])
    if grupo_w and gvar is not None:
        resto = round(gvar - sum(v for _, v in filas), 2)
        if resto > 0.05:
            filas.append(("Resto del grupo 04", resto))
    return filas


if __name__ == "__main__":
    print(f"[ipc] puntos actualizados: {ingest()}")
