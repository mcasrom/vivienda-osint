"""Watchdog del RDL 26/2026 y 27/2026: ¿publicó el Congreso el acuerdo?

Por qué existe: el 2-oct-2026 el Congreso vota la convalidación o derogación de
los RDL 26/2026 y 27/2026. La ficha de la web dice «pendiente» hasta que exista
la fuente oficial. El riesgo real de un estado que depende de un evento externo es
**envejecer en silencio**: nadie se entera de que la fuente apareció (regla 24:
el silencio es indistinguible del fallo).

Qué hace, en orden:
1. Por cada norma en `en_votacion`, busca en el BOE (API abierta, sumarios
   diarios) desde el día de la votación hasta hoy una **Resolución del Congreso
   de los Diputados** cuyo título mencione ese Real Decreto-ley.
2. Si aparece y dice «convalidación» → `estado: convalidada`; si dice
   «derogación» → `estado: derogada`. Registra `resultado`, `resultado_fecha` y la
   URL oficial. **No se anticipa**: si no hay resolución, no cambia nada.
3. Avisa por Telegram **una sola vez por resolución** (dedup en
   `data/watchdog_estado.json`) y comprobando el rc del envío (no se marca como
   notificado si falla: la siguiente pasada reintenta). Con `--aplicar`, además
   actualiza el registro (escritura atómica) y regenera la web **por staging**
   (scripts/regen_publicar.sh: web_tmp + tests, y swap solo si pasan).

Precedentes que fijan el formato esperado del título (verificados en el BOE):
  BOE-A-2023-8221 «Resolución ... por la que se ordena la publicación del Acuerdo
  de convalidación del Real Decreto-ley 2/2023 ...»
  BOE-A-2026-4667 idem, con «Acuerdo de derogación del Real Decreto-ley 2/2026».

Uso:
  venv/bin/python scripts/watchdog_rdl.py            # comprueba y avisa (una vez por resolución)
  venv/bin/python scripts/watchdog_rdl.py --aplicar  # además actualiza registro + regenera
  venv/bin/python scripts/watchdog_rdl.py --dias 7   # ventana de búsqueda (def. 21)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from ingest.boe import _es_domingo  # noqa: E402  (causa raíz del 404 dominical silencioso)

NORMAS = os.path.join(ROOT, "data", "normas.json")
ESTADO_F = os.path.join(ROOT, "data", "watchdog_estado.json")     # qué se avisó (dedup)
CACHE_SUM = os.path.join(ROOT, "data", "watchdog_sumarios.json")    # sumarios ya leídos
LOG = os.path.join(ROOT, "logs", "watchdog_rdl.log")
API = "https://www.boe.es/datosabiertos/api/boe/sumario/%s"
UA = {"User-Agent": "vivienda-osint/0.1 (+pruebapublica.com)", "Accept": "application/xml"}

# El acuerdo del Congreso llega como «Resolución ... del Congreso de los Diputados,
# por la que se ordena la publicación del Acuerdo de convalidación|derogación del
# Real Decreto-ley N/AAAA». Nos interesan esas dos palabras y el número del RDL.
ES_CONGRESO = re.compile(r"congreso de los diputados", re.I)
ES_ACUERDO = re.compile(r"acuerdo de (convalidaci[oó]n|derogaci[oó]n)", re.I)
RDL_EN_TITULO = re.compile(r"real decreto-ley\s*(\d+)\s*/\s*(\d{4})", re.I)


def match_resolucion(titulo: str, rdl: str | None = None):
    """Devuelve el dict que `buscar` necesita si `titulo` es la resolución del
    Congreso sobre `rdl`, o None. Cada regex tiene una sola responsabilidad; la
    composición exige las tres (Congreso + acuerdo + nº de RDL), así que un título
    suelto («Acuerdo de convalidación del presupuesto») no casa por sí solo.
    `rdl` en formato «26/2026»; si es None, casa cualquier RDL (no usado en busca)."""
    if not titulo or not ES_CONGRESO.search(titulo) or not ES_ACUERDO.search(titulo):
        return None
    m = RDL_EN_TITULO.search(titulo)
    if not m:
        return None
    if rdl is not None:
        n, anio = rdl.split("/")
        if m.group(1) != n or m.group(2) != anio:
            return None
    tipo = "convalidada" if re.search(r"convalidaci[oó]n", titulo, re.I) else "derogada"
    return {"numero": m.group(1), "anio": m.group(2), "estado": tipo}


def _log(msg: str) -> None:
    """Log a fichero + stdout, con hora (antes solo fecha: no se veía cuándo pasaba)."""
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(msg, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{marca}] {msg}\n")
    except OSError as e:  # noqa: BLE001
        print(f"[watchdog] no se pudo escribir el log: {e}", file=sys.stderr)


def _escritura_atomica(path: str, data) -> None:
    """Nunca deja un JSON a medias si el proceso muere a mitad de escritura."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def _sumario(d: date) -> ET.Element:
    req = urllib.request.Request(API % d.strftime("%Y%m%d"), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return ET.fromstring(r.read())


def _items(d: date) -> list[dict]:
    """Sumario del día filtrado a resoluciones del Congreso, con caché (a partir de
    hoy se relee en cada pasada: un 404 de domingo NO se cachea como vacío definitivo
    y el BOE puede publicar tarde por la mañana)."""
    cache = {}
    if os.path.exists(CACHE_SUM):
        try:
            cache = json.load(open(CACHE_SUM, encoding="utf-8"))
        except ValueError:
            cache = {}
    clave = d.isoformat()
    if clave in cache.get("dias", {}) and d < date.today():
        return cache["dias"][clave]
    try:
        root = _sumario(d)
    except urllib.error.HTTPError as e:
        if e.code == 404 and _es_domingo(d):
            _log(f"[watchdog] {d.isoformat()} domingo sin sumario (esperado)")
            return []
        _log(f"[watchdog] {d.isoformat()} sumario no disponible (HTTP {e.code})")
        return []
    except Exception as e:  # noqa: BLE001
        _log(f"[watchdog] {d.isoformat()} sumario no disponible ({type(e).__name__}: {e})")
        return []
    out = []
    for item in root.iter("item"):
        titulo = (item.findtext("titulo") or "").strip()
        res = match_resolucion(titulo, None)
        if res is None:
            continue
        ident = (item.findtext("identificador") or "").strip()
        url = ""
        for tag in ("url_txt", "url_html", "url_pdf"):
            el = item.find(tag)
            if el is not None and el.text:
                url = el.text.strip()
                break
        out.append({"id": ident, "titulo": titulo,
                    "url": url or f"https://www.boe.es/buscar/doc.php?id={ident}",
                    "numero": res["numero"], "anio": res["anio"], "estado": res["estado"]})
    if d < date.today():    # solo los días ya cerrados son inmutables
        cache.setdefault("dias", {})[clave] = out
        _escritura_atomica(CACHE_SUM, cache)
    return out


def buscar(rdl: str, desde: date, hasta: date) -> dict | None:
    """Resolución del Congreso sobre ese RDL en [desde, hasta], o None."""
    n, anio = rdl.split("/")
    for i in range((hasta - desde).days + 1):
        d = desde + timedelta(days=i)
        for it in _items(d):
            if it["numero"] == n and it["anio"] == anio:
                return {"id": it["id"], "fecha": d.isoformat(), "titulo": it["titulo"],
                        "url": it["url"], "estado": it["estado"]}
    return None


def _enviar(msg: str) -> bool:
    """Envío a Telegram en .env propio de vivienda (aviso.py); el rc decide el dedup."""
    from aviso import enviar
    ok = enviar(msg)
    if not ok:
        _log("[watchdog] Telegram no confirmó: no se marca como notificado (reintento)")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=21, help="días hacia atrás a buscar (def. 21)")
    ap.add_argument("--aplicar", action="store_true",
                    help="actualiza data/normas.json y regenera por staging (por defecto solo avisa)")
    args = ap.parse_args()

    try:
        reg = json.load(open(NORMAS, encoding="utf-8"))
    except (OSError, ValueError) as e:
        _log(f"[watchdog] no se pudo leer {NORMAS}: {e}")
        return 1
    hoy = date.today()
    pendientes = [n for n in reg["normas"] if n.get("estado") == "en_votacion"]
    if not pendientes:
        _log(f"[watchdog] nada pendiente ({len(reg['normas'])} normas registradas)")
        return 0

    estado = {}
    if os.path.exists(ESTADO_F):
        try:
            estado = json.load(open(ESTADO_F, encoding="utf-8"))
        except ValueError:
            estado = {}
    notificadas = set(estado.get("notificadas", []))

    novedades: list[tuple[str, str, dict]] = []   # (corta, clave, res)
    aplicadas: list[dict] = []
    for n in pendientes:
        rdl = n["corta"].split()[-1]          # «RDL 26/2026» -> «26/2026»
        vot = n.get("votacion") or {}
        desde = date.fromisoformat(vot.get("fecha") or n["estado_fecha"])
        res = buscar(rdl, desde, hoy)
        if not res:
            _log(f"[watchdog] {n['id']} ({rdl}): sin resolución del Congreso desde {desde.isoformat()}")
            continue
        clave = f"{rdl}:{res['id']}"
        _log(f"[watchdog] {n['id']} ({rdl}): {res['estado']} · {res['id']} · {res['fecha']}"
             + (" (ya avisado)" if clave in notificadas else " (NUEVO)"))
        if clave not in notificadas:
            novedades.append((n["corta"], clave, res))
        if args.aplicar:
            n["estado"] = res["estado"]
            n["estado_fecha"] = res["fecha"]
            n["estado_nota"] = f"Acuerdo del Congreso: {res['id']}."
            n["resultado"] = f"Congreso: acuerdo de {res['estado']} ({res['id']})."
            n["resultado_fecha"] = res["fecha"]
            n["resultado_url"] = res["url"]
            n["resultado_numero"] = res.get("numero", "")
            n["resultado_anio"] = res.get("anio", "")
            aplicadas.append(n)

    if not novedades and not aplicadas:
        _log("[watchdog] sin novedades: la web sigue diciendo «pendiente» y es lo correcto")
        return 0

    escrito_normas = False
    if aplicadas:
        reg["actualizado"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        _escritura_atomica(NORMAS, reg)
        escrito_normas = True
        _log(f"[watchdog] registro actualizado ({len(aplicadas)} norma/s)")

    # Aviso SOLO de lo nuevo, y SOLO se marca como notificado si el envío va bien.
    if novedades:
        lineas = "".join(
            f"\n• {corta}: {res['estado']} ({res['id']}, {res['fecha']})\n   {res['url']}"
            for corta, _clave, res in novedades)
        cuerpo = ("Resolución del Congreso publicada para el RDL de vivienda:"
                  + lineas)
        if not args.aplicar:
            cuerpo += "\n\nNo se aplicó nada todavía (--aplicar para escribirlo)."
        if _enviar(cuerpo):
            notificadas |= {clave for _c, clave, _r in novedades}
            state = {"notificadas": sorted(notificadas)}
            _escritura_atomica(ESTADO_F, state)
            _log(f"[watchdog] notificado ({len(novedades)} nueva/s)")
        else:
            return 1

    if escrito_normas:
        _log("[watchdog] regenerando por staging (web_tmp + tests, swap solo si pasan)")
        r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "regen_publicar.sh")],
                           capture_output=True, text=True)
        _log(f"[watchdog] regen_publicar rc={r.returncode}")
        if r.returncode != 0:
            _log(f"[watchdog] regen_publicar stderr: {r.stderr.strip()[-500:]}")
            _enviar("Watchdog vivienda: la regeneración por staging falló. Revisa logs/test.log.")
            return 1
        _log("[watchdog] web regenerada y publicada (tests OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())