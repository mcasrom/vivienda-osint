#!/usr/bin/env python3
"""Contratos de datos del observatorio de vivienda (sin dependencias).

Se ejecuta con el intérprete del venv:  venv/bin/python tests/test_datos.py
Sale con 1 si algo falla. Comprueba que:
  1. data/normas.json carga y su 'actualizado' es ISO-8601.
  2. Cada norma registrada existe en la tabla boe y su fecha BOE coincide.
  3. Cada 'estado' está en el vocabulario declarado.
  4. Un resultado (convalidada/derogada) exige resultado + resultado_fecha.
  5. Una norma pendiente NO puede tener resultado.
  6. Cronología: aprobación < BOE <= vigencia.
  7. Toda fila del CSV publicado tiene 'estado' no vacío.
"""
from __future__ import annotations
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ingest import territorios  # noqa: E402

# Identifica qué artefacto se comprueba:
#  - --web-dir DIR: directorio web a validar (def. ROOT/web). El cron de staging
#    lo pasa con web_tmp/ para comprobar ANTES de publicar.
import argparse as _argparse
_ap = _argparse.ArgumentParser()
_ap.add_argument("--web-dir", default=None,
                 help="directorio web (index.html, data/) a validar (def. ROOT/web)")
_ap.add_argument("--db", default=None, help="ruta a data/vivienda.db (def. ROOT/data/vivienda.db)")
_a = _ap.parse_args()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _a.web_dir and (os.sep in _a.web_dir or _a.web_dir in ("..", ".", "/")):
    print(f"test_datos: --web-dir no puede contener rutas: {_a.web_dir!r}", file=sys.stderr)
    sys.exit(2)
WEB = os.path.join(ROOT, _a.web_dir) if _a.web_dir else os.path.join(ROOT, "web")
DB_P = _a.db or os.path.join(ROOT, "data", "vivienda.db")
FALLOS: list[str] = []
OMITIDO: list[str] = []

# Tabla canónica: todo nombre de CCAA publicado debe salir de aquí.
CCAA_CSV = ("ejecuciones-hipotecarias-ccaa", "compraventas-ccaa", "viviendas-turisticas-ccaa", "lanzamientos-ccaa")


def check(cond: bool, msg: str) -> None:
    if not cond:
        FALLOS.append(msg)


def _d(s: str):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


reg = json.load(open(os.path.join(ROOT, "data", "normas.json"), encoding="utf-8"))

# 1. actualizado ISO-8601
check(bool(re.match(r"^\d{4}-\d{2}-\d{2}T", str(reg.get("actualizado", "")))),
      f"normas.json: 'actualizado' no es ISO-8601: {reg.get('actualizado')!r}")
vocab = set(reg.get("estados") or [])

db_p = DB_P
en_boe: dict[str, str] = {}
if os.path.exists(db_p):
    con = sqlite3.connect(db_p)
    en_boe = {r[0]: r[1] for r in con.execute("SELECT id, fecha FROM boe")}
else:
    OMITIDO.append("data/vivienda.db (no en git): checks 2+ sin DB")

for n in reg.get("normas") or []:
    nid = n.get("id", "?")
    # 2. existe en la tabla boe y la fecha coincide
    if en_boe:
        if nid not in en_boe:
            check(False, f"{nid}: no está en la tabla boe (ingest/boe.py)")
        else:
            check(en_boe[nid] == n.get("boe"),
                  f"{nid}: fecha BOE del registro ({n.get('boe')}) != tabla boe ({en_boe[nid]})")
    # 3. vocabulario
    check(n.get("estado") in vocab, f"{nid}: estado {n.get('estado')!r} fuera de {sorted(vocab)}")
    # 4/5. resultado coherente con el estado
    if n.get("estado") in ("convalidada", "derogada"):
        check(bool(n.get("resultado")), f"{nid}: estado {n['estado']} sin 'resultado'")
        check(bool(n.get("resultado_fecha")), f"{nid}: estado {n['estado']} sin 'resultado_fecha'")
    if n.get("estado") == "en_votacion":
        check(not n.get("resultado"), f"{nid}: pendiente de votación pero con 'resultado'")
        check(not n.get("resultado_fecha"), f"{nid}: pendiente de votación pero con 'resultado_fecha'")
    # 6. cronología
    a, b, v = _d(n.get("aprobacion", "")), _d(n.get("boe", "")), _d(n.get("vigencia", ""))
    check(bool(a) and bool(b), f"{nid}: 'aprobacion' o 'boe' no son fechas ISO")
    if a and b:
        check(a <= b, f"{nid}: aprobación {a} posterior a BOE {b}")
    if b and v:
        check(b < v, f"{nid}: vigencia {v} no posterior a BOE {b}")

# 7. el CSV publicado declara estado en todas sus filas
csv_p = os.path.join(WEB, "data", "boe-vivienda.csv")
if os.path.exists(csv_p):
    with open(csv_p, encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        check("estado" in (rd.fieldnames or []), "boe-vivienda.csv no tiene columna 'estado'")
        filas = list(rd)
    for r in filas:
        check(bool(r.get("estado")), f"boe-vivienda.csv: fila {r.get('id')} sin estado")
    for n in reg.get("normas") or []:
        fila = next((r for r in filas if r.get("id") == n["id"]), None)
        check(fila is not None, f"{n['id']}: no aparece en boe-vivienda.csv")
        if fila:
            check(fila.get("estado") == n.get("estado"),
                  f"{n['id']}: estado del CSV ({fila.get('estado')}) != registro ({n.get('estado')})")
else:
    OMITIDO.append("web/data/boe-vivienda.csv (generado)")

# ---------------------------------------------------------------------------
# 8. Nombres de CCAA canónicos, sin duplicados, con los huecos declarados
# ---------------------------------------------------------------------------
for did in CCAA_CSV:
    p_csv = os.path.join(WEB, "data", did + ".csv")
    if not os.path.exists(p_csv):
        OMITIDO.append(f"web/data/{did}.csv (generado)")
        continue
    with open(p_csv, encoding="utf-8") as fh:
        nombres = [r["ccaa"] for r in csv.DictReader(fh)]
    for nb in nombres:
        check(nb in territorios.NOMBRES, f"{did}: '{nb}' no está en la tabla canónica de CCAA")
    check(len(nombres) == len(set(nombres)), f"{did}: CCAA duplicadas")
    huecos = {h for h, _motivo in territorios.HUECOS.get(did, ())}
    faltan = set(territorios.NOMBRES) - set(nombres)
    check(faltan == huecos,
          f"{did}: faltan {sorted(faltan)} y los huecos declarados son {sorted(huecos)}")

# ---------------------------------------------------------------------------
# 9. Contrato CSV <-> HTML: lo que se descarga es lo que se ve en la página
# ---------------------------------------------------------------------------
html_p = os.path.join(WEB, "index.html")
if not os.path.exists(html_p):
    OMITIDO.append("web/index.html (generado)")
if os.path.exists(html_p):
    page = open(html_p, encoding="utf-8").read()
    bloques = re.findall(
        r"Ver el detalle completo · (\d+) comunidades autónomas</summary>"
        r"<table[^>]*><tbody>(.*?)</tbody>", page, re.S)
    check(len(bloques) == len(CCAA_CSV),
          f"se esperaban {len(CCAA_CSV)} bloques de detalle CCAA en la página y hay {len(bloques)}")
    # orden en la página: ejecuciones (EH), lanzamientos (LZ), viviendas turísticas (VUT)
    orden_pagina = ("ejecuciones-hipotecarias-ccaa", "compraventas-ccaa", "lanzamientos-ccaa", "viviendas-turisticas-ccaa")
    for (anunciado, cuerpo), did in zip(bloques, orden_pagina):
        filas = re.findall(r"<tr><td>([^<]+)</td><td class=\"num\">([^<]*)</td></tr>", cuerpo)
        check(len(filas) == int(anunciado),
              f"{did}: la página anuncia {anunciado} filas y pinta {len(filas)}")
        with open(os.path.join(WEB, "data", did + ".csv"), encoding="utf-8") as fh:
            csv_filas = [(r["ccaa"], r[list(r)[-1]]) for r in csv.DictReader(fh)]
        for (nb_html, v_html), (nb_csv, v_csv) in zip(filas, csv_filas):
            check(nb_html == nb_csv,
                  f"{did}: la página muestra '{nb_html}' y el CSV tiene '{nb_csv}'")
            v_num = v_html.replace(".", "").replace(" ", "").replace(",", ".")
            try:
                check(abs(float(v_num) - float(v_csv)) < 1e-6,
                      f"{did}: valor distinto en '{nb_csv}' (página {v_html} vs CSV {v_csv})")
            except ValueError:
                FALLOS.append(f"{did}: valor no numérico en la página para '{nb_html}': {v_html!r}")

# ---------------------------------------------------------------------------
# 10. Contrato de tendencia: la flecha y el color de la tarjeta == latest.json
# ---------------------------------------------------------------------------
# «se modera» es una deceleración, no una bajada: el nivel sigue en +12,2 % y la
# tarjeta no puede pintarse como una caída (flecha ▼ / clase verde de bajada).
FLECHAS = {"se modera": ("▬", ""), "sube más": ("▲", "up"), "estable": ("▬", ""),
           "subiendo": ("▲", "up"), "bajando": ("▼", "down")}
json_latest = os.path.join(WEB, "data", "latest.json")
if not os.path.exists(json_latest):
    OMITIDO.append("web/data/latest.json (generado)")
if os.path.exists(json_latest) and os.path.exists(html_p):
    ind = json.load(open(json_latest, encoding="utf-8"))["indicadores"]
    tarjetas = re.findall(
        r'<div class="ind"><div class="v">([^<]+)<small>([^<]*)</small></div>'
        r'<div class="t ([^"]*)">([^<]*)</div>'
        r'<div class="f">([^<]+)<br><span class="mut">([^<]*)</span>'
        r'(?: · <span class="mut">([^<]*)</span>)?</div>', page)
    CLAVE = {"IPV (compraventa)": "ipv", "IPVA (alquiler)": "ipva",
             "lanzamientos": "lz", "ejecuciones": "eh"}
    # la portada lleva 4 tarjetas; la VUT se publica como ranking, no como indicador
    check(len(tarjetas) == len(CLAVE),
          f"la portada tiene {len(tarjetas)} tarjetas y se esperan {len(CLAVE)}")
    check(set(ind) - set(CLAVE.values()) == {"vut"},
          f"latest.json publica {sorted(set(ind) - set(CLAVE.values()))} y solo la VUT va como ranking")
    for valor, _unidad, cls, tend_txt, fuente, per_txt, _act in tarjetas:
        k = next((v for c, v in CLAVE.items() if c in fuente), None)
        check(k is not None, f"tarjeta de fuente desconocida: {fuente!r}")
        if k is None:
            continue
        etq = ind[k]["tendencia"]
        check(etq in FLECHAS, f"{k}: tendencia {etq!r} sin flecha definida en el test")
        if etq not in FLECHAS:
            continue
        fl, cls_esp = FLECHAS[etq]
        check(tend_txt.strip() == f"{fl} {etq}",
              f"{k}: la tarjeta pinta {tend_txt.strip()!r} y latest.json dice {etq!r} "
              f"(flecha esperada {fl!r})")
        check(cls.strip() == cls_esp,
              f"{k}: color {cls.strip()!r} para la tendencia {etq!r} (esperado {cls_esp!r})")
        num = valor.replace(".", "").replace(",", ".").rstrip("% ")
        try:
            check(abs(float(num) - float(ind[k]["valor"])) < 1e-6,
                  f"{k}: la tarjeta muestra {valor!r} y latest.json {ind[k]['valor']}")
        except ValueError:
            FALLOS.append(f"{k}: valor no numérico en la tarjeta: {valor!r}")
        # la tarjeta puede anteponer un calificador («variación anual · 2026 2T»)
        check(ind[k]["periodo"] in per_txt,
              f"{k}: periodo {per_txt.strip()!r} en la tarjeta y {ind[k]['periodo']!r} en latest.json")

# ---------------------------------------------------------------------------
# 11. Comparador España↔región: el IPV regional es real, no un placeholder
# ---------------------------------------------------------------------------
if not os.path.exists(html_p):
    OMITIDO.append("web/index.html (generado)")
if os.path.exists(html_p):
    fila_ipv = re.search(
        r'<tr[^>]*><td>Compraventa \(IPV, var\. anual\)</td><td>([^<]*)</td>'
        r'<td class="num">([^<]*)</td><td class="num">([^<]*)</td></tr>', page)
    check(fila_ipv is not None, "la página no tiene la fila del comparador de IPV")
    if fila_ipv:
        _per_es, _esp, _reg = fila_ipv.groups()
        check(_esp.strip() != "no ingestado por CCAA",
              "comparador: la celda de España dice «no ingestado por CCAA»")
        _reg_n = _reg.replace(".", "").replace(",", ".").rstrip("% ")
        try:
            float(_reg_n)
        except ValueError:
            FALLOS.append(f"comparador: celda IPV de la región no numérica: {_reg!r}")
            _reg_n = ""
        check(_reg_n != "", f"comparador: el IPV de la región no puede ser {_reg!r}")

# ---------------------------------------------------------------------------
# 12. Frescura de fuentes y edad del dato (F2)
# ---------------------------------------------------------------------------
FRESC = os.path.join(ROOT, "data", "frescura.json")
if not os.path.exists(FRESC):
    OMITIDO.append("data/frescura.json (no generado aún; lo escribe el cron)")
else:
    fr = json.load(open(FRESC, encoding="utf-8"))
    fuentes = fr.get("fuentes") or {}
    for fx in ("ine", "cgpj", "boe"):
        check(fx in fuentes, f"frescura.json: falta la fuente '{fx}'")
    for fx, e in fuentes.items():
        check(isinstance(e.get("ok"), bool),
              f"frescura.json/{fx}: 'ok' debe ser booleano, no {e.get('ok')!r}")
        act = e.get("actualizado")
        check(act is None or bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(act))),
              f"frescura.json/{fx}: 'actualizado' no es ISO date: {act!r}")
    if os.path.exists(html_p):
        check('id="estado"' in page,
              "la portada no incluye el bloque «Estado de datos» (id=estado)")
    if os.path.exists(json_latest):
        _ind3 = json.load(open(json_latest, encoding="utf-8"))["indicadores"]
        for k, iv in _ind3.items():
            check("actualizado" in iv, f"latest.json/{k}: falta 'actualizado'")
            check("edad_dias" in iv, f"latest.json/{k}: falta 'edad_dias'")
            ed = iv.get("edad_dias")
            check(ed is None or isinstance(ed, int),
                  f"latest.json/{k}: 'edad_dias' no es entero ni None: {ed!r}")
    if any((fuentes.get(k) or {}).get("ok") is not None for k in ("ine", "cgpj", "boe")):
        check(os.path.exists(os.path.join(WEB, "data", "estado-fuentes.csv")),
              "web/data/estado-fuentes.csv no se generó (frescura con estado)")

# ---------------------------------------------------------------------------
# 13. IPC residencial: serie publicada coherente + sección en la portada
# ---------------------------------------------------------------------------
p_ipc = os.path.join(WEB, "data", "ipc-vivienda.csv")
if not os.path.exists(p_ipc):
    OMITIDO.append("web/data/ipc-vivienda.csv (generado; requiere ingest.ipc)")
else:
    with open(p_ipc, encoding="utf-8") as fh:
        rd_ipc = csv.DictReader(fh)
        campos_ipc = rd_ipc.fieldnames or []
        filas_ipc = list(rd_ipc)
    for col in ("periodo", "vivienda", "alquiler", "electricidad", "gas"):
        check(col in campos_ipc, f"ipc-vivienda.csv: falta la columna '{col}'")
    check(len(filas_ipc) >= 6, f"ipc-vivienda.csv: solo {len(filas_ipc)} filas (¿ingesta IPC?)")
    _ult = next((r for r in reversed(filas_ipc) if r.get("vivienda")), None)
    check(_ult is not None, "ipc-vivienda.csv: sin dato de 'vivienda'")
    if _ult:
        try:
            float(_ult["vivienda"])
        except ValueError:
            FALLOS.append(f"ipc-vivienda.csv: 'vivienda' no numérico: {_ult['vivienda']!r}")
    if os.path.exists(html_p):
        check('id="inflacion"' in page,
              "la portada no incluye la sección «Inflación residencial» (id=inflacion)")
        check("grupo 04" in page, "la sección de inflación no menciona el grupo 04")

# ---------------------------------------------------------------------------
# 14. Alquiler SERPAVI/MIVAU por municipio (contratos, no oferta)
# ---------------------------------------------------------------------------
p_serp = os.path.join(WEB, "data", "alquiler-serpavi.csv")
if not os.path.exists(p_serp):
    OMITIDO.append("web/data/alquiler-serpavi.csv (generado; requiere ingest.serpavi)")
else:
    with open(p_serp, encoding="utf-8") as fh:
        _rd_serp = csv.DictReader(fh)
        _campos_serp = _rd_serp.fieldnames or []
        _filas_serp = list(_rd_serp)
    for col in ("codigo_ine", "municipio", "eur_m2", "anio"):
        check(col in _campos_serp, f"alquiler-serpavi.csv: falta '{col}'")
    check(len(_filas_serp) >= 100, f"alquiler-serpavi.csv: solo {len(_filas_serp)} filas")
    _vals = [float(r["eur_m2"]) for r in _filas_serp if r.get("eur_m2")]
    check(bool(_vals) and 1 < min(_vals) and max(_vals) < 40,
          f"alquiler-serpavi.csv: €/m² fuera de rango plausible: {_vals and (min(_vals), max(_vals))}")
    if os.path.exists(html_p):
        check('id="alquiler"' in page, "la portada no incluye la sección de alquiler SERPAVI")

# ---------------------------------------------------------------------------
# 15. Contrato de ingesta: la suma de CCAA debe cuadrar con el nacional
# ---------------------------------------------------------------------------
def _sum_csv(did, col):
    p = os.path.join(WEB, "data", did + ".csv")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return sum(float(r[col]) for r in csv.DictReader(fh) if r.get(col))


_eh = _sum_csv("ejecuciones-hipotecarias-ccaa", "ejecuciones")
_pn = os.path.join(WEB, "data", "ejecuciones-hipotecarias-nacional.csv")
if _eh is not None and os.path.exists(_pn):
    with open(_pn, encoding="utf-8") as fh:
        _nac = list(csv.DictReader(fh))
    if _nac:
        _last = float(_nac[-1]["ejecuciones"])
        check(abs(_eh - _last) <= 1, f"EH: suma CCAA={_eh} != nacional={_last} ({_nac[-1].get('anio')})")
else:
    OMITIDO.append("ejecuciones (nacional/CCAA) para el contrato de suma")

_lz = _sum_csv("lanzamientos-ccaa", "lanzamientos")
_pc = os.path.join(WEB, "data", "lanzamientos-cronologia.csv")
if _lz is not None and os.path.exists(_pc):
    with open(_pc, encoding="utf-8") as fh:
        _cron = list(csv.DictReader(fh))
    if _cron:
        _last = float(_cron[-1]["lanzamientos"])
        check(abs(_lz - _last) <= 1,
              f"LZ: suma CCAA={_lz} != nacional {_cron[-1].get('periodo')}={_last}")
else:
    OMITIDO.append("lanzamientos (cronología/CCAA) para el contrato de suma")

_vut = _sum_csv("viviendas-turisticas-ccaa", "viviendas_turisticas")
if _vut is not None and os.path.exists(json_latest):
    _v = json.load(open(json_latest, encoding="utf-8"))["indicadores"].get("vut", {}).get("valor")
    if _v:
        check(abs(_vut - _v) <= 1, f"VUT: suma CCAA={_vut} != nacional={_v}")
else:
    OMITIDO.append("viviendas-turisticas-ccaa/latest.json para el contrato de suma")

# ---------------------------------------------------------------------------
# 16. Compraventas (ETDP): suma CCAA = nacional + sección
# ---------------------------------------------------------------------------
_cv = _sum_csv("compraventas-ccaa", "compraventas")
_pcv = os.path.join(WEB, "data", "compraventas-nacional.csv")
if _cv is not None and os.path.exists(_pcv):
    with open(_pcv, encoding="utf-8") as fh:
        _cvn = list(csv.DictReader(fh))
    if _cvn:
        _last = float(_cvn[-1]["compraventas"])
        check(abs(_cv - _last) <= 1,
              f"Compraventas: suma CCAA={_cv} != nacional {_cvn[-1].get('periodo')}={_last}")
    if os.path.exists(html_p):
        check('id="compraventas"' in page, "la portada no incluye la sección de compraventas")
else:
    OMITIDO.append("compraventas (nacional/CCAA) para el contrato de suma")

# ---------------------------------------------------------------------------
# 17. Hipotecas constituidas de vivienda (HPT)
# ---------------------------------------------------------------------------
p_hpt = os.path.join(WEB, "data", "hipotecas-nacional.csv")
if not os.path.exists(p_hpt):
    OMITIDO.append("web/data/hipotecas-nacional.csv (generado; requiere ingest_hpt)")
else:
    with open(p_hpt, encoding="utf-8") as fh:
        _hpt = list(csv.DictReader(fh))
    check(len(_hpt) >= 6, f"hipotecas-nacional.csv: solo {len(_hpt)} filas")
    _hv = [float(r["hipotecas"]) for r in _hpt if r.get("hipotecas")]
    check(bool(_hv) and 1000 < max(_hv) < 200000,
          f"hipotecas-nacional.csv: valor fuera de rango plausible: {_hv and max(_hv)}")
    if os.path.exists(html_p):
        check('id="hipotecas"' in page, "la portada no incluye la sección de hipotecas constituidas")

# ---------------------------------------------------------------------------
# 18. Metadatos (datapackage.json) + historial de cambios (changelog.json)
# ---------------------------------------------------------------------------
_pdp = os.path.join(WEB, "data", "datapackage.json")
if not os.path.exists(_pdp):
    OMITIDO.append("web/data/datapackage.json (generado)")
else:
    try:
        _dp = json.load(open(_pdp, encoding="utf-8"))
        check(bool(_dp.get("resources")), "datapackage.json sin recursos")
        for _r in _dp.get("resources", []):
            check(all(k in _r for k in ("name", "path", "hash", "schema")),
                  f"datapackage.json: recurso incompleto {_r.get('name')!r}")
    except ValueError as _e:
        FALLOS.append(f"datapackage.json no es JSON válido: {_e}")
_pch = os.path.join(WEB, "data", "changelog.json")
if not os.path.exists(_pch):
    OMITIDO.append("web/data/changelog.json (lo escribe regen_publicar.sh)")

# ---------------------------------------------------------------------------
# 19. Zonas de mercado residencial tensionado (Ley 12/2023): fichero + sección
# ---------------------------------------------------------------------------
_zmf = os.path.join(ROOT, "data", "zmrt.json")
if not os.path.exists(_zmf):
    OMITIDO.append("data/zmrt.json (curado)")
else:
    try:
        _zm = json.load(open(_zmf, encoding="utf-8"))
        check(bool(_zm.get("declarantes_acumulado")), "zmrt.json: sin 'declarantes_acumulado'")
        check(bool(_zm.get("ultima_resolucion", {}).get("url")), "zmrt.json: sin resolución BOE enlazada")
    except ValueError as _e:
        FALLOS.append(f"zmrt.json no es JSON válido: {_e}")
    if os.path.exists(html_p):
        check('id="zmrt"' in page, "la portada no incluye la sección de zonas tensionadas")

# ---------------------------------------------------------------------------
# 20. páginas por CCAA + RSS de cambios
# ---------------------------------------------------------------------------
_ccdir = os.path.join(WEB, "ccaa")
if os.path.isdir(_ccdir):
    _ncc = len([x for x in os.listdir(_ccdir) if x.endswith(".html") and x != "index.html"])
    check(_ncc >= 15, f"pocas páginas por CCAA: {_ncc}")
    check(os.path.exists(os.path.join(_ccdir, "index.html")), "falta ccaa/index.html")
    if os.path.exists(html_p):
        check('href="/ccaa/' in page, "la portada no enlaza las páginas por CCAA")
else:
    OMITIDO.append("web/ccaa/")
_rss = os.path.join(WEB, "cambios.xml")
if os.path.exists(_rss):
    try:
        import xml.dom.minidom as _md
        _md.parse(_rss)
        check("Observatorio de la vivienda" in open(_rss, encoding="utf-8").read(),
              "cambios.xml sin título")
    except Exception as _e:
        FALLOS.append(f"cambios.xml no es XML válido: {_e}")
else:
    OMITIDO.append("web/cambios.xml")

if FALLOS:
    print(f"FALLOS ({len(FALLOS)}):", file=sys.stderr)
    for f in FALLOS:
        print("  -", f, file=sys.stderr)
    sys.exit(1)
if OMITIDO:
    print(f"OMITIDOS ({len(OMITIDO)} checks no ejecutados por falta de artefacto):")
    for o in OMITIDO:
        print("  -", o)
print(f"OK · {len(reg.get('normas') or [])} normas registradas · "
      f"vocabulario {sorted(vocab)} · CSV con estado")