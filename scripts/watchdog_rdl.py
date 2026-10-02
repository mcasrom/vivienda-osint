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
3. Avisa por Telegram (una vez, no en cada pasada) y regenera la web + tests.

Precedentes que fijan el formato esperado del título (verificados en el BOE):
  BOE-A-2023-8221 «Resolución ... por la que se ordena la publicación del Acuerdo
  de convalidación del Real Decreto-ley 2/2023 ...»
  BOE-A-2026-4667 idem, con «Acuerdo de derogación del Real Decreto-ley 2/2026».

Uso:
  venv/bin/python scripts/watchdog_rdl.py            # comprueba y avisa
  venv/bin/python scripts/watchdog_rdl.py --aplicar  # además actualiza el registro
  venv/bin/python scripts/watchdog_rdl.py --dias 7   # ventana de búsqueda (def. 21)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMAS = os.path.join(ROOT, "data", "normas.json")
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
    print(msg, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"[{date.today().isoformat()}] {msg}\n")
    except OSError as e:  # noqa: BLE001
        print(f"[watchdog] no se pudo escribir el log: {e}", file=sys.stderr)


def _sumario(d: date) -> ET.Element:
    req = urllib.request.Request(API % d.strftime("%Y%m%d"), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return ET.fromstring(r.read())


def buscar(rdl: str, desde: date, hasta: date) -> dict | None:
    """Resolución del Congreso sobre ese RDL en [desde, hasta], o None."""
    n, anio = rdl.split("/")
    for i in range((hasta - desde).days + 1):
        d = desde + timedelta(days=i)
        try:
            root = _sumario(d)
        except Exception as e:  # noqa: BLE001
            # un sumario que no se puede leer no es motivo para callarse el resto
            _log(f"[watchdog] {d.isoformat()} sumario no disponible ({type(e).__name__}: {e})")
            continue
        for item in root.iter("item"):
            titulo = (item.findtext("titulo") or "").strip()
            res = match_resolucion(titulo, rdl)
            if res is None:
                continue
            ident = (item.findtext("identificador") or "").strip()
            url = ""
            for tag in ("url_txt", "url_html", "url_pdf"):
                el = item.find(tag)
                if el is not None and el.text:
                    url = el.text.strip()
                    break
            return {"id": ident, "fecha": d.isoformat(), "titulo": titulo,
                    "url": url or f"https://www.boe.es/buscar/doc.php?id={ident}",
                    "estado": res["estado"]}
    return None


def _telegram(msg: str) -> bool:
    """Aviso al owner. Token/chat se leen del .env del radar (fuente ya existente)."""
    env = "/home/deploy/hybrid-fimi-radar/.env"
    try:
        for line in open(env, encoding="utf-8"):
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError as e:
        _log(f"[watchdog] sin .env para Telegram ({e})")
    token = os.environ.get("FIMI_TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("FIMI_OWNER_CHAT") or os.environ.get("FIMI_TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        _log("[watchdog] sin token/chat de Telegram: no se avisa (el log queda como aviso)")
        return False
    from urllib.request import Request
    data = json.dumps({"chat_id": chat, "text": msg}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        _log(f"[watchdog] Telegram fallo: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=21, help="días hacia atrás a buscar (def. 21)")
    ap.add_argument("--aplicar", action="store_true",
                    help="actualiza data/normas.json y regenera (por defecto solo avisa)")
    args = ap.parse_args()

    with open(NORMAS, encoding="utf-8") as fh:
        reg = json.load(fh)
    hoy = date.today()
    pendientes = [n for n in reg["normas"] if n.get("estado") == "en_votacion"]
    if not pendientes:
        _log(f"[watchdog] nada pendiente ({len(reg['normas'])} normas registradas)")
        return 0

    lineas, cambios = [], 0
    for n in pendientes:
        rdl = n["corta"].split()[-1]          # «RDL 26/2026» -> «26/2026»
        vot = n.get("votacion") or {}
        desde = date.fromisoformat(vot.get("fecha") or n["estado_fecha"])
        res = buscar(rdl, desde, hoy)
        if not res:
            _log(f"[watchdog] {n['id']} ({rdl}): sin resolución del Congreso desde {desde.isoformat()}")
            continue
        cambios += 1
        _log(f"[watchdog] {n['id']} ({rdl}): {res['estado']} · {res['id']} · {res['fecha']}")
        lineas.append(f"{n['corta']}: {res['estado']} ({res['id']}, {res['fecha']})")
        if args.aplicar:
            n["estado"] = res["estado"]
            n["estado_fecha"] = res["fecha"]
            n["estado_nota"] = f"Acuerdo del Congreso: {res['id']}."
            n["resultado"] = f"Congreso: acuerdo de {res['estado']} ({res['id']})."
            n["resultado_fecha"] = res["fecha"]
            n["resultado_url"] = res["url"]
        else:
            lineas[-1] += "\n   " + res["url"]

    if not cambios:
        _log("[watchdog] sin novedades: la web sigue diciendo «pendiente» y es lo correcto")
        return 0

    cuerpo = ("Resolución del Congreso publicada para el RDL de vivienda.\n"
              + "\n".join(lineas))
    if args.aplicar:
        reg["actualizado"] = hoy.isoformat()
        with open(NORMAS, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        _log("[watchdog] registro actualizado; regenerando y comprobando")
        for cmd in ([sys.executable, os.path.join(ROOT, "gen", "gen_vivienda.py")],
                    [sys.executable, os.path.join(ROOT, "tests", "test_datos.py")]):
            r = subprocess.run(cmd, capture_output=True, text=True)
            _log(f"[watchdog] {' '.join(cmd[-1:])} rc={r.returncode} {r.stdout.strip()[-300:]}")
            if r.returncode != 0:
                _log(f"[watchdog] ERROR: {r.stderr.strip()[-600:]}")
                _telegram(f"Watchdog vivienda: la regeneración falló (rc={r.returncode}). "
                          f"Revisa el log del server.")
                return 1
    else:
        cuerpo += "\n\nNo se aplicó nada todavía (--aplicar para escribirlo)."
    _telegram(cuerpo)
    _log(f"[watchdog] notificado ({cambios} norma/s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())