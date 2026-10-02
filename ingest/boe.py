"""Ingesta BOE: decretos-ley / disposiciones sobre vivienda del sumario diario.

Fuente: https://www.boe.es/datosabiertos/api/boe/sumario/YYYYMMDD (requiere Accept: application/xml).
Guarda los items que mencionan vivienda/alquiler/desahucio/... en data/vivienda.db.
"""
from __future__ import annotations
import os, re, sqlite3, urllib.error, urllib.request, xml.etree.ElementTree as ET
from datetime import date, timedelta

API = "https://www.boe.es/datosabiertos/api/boe/sumario/%s"
KW = re.compile(r"vivienda|alquil|arrendamiento|desahucio|\blanzamiento|hipotec|suelo|vpo|asequible|funci[oó]n social", re.I)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")


def _con():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS boe(
        id TEXT PRIMARY KEY, fecha TEXT, titulo TEXT, url TEXT, departamento TEXT)""")
    cols = [r[1] for r in c.execute("PRAGMA table_info(boe)").fetchall()]
    for col in ("seccion", "ambito"):
        if col not in cols:
            c.execute(f"ALTER TABLE boe ADD COLUMN {col} TEXT")
    return c


def _fetch(d: date) -> bytes:
    req = urllib.request.Request(API % d.strftime("%Y%m%d"),
                                 headers={"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)",
                                          "Accept": "application/xml"})
    return urllib.request.urlopen(req, timeout=30).read()


def _ambito(dept: str) -> str:
    u = dept.upper()
    if u.startswith("COMUNIDAD AUT") or "COMUNIDAD AUT" in u:
        return "autonómico"
    if "ADMINISTRACIÓN LOCAL" in u or "AYUNTAMIENTO" in u or "DIPUTACIÓN" in u:
        return "local"
    return "estatal"


def _parse(xml: bytes, d: date):
    """Solo disposiciones generales (sección I): normas, no anuncios ni contratos."""
    root = ET.fromstring(xml)
    out = []
    for sec in root.iter("seccion"):
        if (sec.attrib.get("codigo") or "").strip() != "1":
            continue
        for dept in sec.iter("departamento"):
            dnom = (dept.attrib.get("nombre") or "").strip()
            for item in dept.iter("item"):
                titulo = (item.findtext("titulo") or "").strip()
                if not titulo or not KW.search(titulo):
                    continue
                ident = (item.findtext("identificador") or "").strip()
                url = ""
                for tag in ("url_txt", "url_html", "url_pdf"):
                    el = item.find(tag)
                    if el is not None and el.text:
                        url = el.text.strip()
                        break
                out.append({"id": ident, "fecha": d.isoformat(), "titulo": titulo,
                            "url": url, "departamento": dnom, "seccion": "1",
                            "ambito": _ambito(dnom)})
    return out



def _es_domingo(d: date) -> bool:
    """El BOE no publica sumario los domingos: un 404 ahí es lo normal, no un fallo."""
    return d.weekday() == 6

def ingest(dias: int = 21) -> int:
    c = _con()
    n = 0
    # reingest autoritativo: la tabla se reconstruye desde la ventana de N días
    c.execute("DELETE FROM boe")
    hoy = date.today()
    for i in range(dias):
        d = hoy - timedelta(days=i)
        try:
            items = _parse(_fetch(d), d)
        except urllib.error.HTTPError as e:
            # domingo (o festivo) sin sumario: esperado. El resto de códigos, no.
            if e.code == 404 and _es_domingo(d):
                continue
            print(f"[boe] {d} sumario no disponible (HTTP {e.code})", flush=True)
            continue
        except Exception as e:  # noqa: BLE001
            print(f"[boe] {d} sin sumario ({type(e).__name__}: {e})", flush=True)
            continue
        for it in items:
            cur = c.execute("INSERT OR REPLACE INTO boe(id,fecha,titulo,url,departamento,seccion,ambito) "
                            "VALUES(?,?,?,?,?,?,?)",
                            (it["id"] or it["titulo"][:40], it["fecha"], it["titulo"], it["url"],
                             it["departamento"], it["seccion"], it["ambito"]))
            n += cur.rowcount
    c.commit()
    return n


if __name__ == "__main__":
    print(f"[boe] nuevas disposiciones de vivienda: {ingest()}")
