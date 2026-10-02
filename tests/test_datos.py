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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLOS: list[str] = []

# Tabla canónica: todo nombre de CCAA publicado debe salir de aquí.
CCAA_CSV = ("ejecuciones-hipotecarias-ccaa", "viviendas-turisticas-ccaa", "lanzamientos-ccaa")


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

con = sqlite3.connect(os.path.join(ROOT, "data", "vivienda.db"))
en_boe = {r[0]: r[1] for r in con.execute("SELECT id, fecha FROM boe")}

for n in reg.get("normas") or []:
    nid = n.get("id", "?")
    # 2. existe en la tabla boe y la fecha coincide
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
csv_p = os.path.join(ROOT, "web", "data", "boe-vivienda.csv")
check(os.path.exists(csv_p), "falta web/data/boe-vivienda.csv")
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

# ---------------------------------------------------------------------------
# 8. Nombres de CCAA canónicos, sin duplicados, con los huecos declarados
# ---------------------------------------------------------------------------
for did in CCAA_CSV:
    p_csv = os.path.join(ROOT, "web", "data", did + ".csv")
    if not os.path.exists(p_csv):
        FALLOS.append(f"falta web/data/{did}.csv")
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
html_p = os.path.join(ROOT, "web", "index.html")
check(os.path.exists(html_p), "falta web/index.html")
if os.path.exists(html_p):
    page = open(html_p, encoding="utf-8").read()
    bloques = re.findall(
        r"Ver el detalle completo · (\d+) comunidades autónomas</summary>"
        r"<table[^>]*><tbody>(.*?)</tbody>", page, re.S)
    check(len(bloques) == len(CCAA_CSV),
          f"se esperaban {len(CCAA_CSV)} bloques de detalle CCAA en la página y hay {len(bloques)}")
    # orden en la página: ejecuciones (EH), lanzamientos (LZ), viviendas turísticas (VUT)
    orden_pagina = ("ejecuciones-hipotecarias-ccaa", "lanzamientos-ccaa", "viviendas-turisticas-ccaa")
    for (anunciado, cuerpo), did in zip(bloques, orden_pagina):
        filas = re.findall(r"<tr><td>([^<]+)</td><td class=\"num\">([^<]*)</td></tr>", cuerpo)
        check(len(filas) == int(anunciado),
              f"{did}: la página anuncia {anunciado} filas y pinta {len(filas)}")
        with open(os.path.join(ROOT, "web", "data", did + ".csv"), encoding="utf-8") as fh:
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
json_latest = os.path.join(ROOT, "web", "data", "latest.json")
check(os.path.exists(json_latest), "falta web/data/latest.json")
if os.path.exists(json_latest) and os.path.exists(html_p):
    ind = json.load(open(json_latest, encoding="utf-8"))["indicadores"]
    tarjetas = re.findall(
        r'<div class="ind"><div class="v">([^<]+)<small>([^<]*)</small></div>'
        r'<div class="t ([^"]*)">([^<]*)</div>'
        r'<div class="f">([^<]+)<br><span class="mut">([^<]*)</span></div>', page)
    CLAVE = {"IPV (compraventa)": "ipv", "IPVA (alquiler)": "ipva",
             "lanzamientos": "lz", "ejecuciones": "eh"}
    # la portada lleva 4 tarjetas; la VUT se publica como ranking, no como indicador
    check(len(tarjetas) == len(CLAVE),
          f"la portada tiene {len(tarjetas)} tarjetas y se esperan {len(CLAVE)}")
    check(set(ind) - set(CLAVE.values()) == {"vut"},
          f"latest.json publica {sorted(set(ind) - set(CLAVE.values()))} y solo la VUT va como ranking")
    for valor, _unidad, cls, tend_txt, fuente, per_txt in tarjetas:
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

if FALLOS:
    print(f"FALLOS ({len(FALLOS)}):", file=sys.stderr)
    for f in FALLOS:
        print("  -", f, file=sys.stderr)
    sys.exit(1)
print(f"OK · {len(reg.get('normas') or [])} normas registradas · "
      f"vocabulario {sorted(vocab)} · CSV con estado")