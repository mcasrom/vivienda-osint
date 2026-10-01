"""Ingesta BOE: decretos-ley / disposiciones sobre vivienda del sumario diario.

Fuente: https://www.boe.es/datosabiertos/api/boe/sumario/YYYYMMDD (requiere Accept: application/xml).
Guarda los items que mencionan vivienda/alquiler/desahucio/... en data/vivienda.db.
"""
from __future__ import annotations
import os, re, sqlite3, urllib.request, xml.etree.ElementTree as ET
from datetime import date, timedelta

API = "https://www.boe.es/datosabiertos/api/boe/sumario/%s"
KW = re.compile(r"vivienda|alquil|arrendamiento|desahucio|lanzamiento|hipotec|suelo|vpo|asequible|funci[oó]n social", re.I)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")


def _con():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS boe(
        id TEXT PRIMARY KEY, fecha TEXT, titulo TEXT, url TEXT, departamento TEXT)""")
    return c


def _fetch(d: date) -> bytes:
    req = urllib.request.Request(API % d.strftime("%Y%m%d"),
                                 headers={"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)",
                                          "Accept": "application/xml"})
    return urllib.request.urlopen(req, timeout=30).read()


def _parse(xml: bytes, d: date):
    root = ET.fromstring(xml)
    out = []
    for item in root.iter("item"):
        titulo = (item.findtext("titulo") or "").strip()
        if not titulo or not KW.search(titulo):
            continue
        xml_el = item.find("identificador")
        ident = (xml_el.text or "").strip() if xml_el is not None else ""
        url = ""
        for tag in ("url_txt", "url_html", "url_pdf"):
            el = item.find(tag)
            if el is not None and el.text:
                url = el.text.strip()
                break
        dept = ""
        p = item
        # sube por padres buscando el departamento (ET no da parent; se busca por estructura)
        out.append({"id": ident, "fecha": d.isoformat(), "titulo": titulo, "url": url, "departamento": dept})
    return out


def ingest(dias: int = 21) -> int:
    c = _con()
    n = 0
    hoy = date.today()
    for i in range(dias):
        d = hoy - timedelta(days=i)
        try:
            items = _parse(_fetch(d), d)
        except Exception as e:  # noqa: BLE001
            print(f"[boe] {d} sin sumario ({type(e).__name__})", flush=True)
            continue
        for it in items:
            cur = c.execute("INSERT OR IGNORE INTO boe(id,fecha,titulo,url,departamento) VALUES(?,?,?,?,?)",
                            (it["id"] or it["titulo"][:40], it["fecha"], it["titulo"], it["url"], it["departamento"]))
            n += cur.rowcount
    c.commit()
    return n


if __name__ == "__main__":
    print(f"[boe] nuevas disposiciones de vivienda: {ingest()}")
