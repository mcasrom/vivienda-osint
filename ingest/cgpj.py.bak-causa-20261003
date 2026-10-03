"""Ingesta CGPJ — Lanzamientos (desahucios) por CCAA y trimestre.

Fuente: «Datos sobre el efecto de la crisis en los órganos judiciales» (Excel trimestral),
https://www.poderjudicial.es/cgpj/es/Temas/Estadistica-Judicial/.../Efecto-de-la-Crisis-en-los-organos-judiciales/
Hoja objetivo: 'Lanzamientos practic. total TSJ'. Guarda en data/vivienda.db (tabla lanzamientos).

Las etiquetas del CGPJ se traducen al nombre canónico del INE (`ingest/territorios`):
el XLSX viene en mayúsculas y abreviaturas («MADRID, COMUNIDAD») y el INE usa
«Madrid, Comunidad de». Sin esa traducción la misma fila se llamaba de dos formas
en dos páginas del observatorio.
"""
from __future__ import annotations
import os, re, sqlite3, sys, urllib.request, tempfile
import openpyxl

from ingest import territorios

PAGINA = ("https://www.poderjudicial.es/cgpj/es/Temas/Estadistica-Judicial/Estadistica-por-temas/"
          "Datos-penales--civiles-y-laborales/Civil-y-laboral/Efecto-de-la-Crisis-en-los-organos-judiciales/")
BASE = "https://www.poderjudicial.es"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
HOJA = "Lanzamientos practic. total TSJ"
UA = {"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)"}


def _con():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS lanzamientos(ambito TEXT, periodo TEXT, valor REAL, PRIMARY KEY(ambito,periodo))")
    return c


def _get(url, bin=False):
    req = urllib.request.Request(url, headers=UA)
    d = urllib.request.urlopen(req, timeout=60).read()
    return d if bin else d.decode("utf-8", "ignore")


def _clave(nombre):
    m = re.search(r"(\d)T[\s-]*(\d{4})", nombre)
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def _latest_xlsx():
    html = _get(PAGINA)
    cands = []
    for href in re.findall(r'href="([^"]+\.xlsx[^"]*)"', html):
        h = href.lower()
        if ("datos sobre el efecto de la crisis" in h
                and "por provincias" not in h and "series" not in h
                and "mercantil" not in h):
            cands.append((_clave(href), href))
    if not cands:
        raise RuntimeError("sin xlsx de crisis")
    cands.sort(reverse=True)
    return BASE + cands[0][1].replace(" ", "%20")


def ingest() -> tuple[int, str, str]:
    url = _latest_xlsx()
    raw = _get(url, bin=True)
    tmp = os.path.join(tempfile.gettempdir(), "cgpj_lanz.xlsx")
    with open(tmp, "wb") as f:
        f.write(raw)
    wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
    ws = None
    for n in wb.sheetnames:
        ln = n.lower().replace(".", " ")
        if "lanzamiento" in ln and "total" in ln:
            ws = wb[n]
            break
    if ws is None:
        for n in wb.sheetnames:
            if "lanzamiento" in n.lower() and "recibidos" not in n.lower():
                ws = wb[n]
                break
    if ws is None:
        raise RuntimeError("sin hoja de lanzamientos: " + " | ".join(wb.sheetnames))
    filas = list(ws.iter_rows(values_only=True))
    # localiza la fila de cabecera (con 'NN-TN')
    hi = next(i for i, r in enumerate(filas) if any(isinstance(c, str) and re.fullmatch(r"\d\d-T\d", c.strip()) for c in r))
    header = filas[hi]
    cols = [(j, c.strip()) for j, c in enumerate(header) if isinstance(c, str) and re.fullmatch(r"\d\d-T\d", c.strip())]
    ult_periodo = cols[-1][1]      # el más reciente (p. ej. 26-T1)
    # lee SOLO el primer bloque (CCAA...TOTAL) para no mezclar con bloques posteriores
    bloque = []
    for r in filas[hi + 1:]:
        amb = r[1] if isinstance(r[1], str) else None
        if amb is None or not amb.strip():
            if bloque:
                break
            continue
        bloque.append((amb.strip(), r))
        if amb.strip().upper() == "TOTAL":
            break
    c = _con()
    # --- etiquetas: CGPJ -> nombre canónico del INE; lo desconocido se avisa (no se descarta) ---
    filas_ccaa, desconocidas = [], []
    for amb, r in bloque:
        if amb.upper() == "TOTAL":
            continue
        canon = territorios.canonico(amb)
        if canon is None:
            desconocidas.append(amb)
            continue
        val = r[cols[-1][0]]
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        filas_ccaa.append((canon, ult_periodo, v))
    if desconocidas:
        print(f"[cgpj] AVISO: {len(desconocidas)} etiquetas no reconocidas y NO publicadas: "
              f"{desconocidas}", file=sys.stderr)
    # borra las filas del periodo con etiquetas antiguas (mismo dato, otro nombre)
    c.execute("DELETE FROM lanzamientos WHERE periodo=? AND ambito<>'TOTAL' AND ambito NOT IN (%s)"
              % ",".join("?" * len(territorios.NOMBRES)), [ult_periodo, *territorios.NOMBRES])
    stale = c.execute("SELECT DISTINCT periodo FROM lanzamientos WHERE ambito<>'TOTAL' "
                      "AND ambito NOT IN (%s)" % ",".join("?" * len(territorios.NOMBRES)),
                      tuple(territorios.NOMBRES)).fetchall()
    if stale:
        print(f"[cgpj] AVISO: quedan filas con etiquetas antiguas en periodos "
              f"{sorted(p[0] for p in stale)} (histórico, no publicado)", file=sys.stderr)
    n = 0
    for canon, per, v in filas_ccaa:
        n += c.execute("INSERT OR REPLACE INTO lanzamientos VALUES(?,?,?)", (canon, per, v)).rowcount
    # cronología nacional (fila TOTAL, todas las columnas)
    for amb, r in bloque:
        if amb.upper() == "TOTAL":
            for j, per in cols:
                try:
                    c.execute("INSERT OR REPLACE INTO lanzamientos VALUES(?,?,?)", ("TOTAL", per, float(r[j])))
                except (TypeError, ValueError):
                    pass
    c.commit()
    return n, ult_periodo, os.path.basename(url)


def por_ccaa(periodo=None):
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    if periodo is None:
        periodo = c.execute("SELECT MAX(periodo) FROM lanzamientos").fetchone()[0]
    rows = c.execute("SELECT ambito, valor FROM lanzamientos WHERE periodo=? AND ambito<>'TOTAL' ORDER BY valor DESC", (periodo,)).fetchall()
    total = c.execute("SELECT valor FROM lanzamientos WHERE periodo=? AND ambito='TOTAL'", (periodo,)).fetchone()
    # red de seguridad: si la BD aún tiene etiquetas antiguas (p. ej. sin reingesta),
    # se normalizan al leer. La ingesta ya las escribe canónicas.
    rows = [(territorios.canonico(a) or a, v) for a, v in rows]
    return territorios.ordenar(rows), periodo, (total[0] if total else None)


def cronologia():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    return c.execute("SELECT periodo, valor FROM lanzamientos WHERE ambito='TOTAL' ORDER BY periodo").fetchall()


if __name__ == "__main__":
    n, per, f = ingest()
    print(f"[cgpj] {n} CCAA · último periodo {per} · {f}")