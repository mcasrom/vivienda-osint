"""Observatorio de la vivienda — página estática (aproxima la maqueta, cívico y neutral).

Estructura: Indicadores · IPV · Alquiler · Mapa de calor provincial · Comparador España↔región ·
Calendario · Registro de medidas · Método y límites. Sin puntuaciones compuestas.
"""
from __future__ import annotations
import os, sys, sqlite3, html, json, csv, math, hashlib
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import boe as boeing, via, ine, cgpj, territorios, frescura, ipc, serpavi  # noqa: E402

# Directorio de salida: por defecto web/ (público); el cron/publicar por staging
# usa web_tmp/ y solo intercambia si el contrato de datos pasa (regla: publicar
# después de comprobar, no antes). --out se valida contra ROOT en __main__.
_OUT_DIR_DEF = "web"   # relativo a ROOT
OUT_DIR = os.path.join(ROOT, _OUT_DIR_DEF)
OUT = os.path.join(OUT_DIR, "index.html")
DATA_DIR = os.path.join(OUT_DIR, "data")
E = html.escape

# Versión del microservicio (una sola fuente: se muestra en el footer de todas
# las páginas generadas y debe coincidir con el tag/la release del repo).
VERSION = "0.1.0"

# --- Registro de normas: estado y fechas (FUENTE ÚNICA) -------------------
# El estado vive en data/normas.json y solo se cambia con fuente oficial (BOE o
# Resolución del Congreso). No se infiere ni se anticipa. Los títulos oficiales
# completos NO se duplican aquí: se leen de la tabla `boe` (ingest/boe.py).
NORMAS_F = os.path.join(ROOT, "data", "normas.json")
with open(NORMAS_F, encoding="utf-8") as _fh:
    _REGN = json.load(_fh)
NORMAS = {n["id"]: n for n in _REGN["normas"]}
MED_IDS = set(NORMAS)
MARCO = _REGN["marco"]
# Zonas de mercado residencial tensionado (Ley 12/2023, art. 18): fichero curado
ZMRT_F = os.path.join(ROOT, "data", "zmrt.json")
try:
    with open(ZMRT_F, encoding="utf-8") as _fh:
        ZMRT = json.load(_fh)
except (OSError, ValueError):
    ZMRT = {}
ESTADO_TXT = {
    "publicada": "Publicada",
    "en_votacion": "Pendiente de convalidación o derogación",
    "convalidada": "Convalidada por el Congreso",
    "derogada": "Derogada por el Congreso",
}
DESENLACE_TXT = {
    "convalidada": "si se convalida, el Decreto-ley queda convalidado y mantiene su vigencia",
    "derogada": "si se deroga, el Decreto-ley queda derogado",
}
_MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fd(s):
    """Fecha ISO (datos) → 29-sep-2026 (texto de la página)."""
    try:
        d = date.fromisoformat(s)
    except (TypeError, ValueError):
        return s or ""
    return f"{d.day:02d}-{_MES[d.month - 1]}-{d.year}"

# Línea de tiempo: fecha de aprobación + etiqueta corta (el texto oficial va en la ficha).
MEDIDAS = [("2023-05-25", "Ley 12/2023 por el derecho a la vivienda",
            "https://www.boe.es/buscar/act.php?id=BOE-A-2023-12203")] + [
    (n["aprobacion"], f'{n["corta"]} — {n["resumen"]}',
     "https://www.boe.es/buscar/act.php?id=" + n["id"]) for n in _REGN["normas"]]
CALENDARIO = [
    ("16/10/2026", "CGPJ — lanzamientos del 2.º trimestre"),
    ("14/12/2026", "CGPJ — lanzamientos del 3.er trimestre"),
    ("Cada mes", "INE — compraventas inscritas e IRAV (el de agosto, 15/09)"),
]



BASE_JSON = os.path.join(ROOT, "data", "baseline_t0.json")


def congelar_baseline(ind):
    """Congela el snapshot t0 (una vez) y lo devuelve."""
    if os.path.exists(BASE_JSON):
        try:
            return json.load(open(BASE_JSON, encoding="utf-8"))
        except Exception:
            pass
    snap = {"fecha_t0": "2026-09-29", "creado": str(date.today()), "ind": ind}
    try:
        json.dump(snap, open(BASE_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    return snap


def _fmtv(tipo, v):
    if v is None:
        return "—"
    if tipo == "pct":
        return _pct(v)
    if tipo == "eur":
        return _eur(v)
    return f"{int(v):,}".replace(",", ".")


def _dlt(tipo, a, b):
    if a is None or b is None:
        return ""
    d = b - a
    if abs(d) < 1e-9:
        return "="
    s = "+" if d >= 0 else ""
    if tipo == "pct":
        return f"{s}{d:.1f} pp"
    if tipo == "eur":
        return f"{s}{d:.0f} €"
    return f"{s}{d:,.0f}".replace(",", ".")


PROV_INE = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería", "05": "Ávila", "06": "Badajoz",
    "07": "Baleares", "08": "Barcelona", "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "Coruña", "16": "Cuenca", "17": "Girona", "18": "Granada",
    "19": "Guadalajara", "20": "Gipuzkoa", "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga", "30": "Murcia",
    "31": "Navarra", "32": "Ourense", "33": "Asturias", "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra",
    "37": "Salamanca", "38": "S.C. Tenerife", "39": "Cantabria", "40": "Segovia", "41": "Sevilla", "42": "Soria",
    "43": "Tarragona", "44": "Teruel", "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia",
    "49": "Zamora", "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}
# Nombres de presentación (los de VIA/INE pueden variar; se normaliza por código).
PROV_DISP = {"15": "A Coruña", "38": "Santa Cruz de Tenerife"}
PROV_NAME2CODE = {v.strip().lower(): k for k, v in PROV_INE.items()}
PROV_NAME2CODE.update({"a coruña": "15", "santa cruz de tenerife": "38", "illes balears": "07",
                       "la rioja": "26", "valència": "46", "alacant": "03"})


def _prov(p, code):
    """Nombre canónico de provincia. Prioriza el código INE; si falta, el nombre."""
    c = (code or "").strip()
    if len(c) >= 2 and c[:2] in PROV_INE:
        return PROV_DISP.get(c[:2], PROV_INE[c[:2]])
    name = (p or "").strip()
    if name:
        k = PROV_NAME2CODE.get(name.lower())
        if k:
            return PROV_DISP.get(k, PROV_INE[k])
        return name
    return "Otras"


def _eur(v):
    return f"{v:,.0f} €".replace(",", ".") if v is not None else "—"


def _pct(v):
    return f"{v:+.1f} %".replace(".", ",") if v is not None else "—"


def _tendencia(serie):
    if len(serie) < 2:
        return "estable", ""
    d = serie[-1][1] - serie[-2][1]
    if d > 0.05:
        return "subiendo", "up"
    if d < -0.05:
        return "bajando", "down"
    return "estable", ""


def _etq_var(t):
    """Tendencia de una VARIACIÓN: no 'baja el precio', sino que la subida se modera."""
    return {"subiendo": "sube más", "bajando": "se modera", "estable": "estable"}.get(t, "")


def _etq_nivel(t):
    """Tendencia de un NIVEL (conteo): sube/baja el número."""
    return {"subiendo": "subiendo", "bajando": "bajando", "estable": "estable"}.get(t, "")


def _write_dataset(did, titulo, fuente, periodo, licencia, headers, records, datasets):
    """Escribe <did>.csv y <did>.json (UTF-8) y registra el catálogo."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, did + ".csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in records:
            w.writerow([r.get(h, "") for h in headers])
    with open(os.path.join(DATA_DIR, did + ".json"), "w", encoding="utf-8") as f:
        json.dump({"id": did, "titulo": titulo, "fuente": fuente, "periodo": periodo,
                   "licencia": licencia, "columnas": headers, "datos": records},
                  f, ensure_ascii=False, indent=1)
    datasets.append({"id": did, "titulo": titulo, "fuente": fuente,
                     "periodo": periodo, "licencia": licencia, "n": len(records),
                     "columnas": list(headers)})


def _descarga(did):
    """Enlaces de descarga CSV/JSON para una sección."""
    return (f'<p class="mut" style="font-size:.78rem;margin:8px 0 0">Descargar: '
            f'<a href="/data/{did}.csv">CSV</a> · <a href="/data/{did}.json">JSON</a></p>')




SOURCES = [
    ("INE · IPV", "Precio de compraventa de vivienda (variación anual)",
     "Índice de Precios de Vivienda", "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/80270",
     "Trimestral", "INE — reutilización permitida citando la fuente", "https://www.ine.es/"),
    ("INE · IPVA", "Índice de precios del alquiler (variación anual)",
     "Índice de Precios de Vivienda en Alquiler", "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/59056",
     "Anual (experimental, base fiscal)", "INE", "https://www.ine.es/"),
    ("INE · EH", "Ejecuciones hipotecarias de vivienda por CCAA",
     "Estadística de Ejecuciones Hipotecarias", "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/10740",
     "Trimestral", "INE", "https://www.ine.es/"),
    ("INE · VTE", "Viviendas turísticas (VUT) por CCAA",
     "Estadística de Viviendas Turísticas", "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/46141",
     "Anual", "INE", "https://www.ine.es/"),
    ("CGPJ", "Lanzamientos (desahucios) por CCAA y trimestre",
     "Efecto de la crisis económica en los órganos judiciales (Excel trimestral)",
     "https://www.poderjudicial.es/cgpj/es/Temas/Estadistica-Judicial/",
     "Trimestral", "CGPJ — datos judiciales públicos", "https://www.poderjudicial.es/"),
    ("BOE", "Decretos y disposiciones sobre vivienda",
     "BOE · datos abiertos (sumario diario XML)",
     "https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD",
     "Diaria", "BOE — reutilización permitida citando la fuente", "https://www.boe.es/datosabiertos/"),
]



CSS = """
:root{--ink:#0f172a;--mut:#64748b;--accent:#0f766e;--line:#e2e8f0;--bg:#f8fafc;--card:#fff}
*{box-sizing:border-box} body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}
.nav{position:sticky;top:0;background:#0f766e;color:#fff;z-index:9} .nav .in{max-width:1060px;margin:0 auto;padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:.86rem}
.nav a{color:#fff;text-decoration:none;opacity:.9} .nav a:hover{opacity:1} .nav b{margin-right:auto}
.hero{background:linear-gradient(135deg,#0f766e,#0e7490 70%,#0369a1);color:#fff;padding:40px 20px 52px}
.wrap{max-width:1060px;margin:0 auto;padding:0 20px} .hero h1{font-size:2rem;margin:0 0 8px} .hero p{margin:0;opacity:.95;max-width:760px}
main{max-width:1060px;margin:0 auto;padding:34px 20px 60px} h2{font-size:1.2rem;margin:34px 0 10px} h2 span{color:var(--mut);font-weight:400;font-size:.85rem}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px;margin-bottom:14px}
.mut{color:var(--mut)} a{color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:.88rem} th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--accent);color:var(--mut);font-size:.74rem;text-transform:uppercase} td{padding:8px 10px;border-bottom:1px solid var(--line)} .num{text-align:right;font-variant-numeric:tabular-nums}
code{background:#f1f5f9;padding:1px 4px;border-radius:4px}
.box{margin:12px 0;padding:12px 16px;background:#fffbeb;border-left:4px solid #d97706;border-radius:6px;font-size:.88rem}
footer{max-width:1060px;margin:0 auto;padding:24px 20px 50px;font-size:.8rem;color:var(--mut)} footer a{color:var(--accent)}
"""


def _shell(titulo, desc, canonical, h1, intro, body, active=""):
    def na(href, txt):
        st = ' style="opacity:.6;font-weight:800"' if href == active else ''
        return f'<a href="{href}"{st}>{txt}</a>'
    nav = ('<nav class="nav"><div class="in"><b>🏠 Observatorio de la vivienda</b>'
           + na("/", "Observatorio") + na("/fuentes.html", "Fuentes") + na("/propiedad.html", "Propiedad")
           + na("/datos.html", "Datos")
           + '<a href="https://pruebapublica.com" style="opacity:.7">pruebapublica.com</a></div></nav>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(titulo)}</title><meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canonical}"><meta name="robots" content="index, follow">
<style>{CSS}</style></head><body>
{nav}
<header class="hero"><div class="wrap"><h1>{h1}</h1><p>{intro}</p></div></header>
<main>{body}</main>
<footer>Observatorio de la vivienda · <a href="https://pruebapublica.com">pruebapublica.com</a> · datos de fuentes públicas · <a href="/fuentes.html">Fuentes y auditoría</a> · <a href="https://github.com/mcasrom/vivienda-osint" target="_blank" rel="noopener">código abierto</a> · v{VERSION}</footer>
</body></html>"""


def _fuentes_html():
    filas = "".join(
        f'<tr><td><b>{E(n)}</b></td><td>{E(q)}<br><span class="mut" style="font-size:.78rem">{E(d)}</span></td>'
        f'<td><code style="font-size:.72rem;word-break:break-all">{E(ep)}</code></td><td>{E(per)}<br><span class="mut" style="font-size:.78rem">{E(lic)}</span></td>'
        f'<td><a href="{E(link)}" target="_blank" rel="noopener">ver ↗</a></td></tr>'
        for n, q, d, ep, per, lic, link in SOURCES)
    body = f'''<h2>1. Fuentes (todas oficiales y abiertas)</h2>
<div class="panel"><table><thead><tr><th>Fuente</th><th>Qué aporta</th><th>Endpoint (reproducible)</th><th>Periodicidad / licencia</th><th></th></tr></thead><tbody>{filas}</tbody></table>
<p class="mut" style="font-size:.8rem">Cada cifra procede de una de estas fuentes, por su API o fichero público. El endpoint exacto se indica para poder reproducirlo.</p></div>
<h2>2. Cómo se obtiene y se verifica</h2>
<div class="panel"><ul>
<li><b>Ingesta directa</b> de las APIs/ficheros (sin intermediarios); los valores se guardan <b>tal cual</b> en <code>data/vivienda.db</code>.</li>
<li><b>Reproducible</b>: cualquiera puede llamar al mismo endpoint y comparar. Módulos públicos (<code>ingest/</code>).</li>
<li><b>Reconstrucción diaria</b> por cron; <b>sin editar cifras</b> (solo ordena y agrega); <b>fecha visible</b> en cada indicador.</li>
</ul></div>
<h2>3. Trazabilidad por sección</h2>
<div class="panel"><ul>
<li>Precio (IPV) · alquiler índice (IPVA) · ejecuciones (EH) · turísticas (VTE) → <b>INE</b>.</li>
<li>Lanzamientos (desahucios) → <b>CGPJ</b>. Decretos → <b>BOE</b>.</li>
</ul></div>
<h2>4. Límites de la auditoría</h2>
<div class="panel"><ul>
<li><b>Licencias</b>: INE y datos del observatorio, <b>CC BY 4.0</b>; CGPJ (datos judiciales públicos), BOE y MIVAU/SERPAVI, reutilización <b>citando la fuente</b>.</li>
<li><b>Momentos distintos</b>: precios, registros, alquiler fiscal y lanzamientos no se combinan en un mismo gráfico.</li>
<li><b>No se publica precio del alquiler por municipio ni provincia</b>: la muestra de anuncios disponible no da para una cifra defendible. El alquiler se publica solo como índice IPVA (INE), cuyo último dato es de 2024.</li>
<li>El observatorio <b>no interpreta causalidad</b>.</li>
</ul></div>
<p class="mut" style="font-size:.8rem">Última revisión: {date.today().isoformat()}</p>'''
    return _shell("Fuentes y auditoría — Observatorio de la vivienda",
                  "Fuentes oficiales (INE, CGPJ, BOE), endpoint exacto, periodicidad y cómo se verifica cada dato.",
                  "https://vivienda.pruebapublica.com/fuentes.html", "Fuentes y auditoría",
                  "Qué datos usamos, de dónde salen exactamente, cada cuánto se actualizan y cómo se verifican.", body, active="/fuentes.html")



def _datos_html(datasets):
    filas = "".join(
        f'<tr><td><b>{E(d["titulo"])}</b><br><span class="mut" style="font-size:.78rem">{E(d["fuente"])}</span></td>'
        f'<td>{E(d["periodo"])}<br><span class="mut" style="font-size:.78rem">{d["n"]} filas · {E(d["licencia"])}</span></td>'
        f'<td><a href="/data/{d["id"]}.csv">CSV</a> · <a href="/data/{d["id"]}.json">JSON</a></td></tr>'
        for d in datasets)
    body = f'''<h2>1. Catálogo de datos (descarga por serie)</h2>
<div class="panel"><table><thead><tr><th>Serie</th><th>Periodo / licencia</th><th>Descarga</th></tr></thead><tbody>{filas}</tbody></table>
<p class="mut" style="font-size:.8rem">Cada serie se publica como <b>CSV</b> (UTF-8, separado por comas, punto decimal) y <b>JSON</b>. Los ficheros se regeneran con la página; el endpoint de cada fuente está en <a href="/fuentes.html">Fuentes</a>.</p></div>
<h2>2. Cómo citar</h2>
<div class="panel"><p style="font-size:.9rem">Observatorio de la vivienda (pruebapublica.com). Datos de INE, CGPJ y BOE. Citando la fuente original y este observatorio.</p>
<p class="mut" style="font-size:.82rem">Atajo: <a href="/data/latest.json">latest.json</a> (último dato de cada indicador) · catálogo <a href="/data/index.json">index.json</a> · guía para asistentes de IA: <a href="/llms.txt">/llms.txt</a>.</p></div>
<h2>3. Límites</h2>
<div class="panel"><ul style="font-size:.9rem">
<li>Las cifras son <b>tal cual</b> las publica cada organismo, agregadas cuando la serie es por CCAA/provincia.</li>
<li>No se publica precio del alquiler por municipio ni provincia (muestra insuficiente). El alquiler se publica solo como índice IPVA del INE, con su periodo.</li>
<li>Licencias de reutilización INE/CGPJ/BOE: reutilización con cita.</li>
</ul></div>'''
    return _shell("Datos — Observatorio de la vivienda",
                  "Descarga en CSV y JSON de cada serie: precios (INE), índice de alquiler, ejecuciones, lanzamientos (CGPJ) y viviendas turísticas.",
                  "https://vivienda.pruebapublica.com/datos.html", "Datos y descargas",
                  "Todas las series del observatorio, listas para reutilizar: CSV y JSON con su fuente y periodo.", body, active="/datos.html")


def _propiedad_html():
    body = f'''<h2>1. Concentración de la propiedad (propietarios por nº de viviendas)</h2>
<div class="panel">
<div class="box">⚠️ <b>No hay fuente oficial abierta</b> que publique, de forma nominal y actualizada, cuántos propietarios tienen 1, 2, 5, 10 o 20 viviendas. El <b>Catastro</b> y el <b>Registro de la Propiedad</b> tienen el dato pero <b>no lo publican agregado</b> (privacidad/RGPD). Por eso <b>no lo medimos</b>.</div>
<p style="font-size:.9rem">Dónde SÍ se publican aproximaciones (estudios, no datasets actualizables):</p>
<ul style="font-size:.9rem">
<li><b>Colegio de Registradores</b> — «Anuario/Panorama Registral» (distribución de la propiedad). <a href="https://www.registradores.org/actualidad/portal-estadistico-registral" target="_blank" rel="noopener">portal estadístico ↗</a></li>
<li><b>Banco de España</b> — boletines sobre vivienda y tenedores institucionales. <a href="https://www.bde.es/" target="_blank" rel="noopener">bde.es ↗</a></li>
<li><b>AEAT</b> — «Estadística de viviendas declaradas en IRPF» (arrendadores, viviendas, alquiler medio; anual). <a href="https://sede.agenciatributaria.gob.es/Sede/estadisticas/estadisticas-impuesto/estadistica-viviendas-declaradas-irpf.html" target="_blank" rel="noopener">visor AEAT ↗</a></li>
</ul></div>
<h2>2. Grandes tenedores institucionales (SOCIMIs)</h2>
<div class="panel"><p style="font-size:.9rem">Los «fondos buitre» <b>no son una categoría registral</b>; muchos operan vía <b>SOCIMIs</b>, cuyos datos <b>sí</b> se publican.</p>
<ul style="font-size:.9rem">
<li><b>CNMV</b> — <a href="https://www.cnmv.es/portal/consultas/busquedaemisores" target="_blank" rel="noopener">registro de emisores/SOCIMIs ↗</a></li>
<li><b>BME</b> — <a href="https://www.bolsasymercados.es/" target="_blank" rel="noopener">SOCIMIs cotizadas ↗</a></li>
</ul>
<p class="mut" style="font-size:.8rem">Pendiente (no automatizable con fiabilidad): sin API/CSV abierto.</p></div>
<h2>3. Límites de esta pestaña</h2>
<div class="panel"><ul style="font-size:.9rem">
<li><b>Oferta de alquiler</b>: no se publica. La muestra de anuncios disponible no alcanza para una cifra defendible.</li>
<li><b>Propietarios por tramos</b>: no medible en abierto. <b>Tenencia institucional</b>: solo vía SOCIMIs.</li>
</ul></div>'''
    return _shell("Propiedad y grandes tenedores — Observatorio de la vivienda",
                  "Concentración de la propiedad y grandes tenedores: qué se mide con datos abiertos y qué no.",
                  "https://vivienda.pruebapublica.com/propiedad.html", "¿Quién tiene la vivienda?",
                  "Oferta de alquiler, concentración de la propiedad y grandes tenedores. Qué se puede medir con datos abiertos y qué no.", body, active="/propiedad.html")



def bloque_barras(pares, color, fmt=None, unidad="", top=10, grupo="grupos"):
    """Top-N barras + desplegable con la lista completa (no se pierde detalle)."""
    if not pares:
        return "<p class='mut'>sin datos</p>"
    top_pares = pares[:top]
    grafico = svg_bars(top_pares, color=color, h=max(150, len(top_pares) * 26), fmt=fmt, unidad=unidad)
    if len(pares) > top:
        filas = "".join(
            f'<tr><td>{E(k)}</td><td class="num">{fmt(v) if fmt else _eur(v)}</td></tr>' for k, v in pares)
        det = ('<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:600;font-size:.82rem;color:var(--ink)">'
               f'Ver el detalle completo · {len(pares)} {E(grupo)}</summary><table style="margin-top:8px"><tbody>{filas}</tbody></table></details>')
        grafico += det
    return grafico


def _ind(valor, unidad, tend, etq_tend, fuente, periodo, edad=None):
    # Una variación que «se modera» NO es una bajada: el nivel sigue subiendo, lo que
    # se frena es su ritmo (IPV +12,2 % anual). Pintarla con la flecha de «bajando» hacía
    # que una tarjeta en verde con un número positivo se leyera como precio en caída.
    # La deceleración usa flecha neutra; ▼/verde queda solo para bajadas de nivel reales.
    if etq_tend == "se modera":
        cls, fl = "", "▬"
    else:
        cls = {"subiendo": "up", "bajando": "down", "estable": ""}.get(tend, "")
        fl = {"subiendo": "▲", "bajando": "▼", "estable": "▬"}.get(tend, "")
    return (f'<div class="ind"><div class="v">{valor}<small>{unidad}</small></div>'
            f'<div class="t {cls}">{fl} {etq_tend}</div><div class="f">{etiqueta_src(fuente, periodo, edad)}</div></div>')


def etiqueta_src(f, p, edad=None):
    # `p` = periodo del DATO (p. ej. «2024»); `edad` = días desde nuestra última
    # incorporación. Se separan en spans distintos para que no se lea «dato de hoy».
    act = ""
    if edad is not None:
        txt = "actualizado hoy" if edad == 0 else f"actualizado hace {edad} d"
        act = f' · <span class="mut">{txt}</span>'
    return f'{f}<br><span class="mut">{p}</span>{act}'


def _estado_datos(est):
    """Bloque «Estado de datos»: ✓/⚠ por fuente con la última incorporación válida.

    Hace visible un fallo de ingesta que hoy solo quedaba en el log (regla 24b):
    si una fuente no se actualiza, muestra su última versión válida y su antigüedad.
    """
    filas = []
    for k in est:
        e = est.get(k, {}) or {}
        nom = e.get("nombre", k.upper())
        if e.get("ok") is True:
            ic = '<span style="color:#15803d" title="ok">✓</span>'
            txt = (f'incorporado {_fd(e["actualizado"])}' if e.get("actualizado")
                   else 'incorporado')
        elif e.get("ok") is False:
            ic = '<span style="color:#b45309" title="fallo">⚠</span>'
            txt = (f'<b>sin actualizar</b> · última válida {_fd(e["ultima_ok"])}'
                   + (f' (hace {e["edad_dias"]} d)' if e.get("edad_dias") is not None else '')
                   if e.get("ultima_ok") else '<b>sin incorporación válida</b>')
        else:
            ic = '<span class="mut">·</span>'
            txt = 'sin estado'
        filas.append(f'<div class="m"><span class="d">{ic} {E(nom)}</span> {txt}</div>')
    return "".join(filas)


def svg_line(serie, color="#0f766e", w=780, h=210, marcas=(), fmt=None):
    if len(serie) < 2:
        return "<p class='mut'>serie no conectada</p>"
    ys = [v for _, v in serie]
    mn, mx = min(min(ys), 0), max(ys)
    rng = (mx - mn) or 1
    n = len(serie)
    pts = [(40 + i * (w - 80) / (n - 1), h - 34 - (v - mn) / rng * (h - 70), e, v) for i, (e, v) in enumerate(serie)]
    poly = " ".join(f"{x:.0f},{y:.0f}" for x, y, _, _ in pts)
    area = f"40,{h-34} {poly} {pts[-1][0]:.0f},{h-34}"
    zero = h - 34 - (0 - mn) / rng * (h - 70)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    out.append(f'<line x1="40" y1="{zero:.0f}" x2="{w-40}" y2="{zero:.0f}" stroke="#cbd5e1"/>')
    out.append(f'<polygon points="{area}" fill="{color}18"/>')
    out.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    for x, y, _, _ in pts:
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.4" fill="{color}"/>')
    for k, (x, y, e, v) in enumerate(pts):
        if k % max(1, n // 8) == 0 or k == n - 1:
            out.append(f'<text x="{x:.0f}" y="{h-12}" font-size="9.5" fill="#64748b" text-anchor="middle">{E(e)}</text>')
    # valor en cada punto (rotulado)
    for x, y, e, v in pts:
        lab = fmt(v) if fmt else _pct(v)
        va = "bottom" if y > h * 0.5 else "top"
        dy = -7 if va == "bottom" else 12
        out.append(f'<text x="{x:.0f}" y="{y+dy:.0f}" font-size="9.5" fill="#0f172a" text-anchor="middle" font-weight="700">{lab}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_bars(pares, color=None, h=200, w=780, fmt=None, unidad="/m²"):
    if not pares:
        return "<p class='mut'>sin datos</p>"
    mx = max(v for _, v in pares) or 1
    padl = 190          # hueco para la etiqueta (a la izquierda, en negro)
    bw = w - padl - 70  # ancho útil para las barras
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    rowh = h / len(pares)
    for i, (lab, v) in enumerate(pares):
        y = i * rowh + rowh * 0.16
        bh = rowh * 0.72
        ww = max(2, v / mx * bw)
        c = color or ("#dc2626" if v >= 8 else "#f59e0b" if v >= 5 else "#16a34a")
        out.append(f'<text x="{padl-8}" y="{y+bh*0.72:.1f}" font-size="12" fill="#0f172a" text-anchor="end" font-weight="600">{E(lab)}</text>')
        out.append(f'<rect x="{padl}" y="{y:.1f}" width="{ww:.1f}" height="{bh:.1f}" rx="3" fill="{c}"/>')
        txt = fmt(v) if fmt else (_eur(v) + unidad)
        out.append(f'<text x="{padl+ww+7:.1f}" y="{y+bh*0.72:.1f}" font-size="12" fill="#0f172a" font-weight="700">{txt}</text>')
    out.append("</svg>")
    return "".join(out)


def _eurp(v):
    return f"{v:,.1f} €".replace(",", " ").replace(".", ",") if v is not None else "—"


_MESES3 = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _etq_mes(f):
    try:
        d = date.fromisoformat(str(f)[:10])
        return f"{_MESES3[d.month - 1]} {str(d.year)[2:]}"
    except (TypeError, ValueError):
        return str(f)


def _nice_ticks(mn, mx, n=5):
    """Valores «redondos» de Y para la rejilla (paso 1/2/2,5/5/10)."""
    if not (mx > mn):
        mx = mn + 1
    span = mx - mn
    step = 10 ** math.floor(math.log10(span / n))
    for mult in (1, 2, 2.5, 5, 10):
        if span / (step * mult) <= n:
            step *= mult
            break
    lo, hi, out, v = math.floor(mn / step) * step, math.ceil(mx / step) * step, [], math.floor(mn / step) * step
    while v <= hi + 1e-9:
        out.append(round(v, 2))
        v += step
    return out


def svg_multiline(series, w=780, h=270, fmt=None, ticks_n=5):
    """Varias líneas sobre el mismo eje Y, con **rejilla y valores del eje Y**
    rotulados, leyenda con el último valor de cada línea y eje X con las fechas.
    `series` = [(label, color, [(fecha, valor)])]; alineadas por fecha (intersección)."""
    fmt = fmt or (lambda v: f"{v:.1f}".replace(".", ","))
    sets = [set(f for f, _ in s) for _, _, s in series if s]
    if not sets:
        return "<p class='mut'>sin datos</p>"
    comun = sorted(set.intersection(*sets))
    if len(comun) < 2:
        return "<p class='mut'>serie no conectada</p>"
    mapas = [dict(s) for _, _, s in series]
    allv = [mapas[i][f] for i in range(len(series)) for f in comun]
    ticks = _nice_ticks(min(allv), max(allv), ticks_n)
    mn, mx = min(ticks), max(ticks)
    rng = (mx - mn) or 1
    n = len(comun)
    l, r, t, b = 52, 122, 14, 34

    def xy(i, v):
        return l + i * (w - l - r) / (n - 1), h - b - (v - mn) / rng * (h - t - b)

    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    for tv in ticks:                                    # rejilla + valores Y
        _, y = xy(0, tv)
        out.append(f'<line x1="{l}" y1="{y:.0f}" x2="{w-r}" y2="{y:.0f}" stroke="#e2e8f0"/>')
        out.append(f'<text x="{l-6}" y="{y+3:.0f}" font-size="9.5" fill="#64748b" '
                   f'text-anchor="end">{E(fmt(tv))}%</text>')
    if mn <= 0 <= mx:                                   # línea 0 destacada
        _, y0 = xy(0, 0)
        out.append(f'<line x1="{l}" y1="{y0:.0f}" x2="{w-r}" y2="{y0:.0f}" stroke="#94a3b8"/>')
    for idx, (label, color, _s) in enumerate(series):
        pts = [xy(i, mapas[idx][f]) for i, f in enumerate(comun)]
        out.append('<polyline points="' + " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
                   + f'" fill="none" stroke="{color}" stroke-width="2.4"/>')
        for x, y in pts:
            out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.2" fill="{color}"/>')
        xl, yl = pts[-1]
        out.append(f'<text x="{xl+6:.0f}" y="{yl+3:.0f}" font-size="10" fill="{color}" '
                   f'font-weight="700">{E(label)} {E(fmt(mapas[idx][comun[-1]]))}%</text>')
    step = max(1, n // 8)
    for i, f in enumerate(comun):                       # eje X
        if i % step == 0 or i == n - 1:
            x, _ = xy(i, mn)
            out.append(f'<text x="{x:.0f}" y="{h-12}" font-size="9.5" fill="#64748b" '
                       f'text-anchor="middle">{E(_etq_mes(f))}</text>')
    out.append("</svg>")
    return "".join(out)


_SLUG_FIX = {
    "Madrid, Comunidad de": "madrid",
    "Murcia, Región de": "murcia",
    "Asturias, Principado de": "asturias",
    "Navarra, Comunidad Foral de": "navarra",
    "Balears, Illes": "baleares",
    "Rioja, La": "la-rioja",
}


def _slug(s):
    if s in _SLUG_FIX:
        return _SLUG_FIX[s]
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _ccaa_page(nom, d):
    def _pctv(v):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " %"
    def _int(v):
        return f"{int(v):,}".replace(",", ".") if v is not None else "—"
    def _rate(v):
        return f"{v:.1f}".replace(".", ",") if v is not None else "—"
    filas = "".join(f'<tr><td>{E(k)}</td><td class="num">{v}</td><td class="mut">{E(per)}</td>'
                    f'<td class="mut">{E(src)}</td></tr>' for k, v, per, src in [
                        ("Compraventas de vivienda", _int(d.get("cv")), d.get("per_cv", "—"), "INE · ETDP"),
                        ("Lanzamientos (desahucios)", _int(d.get("lz")), d.get("per_lz", "—"), "CGPJ"),
                        ("Ejecuciones hipotecarias", _int(d.get("eh")), d.get("per_eh", "—"), "INE · EH"),
                        ("Viviendas de uso turístico", _int(d.get("vut")), d.get("per_vut", "—"), "INE · VUT"),
                        ("Compraventa (IPV, var. anual)", ("—" if d.get("ipv") is None else _pctv(d["ipv"])),
                         d.get("per_ipv", "—"), "INE · IPV"),
                        ("Lanzamientos por 1.000 viviendas", _rate(d.get("lz_rate")), "anualizado ×4", "calc. sobre MIVAU"),
                        ("Ejecuciones por 1.000 viviendas", _rate(d.get("eh_rate")), "último año", "calc. sobre MIVAU"),
                    ])
    body = (f'<h2>Indicadores de {E(nom)}</h2><div class="panel"><table>'
            f'<thead><tr><th>Indicador</th><th class="num">Valor</th><th>Periodo</th><th>Fuente</th></tr></thead>'
            f'<tbody>{filas}</tbody></table>'
            f'<p class="mut" style="font-size:.78rem;margin:10px 0 0">Datos oficiales. Las tasas usan como denominador '
            f'el total de viviendas (derivado del % VUT del INE). Ver <a href="/metodo.html">método</a> y '
            f'<a href="/">panel general</a>.</p></div>')
    return _shell(f"{nom} — datos de vivienda", f"Datos oficiales de vivienda en {nom}: compraventas, lanzamientos, "
                  f"ejecuciones, viviendas turísticas, precios y tasas. INE/CGPJ/MIVAU.",
                  f"https://vivienda.pruebapublica.com/ccaa/{_slug(nom)}.html",
                  f"{nom} — datos de vivienda", f"Situación de la vivienda en {nom}, con datos oficiales y su fuente.", body)


def _ccaa_index(pages):
    items = "".join(f'<li><a href="/ccaa/{_slug(nom)}.html">{E(nom)}</a></li>' for _c, nom, _d in pages)
    body = (f'<h2>Comunidades autónomas</h2><div class="panel"><ul style="columns:2;font-size:.95rem">{items}</ul>'
            f'<p class="mut" style="font-size:.8rem;margin-top:10px">Una página por comunidad autónoma, con sus '
            f'indicadores oficiales. Fuente: INE / CGPJ / MIVAU.</p></div>')
    return _shell("Comunidades autónomas — datos de vivienda", "Datos oficiales de vivienda por comunidad autónoma.",
                  "https://vivienda.pruebapublica.com/ccaa/", "Comunidades autónomas",
                  "Índice de páginas por CCAA del observatorio de la vivienda.", body)


def _cambios_xml(normas, hist, hoy):
    items = []
    for n in normas:
        f = n.get("resultado_fecha") or n.get("boe") or n.get("aprobacion")
        t = f"{n['corta']}: {ESTADO_TXT.get(n['estado'], n['estado'])}"
        d = (n.get("resultado") or n.get("resumen") or "").strip()
        if f:
            items.append((f, t, d, f"https://www.boe.es/buscar/act.php?id={n['id']}"))
    for c in hist[-30:]:
        if not c.get("fecha"):
            continue
        items.append((c["fecha"], f"Serie actualizada: {c.get('serie')}",
                      f"nueva versión (md5 {c.get('md5')})",
                      f"https://vivienda.pruebapublica.com/data/{c.get('serie')}.csv"))
    items.sort(key=lambda x: x[0], reverse=True)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           '<title>Observatorio de la vivienda — cambios</title>',
           '<link>https://vivienda.pruebapublica.com/</link>',
           '<description>Nuevas normas y cambios en las series de datos del observatorio.</description>',
           '<language>es</language>']
    for f, t, d, u in items[:40]:
        out.append(f'<item><title>{E(t)}</title><link>{E(u)}</link><guid>{E(u)}</guid>'
                   f'<pubDate>{E(f)}T00:00:00Z</pubDate><description>{E(d)}</description></item>')
    out.append('</channel></rss>')
    return "\n".join(out)


def build():
    v = via.resumen()
    hoy = date.today().isoformat()
    est = frescura.estado()          # estado por fuente (F2): ✓/⚠ + edad del dato
    ed_ine = (est.get("ine") or {}).get("edad_dias")
    ed_cgpj = (est.get("cgpj") or {}).get("edad_dias")
    region_cod = "14"                       # Murcia (código INE)
    region = territorios.NOMBRE[region_cod]

    ipv = ine.serie("ipv_var_anual")
    ipv_ult = ine.ultimo("ipv_var_anual")
    nueva = ine.ultimo("ipv_nueva_var")
    seg = ine.ultimo("ipv_segunda_var")
    eh, eh_anyo, eh_total = ine.eh_ccaa()
    lz, lz_per, lz_total = cgpj.por_ccaa()
    lz_crono = " · ".join(f"{p} <b>{int(v):,}</b>".replace(",", ".") for p, v in cgpj.cronologia() if v)
    lz_serie = cgpj.cronologia()
    lz_tot_txt = f"{int(lz_total):,}".replace(",", ".") if lz_total else "—"
    eh_nac = ine.eh_nacional()
    eh_crono = " · ".join(f"{a} <b>{int(v):,}</b>".replace(",", ".") for a, v in eh_nac)
    eh_tot_txt = f"{int(eh_total):,}".replace(",", ".") if eh_total else "—"
    cv, cv_fecha, cv_total = ine.cv_ccaa()
    cv_serie = ine.cv_nacional()
    per_cv = cv_fecha or "—"
    cv_tot_txt = f"{int(cv_total):,}".replace(",", ".") if cv_total else "—"
    hpt = ine.hpt_serie()
    hpt_ult = hpt[-1][1] if hpt else None
    per_hpt = hpt[-1][0] if hpt else "—"
    hpt_tot_txt = f"{int(hpt_ult):,}".replace(",", ".") if hpt_ult is not None else "—"
    vut, vut_anyo, vut_total, vut_pct = ine.vte_ccaa()
    vut_tot_txt = f"{int(vut_total):,}".replace(",", ".") if vut_total else "—"
    # tasas por 1.000 viviendas (denominador = total de viviendas censadas,
    # derivado del % de viviendas turísticas que publica el INE por CCAA)
    _vte_pct_ccaa = ine.vte_pct_ccaa()
    _total_viv = {c: (v / (_vte_pct_ccaa[c] / 100.0)) for c, v in vut if _vte_pct_ccaa.get(c)}
    _lz_d = {k: v for k, v in lz}
    _eh_d = {k: v for k, v in eh}
    _tasas = []
    for _c in territorios.NOMBRES:
        _tv = _total_viv.get(_c)
        if not _tv:
            continue
        _l, _e = _lz_d.get(_c), _eh_d.get(_c)
        _tasas.append((_c,
                       round(_l * 4 / _tv * 1000, 1) if _l is not None else None,
                       round(_e / _tv * 1000, 1) if _e is not None else None))
    _tasas.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))

    def _r1(v):
        return "—" if v is None else f"{v:.1f}".replace(".", ",")

    tasas_rows = "".join(f'<tr><td>{E(_c)}</td><td class="num">{_r1(_l)}</td>'
                         f'<td class="num">{_r1(_e)}</td></tr>' for _c, _l, _e in _tasas)

    # SERPAVI / MIVAU — alquiler de referencia por municipio (contratos, no oferta)
    _serp_n, _serp_anio = serpavi.total_anio()

    def _serp_rows(_rows):
        _out = []
        for _m, _p, _v in _rows:
            _vs = f"{_v:.2f}".replace(".", ",")
            _out.append(f'<tr><td>{E(_m)} <span class="mut">{E(_p)}</span></td>'
                        f'<td class="num">{_vs} €/m²</td></tr>')
        return "".join(_out)

    _serp_top_rows = _serp_rows(serpavi.top(12))
    _serp_bot_rows = _serp_rows(serpavi.bottom(12))
    ipva_s = ine.serie("ipva_var_anual")
    ipva_var = ipva_s[-1][1] if ipva_s else None
    tend_ia, _ = _tendencia(ipva_s)
    tend_lz, _ = _tendencia(lz_serie)
    tend_eh, _ = _tendencia(eh_nac)
    per_ipv = ipv[-1][0] if ipv else "—"
    per_ipva = ipva_s[-1][0] if ipva_s else "—"
    per_lz = lz_per or "—"
    per_eh = str(eh_anyo) if eh_anyo else "—"
    per_vut = str(vut_anyo) if vut_anyo else "—"
    ind_now = {"ipv": (ipv_ult, per_ipv), "ipva": (ipva_var, per_ipva),
               "lz": (lz_total, per_lz), "eh": (eh_total, per_eh), "vut": (vut_total, per_vut)}
    b0 = congelar_baseline(ind_now).get("ind", {})
    _IND = [("ipv", "pct", "Precio compraventa (IPV, var. anual)", "INE"),
            ("ipva", "pct", "Alquiler — índice (IPVA, var. anual)", "INE"),
            ("lz", "int", "Lanzamientos (desahucios)", "CGPJ"),
            ("eh", "int", "Ejecuciones hipotecarias", "INE"),
            ("vut", "int", "Viviendas turísticas (VUT)", "INE")]

    def _vp(d):
        if not d:
            return None, None
        if isinstance(d, dict):
            return d.get("v"), d.get("p")
        return (d[0], d[1] if len(d) > 1 else None)

    def _celda(d, tp):
        val, per = _vp(d)
        if val is None:
            return "—"
        return f'{_fmtv(tp, val)} <span class="mut">· {E(str(per or "—"))}</span>'

    filas_control = "".join(
        f'<tr><td>{tt}</td><td class="num">{_celda(b0.get(k), tp)}</td>'
        f'<td class="num"><b>{_celda(ind_now.get(k), tp)}</b></td>'
        f'<td class="num">{_dlt(tp, _vp(b0.get(k))[0], _vp(ind_now.get(k))[0])}</td>'
        f'<td class="mut">{src}</td></tr>'
        for k, tp, tt, src in _IND)
    _control_igual = all(_vp(b0.get(k))[0] == _vp(ind_now.get(k))[0] for k, tp, tt, src in _IND)
    _tabla_control = ('<table><thead><tr><th>Indicador</th><th class="num">Referencia · valor · periodo</th>'
                      '<th class="num">Último dato · valor · periodo</th><th class="num">Δ</th>'
                      f'<th>Fuente</th></tr></thead><tbody>{filas_control}</tbody></table>')
    if _control_igual:
        _tabla_control = ('<details style="margin-top:6px"><summary style="cursor:pointer;font-weight:600;'
                          'font-size:.82rem;color:var(--ink)">Ver la tabla del punto de control '
                          '(aún sin cambios desde la referencia)</summary>' + _tabla_control + '</details>')
    ipva = ine.serie("ipva_indice")

    tend, _ = _tendencia(ipv)
    inds = "".join([
        _ind(_pct(ipv_ult), "", tend, _etq_var(tend), "INE · IPV (compraventa)",
             "variación anual · " + per_ipv + (f" · nueva {_pct(nueva)}, 2.ª mano {_pct(seg)}" if nueva and seg else ""),
             edad=ed_ine),
        _ind(_pct(ipva_var), "", tend_ia, _etq_var(tend_ia), "INE · IPVA (alquiler)",
             "variación anual · " + per_ipva, edad=ed_ine),
        _ind((f"{int(lz_total):,}".replace(",", ".") if lz_total else "—"), "", tend_lz, _etq_nivel(tend_lz),
             "CGPJ · lanzamientos (desahucios)", per_lz, edad=ed_cgpj),
        _ind((f"{int(eh_total):,}".replace(",", ".") if eh_total else "—"), "", tend_eh, _etq_nivel(tend_eh),
             "INE · ejecuciones hipotecarias", per_eh, edad=ed_ine),
    ])
    estado_datos = _estado_datos(est)

    # --- IPC residencial (F1) ------------------------------------------------
    _cols_ipc = {"general": "#334155", "vivienda": "#0f766e",
                 "alquiler": "#b45309", "electricidad": "#0369a1"}
    ipc_series = [(ipc.COMPONENTES[c][0], _cols_ipc[c], ipc.serie(c, "var_anual"))
                  for c in ("general", "vivienda", "alquiler", "electricidad")
                  if ipc.serie(c, "var_anual")]
    ipc_multiline = svg_multiline(ipc_series)
    ipc_contrib = ipc.contribucion()
    ipc_bars = svg_bars(ipc_contrib, color="#0f766e",
                        fmt=lambda v: f"{v:.2f}".replace(".", ",") + " pp",
                        unidad="", h=max(150, len(ipc_contrib) * 30))
    ipc_viv_ult, ipc_viv_per = ipc.ultimo("vivienda", "var_anual")
    # detalle numérico cronológico (tabla plegable bajo el gráfico)
    ipc_tabla = ""
    if ipc_series:
        _comun = sorted(set.intersection(*[set(f for f, _ in s) for _, _, s in ipc_series]))
        _maps = {lab: dict(s) for lab, _, s in ipc_series}

        def _pv(v):
            return (f"{v:.1f}".replace(".", ",") + " %") if v is not None else "—"

        _head = "".join(f'<th class="num">{E(lab)}</th>' for lab, _, _ in ipc_series)
        _rows = "".join(
            f'<tr><td>{E(_etq_mes(f))}</td>'
            + "".join(f'<td class="num">{E(_pv(_maps[lab].get(f)))}</td>' for lab, _, _ in ipc_series)
            + "</tr>" for f in _comun)
        ipc_tabla = (
            f'<details style="margin-top:10px"><summary style="cursor:pointer;font-weight:600;'
            f'font-size:.82rem;color:var(--ink)">Ver los valores · {len(_comun)} meses</summary>'
            f'<table style="margin-top:8px"><thead><tr><th>Periodo</th>{_head}</tr></thead>'
            f'<tbody>{_rows}</tbody></table></details>')

    eh_bars = "".join(
        f'<tr><td>{E(k)}</td><td class="num">{int(v):,}</td>'.replace(",", ".") + "</tr>"
        for k, v in eh[:12])

    # comparador España vs región (SELECTOR de CCAA, client-side)
    _lz_map = {k: v for k, v in lz}
    comp_data = {}
    for cod, nom in territorios.NOMBRE.items():
        _ipv = ine.ultimo(f"ipv_var_anual:{cod}")
        comp_data[cod] = {"nombre": nom,
                          "ipv": round(_ipv, 1) if _ipv is not None else None,
                          "lz": int(_lz_map[nom]) if nom in _lz_map else None}
    region = territorios.NOMBRE[region_cod]
    reg_lz = comp_data[region_cod]["lz"]
    ipv_ccaa_ult = comp_data[region_cod]["ipv"]
    ipv_row = (f'<tr id="cmp-ipv"><td>Compraventa (IPV, var. anual)</td><td>{E(per_ipv)}</td>'
               f'<td class="num">{_pct(ipv_ult)}</td>'
               + (f'<td class="num">{_pct(ipv_ccaa_ult)}</td></tr>'
                  if ipv_ccaa_ult is not None
                  else '<td class="num mut">sin dato CCAA</td></tr>'))
    lz_row = (f'<tr id="cmp-lz"><td>Lanzamientos judiciales</td><td>{E(per_lz)}</td>'
              f'<td class="num">{_fmtv("int", lz_total)}</td>'
              f'<td class="num">{_fmtv("int", reg_lz) if reg_lz is not None else "sin dato"}</td></tr>')
    comp_rows = ipv_row + lz_row
    _opts = "".join(f'<option value="{c}"{" selected" if c == region_cod else ""}>{E(n)}</option>'
                    for c, n in territorios.NOMBRE.items())
    comp_json = json.dumps(comp_data, ensure_ascii=False)
    nat_json = json.dumps({"ipv_per": per_ipv, "ipv_txt": _pct(ipv_ult),
                           "lz_per": per_lz, "lz_txt": _fmtv("int", lz_total)}, ensure_ascii=False)

    filas_med = "".join(
        f'<div class="m"><span class="d">{E(d)}</span> <b>{E(t)}</b> '
        + (f'<a class="src" href="{E(u)}" target="_blank" rel="noopener">fuente ↗</a>' if u else "")
        + "</div>" for d, t, u in MEDIDAS)
    cal = "".join(f'<div class="m"><span class="d">{E(d)}</span> {E(t)}</div>' for d, t in CALENDARIO)
    # disposiciones del BOE (sección I) — se excluyen las ya listadas en MEDIDAS
    c = sqlite3.connect(boeing.DB)
    boe_all = c.execute("SELECT id, fecha, titulo, url, departamento, ambito FROM boe ORDER BY fecha DESC").fetchall()

    def _estado(uid):
        """Estado de una norma: del registro si está registrada; si no, «publicada»."""
        return NORMAS.get(uid, {}).get("estado", "publicada")

    boe_rows = [(f, t, u, dep, amb, _estado(i)) for i, f, t, u, dep, amb in boe_all
                if not any(m in (u or "") for m in MED_IDS)][:8]
    boe_html = "".join(
        f'<div class="card"><div class="fecha">{E(f)} · {E(dep or "BOE")}'
        + (f' · {E(amb)}' if amb else "") + f' · {E(ESTADO_TXT.get(est, est))}</div><div class="tit">{E(t)}</div>'
        + (f'<a class="src" href="{E(u)}" target="_blank" rel="noopener">BOE ↗</a>' if u else "")
        + "</div>" for f, t, u, dep, amb, est in boe_rows)

    # --- ficha de las normas registradas -----------------------------------
    _fichas, _ap, _bo = [], set(), set()
    for n in _REGN["normas"]:
        fila = next((r for r in boe_all if r[0] == n["id"]), None)
        if fila is None:
            print(f'[normas] AVISO: {n["id"]} no está en la tabla boe; ficha sin título oficial',
                  file=sys.stderr)
        elif fila[1] != n["boe"]:
            print(f'[normas] AVISO: {n["id"]} fecha BOE del registro {n["boe"]} ≠ BD {fila[1]}',
                  file=sys.stderr)
        _ap.add(n["aprobacion"]); _bo.add(n["boe"])
        titulo = fila[2] if fila else n["corta"]
        fechas = (f'Aprobación {_fd(n["aprobacion"])} · BOE {_fd(n["boe"])}'
                  + (f' · Vigencia {_fd(n["vigencia"])}' if n.get("vigencia") else ""))
        vot = n.get("votacion") or {}
        res = ""
        if n["estado"] == "en_votacion" and vot:
            res = (f'<div class="mut" style="font-size:.8rem">Votación de convalidación o derogación: '
                   f'{E(vot.get("organo", ""))}, {_fd(vot.get("fecha", ""))} {E(vot.get("hora", ""))}. '
                   f'<b>Resultado pendiente.</b> {E(n.get("estado_nota", ""))}</div>')
        elif n.get("resultado"):
            _u = n.get("resultado_url")
            _boe = n.get("resultado_boe") or ""
            res = (f'<div class="mut" style="font-size:.8rem">Resultado: {E(n["resultado"])}'
                   + (f' <a class="src" href="{E(_u)}" target="_blank" rel="noopener">'
                      f'Resolución del Congreso{f" ({E(_boe)})" if _boe else ""} ↗</a>' if _u else "")
                   + '</div>')
        _fichas.append(
            f'<div class="card"><div class="fecha">{E(ESTADO_TXT.get(n["estado"], n["estado"]))} · '
            f'{E(n["corta"])} · {E(n["ambito"])}</div><div class="tit">{E(titulo)}</div>'
            f'<div class="mut" style="font-size:.8rem">{E(fechas)}</div>' + res
            + (f'<div class="mut" style="font-size:.78rem">{E(n["vigencia_nota"])}</div>'
               if n.get("vigencia_nota") else "")
            + f'<a class="src" href="https://www.boe.es/buscar/act.php?id={E(n["id"])}"'
              f' target="_blank" rel="noopener">BOE ↗</a></div>')
    ficha_html = "".join(_fichas)
    desenlaces = " · ".join(
        f'<span class="mut">{E(v[0].upper() + v[1:])}.</span>' for v in DESENLACE_TXT.values())
    _ej = " · ".join(f'<a class="src" href="{E(x["url"])}" target="_blank" rel="noopener">'
                     f'{E(x["etiqueta"])}</a>' for x in MARCO.get("ejemplos", []))
    marco_html = (f'<p class="mut" style="font-size:.82rem;margin-top:12px">{E(MARCO["descripcion"])} '
                  f'<a class="src" href="{E(MARCO["url"])}" target="_blank" rel="noopener">art. 86.2 CE ↗</a>. '
                  f'{E(MARCO["registro"])} {_ej}</p><p class="mut" style="font-size:.82rem">'
                  f'{desenlaces} El observatorio no anticipa el resultado.</p>')
    _txt_ap = " y ".join(f"<b>{_fd(a)}</b>" for a in sorted(_ap))
    _txt_bo = " y ".join(f"<b>{_fd(b)}</b>" for b in sorted(_bo))
    # ZMRT (Ley 12/2023, art. 18)
    _zm = ZMRT or {}
    _zm_decl = ", ".join(_zm.get("declarantes_acumulado", [])) or "—"
    _zm_nuevas = "".join(
        f'<li><b>{E(x["ccaa"])}</b>: {E(x["zonas"])}</li>'
        for x in _zm.get("nuevas_ultimo_trimestre", []))
    _zm_res = _zm.get("ultima_resolucion") or {}
    _zm_src = (f'<a href="{E(_zm_res.get("url", ""))}" target="_blank" rel="noopener">'
               f'{E(_zm_res.get("boe", ""))} ({E(_zm_res.get("trimestre", ""))}) ↗</a>'
               if _zm_res.get("url") else "del BOE")
    _zm_mivau = _zm.get("acumulado_mivau", "")

    # --- exportaciones CSV/JSON (por serie) ---
    datasets = []

    def _idx(serie):
        return {e: v for e, v in serie}

    ipv_idx, ipv_nv, ipv_sg = _idx(ine.serie("ipv_indice")), _idx(ine.serie("ipv_nueva_var")), _idx(ine.serie("ipv_segunda_var"))
    _write_dataset("precios-ipv", "Precio de compraventa (IPV), variación anual", "INE · tabla 80270",
                   "trimestral", "INE — reutilización citando fuente",
                   ["periodo", "variacion_anual", "variacion_nueva", "variacion_segunda", "indice"],
                   [{"periodo": e, "variacion_anual": v, "variacion_nueva": ipv_nv.get(e, ""),
                     "variacion_segunda": ipv_sg.get(e, ""), "indice": ipv_idx.get(e, "")} for e, v in ipv], datasets)
    ipva_idx = _idx(ipva)
    _write_dataset("alquiler-ipva", "Índice de precios del alquiler (IPVA)", "INE · tabla 59056",
                   "anual (experimental, base fiscal)", "INE — reutilización citando fuente",
                   ["periodo", "variacion_anual", "indice"],
                   [{"periodo": e, "variacion_anual": v, "indice": ipva_idx.get(e, "")} for e, v in ipva_s], datasets)
    _write_dataset("ejecuciones-hipotecarias-ccaa", "Ejecuciones hipotecarias de vivienda por CCAA",
                   "INE · tabla 10740", str(eh_anyo) if eh_anyo else "—", "INE — reutilización citando fuente",
                   ["ccaa", "ejecuciones"], [{"ccaa": k, "ejecuciones": int(v)} for k, v in eh], datasets)
    _write_dataset("ejecuciones-hipotecarias-nacional", "Ejecuciones hipotecarias de vivienda (nacional)",
                   "INE · tabla 10740", "anual", "INE — reutilización citando fuente",
                   ["anio", "ejecuciones"], [{"anio": a, "ejecuciones": int(v)} for a, v in eh_nac], datasets)
    _write_dataset("compraventas-ccaa", "Compraventas de vivienda por CCAA", "INE · ETDP (tabla 49280)",
                   per_cv, "INE — reutilización citando fuente",
                   ["ccaa", "compraventas"], [{"ccaa": k, "compraventas": int(v)} for k, v in cv], datasets)
    _write_dataset("compraventas-nacional", "Compraventas de vivienda (nacional)", "INE · ETDP (tabla 49280)",
                   "anual", "INE — reutilización citando fuente",
                   ["periodo", "compraventas"],
                   [{"periodo": p, "compraventas": int(v)} for p, v in cv_serie], datasets)
    _write_dataset("hipotecas-nacional", "Hipotecas constituidas de vivienda (nacional)", "INE · HPT (tabla 3200)",
                   "mensual", "INE — reutilización citando fuente",
                   ["periodo", "hipotecas"], [{"periodo": p, "hipotecas": int(v)} for p, v in hpt], datasets)
    _write_dataset("lanzamientos-ccaa", "Lanzamientos (desahucios) por CCAA", "CGPJ · Efecto de la crisis",
                   per_lz, "CGPJ — datos judiciales públicos",
                   ["ccaa", "lanzamientos"], [{"ccaa": k, "lanzamientos": int(v)} for k, v in lz], datasets)
    _write_dataset("lanzamientos-cronologia", "Lanzamientos (desahucios) nacionales por trimestre",
                   "CGPJ · Efecto de la crisis",
                   f"{lz_serie[0][0]}–{lz_serie[-1][0]}" if lz_serie else "—", "CGPJ — datos judiciales públicos",
                   ["periodo", "lanzamientos"], [{"periodo": p, "lanzamientos": int(v)} for p, v in lz_serie], datasets)
    _write_dataset("viviendas-turisticas-ccaa", "Viviendas de uso turístico por CCAA", "INE · tabla 46141",
                   str(vut_anyo) if vut_anyo else "—", "INE — reutilización citando fuente",
                   ["ccaa", "viviendas_turisticas"],
                   [{"ccaa": k, "viviendas_turisticas": int(v)} for k, v in vut], datasets)
    _write_dataset("boe-vivienda", "Disposiciones generales del BOE sobre vivienda",
                   "BOE · sumario diario (sección I)", "diaria (últimos 21 días)", "BOE — reutilización citando fuente",
                   ["id", "fecha", "estado", "fecha_aprobacion", "fecha_vigencia",
                    "ambito", "departamento", "titulo", "url"],
                   [{"id": i, "fecha": f, "estado": _estado(i),
                     "fecha_aprobacion": NORMAS.get(i, {}).get("aprobacion", ""),
                     "fecha_vigencia": NORMAS.get(i, {}).get("vigencia", ""),
                     "ambito": amb, "departamento": dep, "titulo": t, "url": u}
                    for i, f, t, u, dep, amb in boe_all], datasets)
    ctrl_rows = []
    for k, tp, tt, src in _IND:
        rv, rp = _vp(b0.get(k)); uv, up = _vp(ind_now.get(k))
        ctrl_rows.append({"indicador": tt, "referencia": rv, "periodo_referencia": rp,
                          "ultimo": uv, "periodo_ultimo": up, "fuente": src})
    _write_dataset("punto-control", "Punto de control (referencia vs último dato)",
                   "varias (INE/CGPJ)", "ver columnas de periodo", "varias — ver fuente",
                   ["indicador", "referencia", "periodo_referencia", "ultimo", "periodo_ultimo", "fuente"],
                   ctrl_rows, datasets)
    # Estado de frescura por fuente (F2): dato operativo, se publica por transparencia.
    if any((est.get(k) or {}).get("ok") is not None for k in est):
        _write_dataset("estado-fuentes", "Estado de actualización de las fuentes",
                       "cron del observatorio", "diaria", "CC BY 4.0",
                       ["fuente", "ok", "actualizado", "edad_dias", "ultima_ok"],
                       [{"fuente": (est.get(k) or {}).get("nombre", k.upper()),
                         "ok": (est.get(k) or {}).get("ok"),
                         "actualizado": (est.get(k) or {}).get("actualizado") or "",
                         "edad_dias": (est.get(k) or {}).get("edad_dias"),
                         "ultima_ok": (est.get(k) or {}).get("ultima_ok") or ""}
                        for k in est], datasets)
    # IPC residencial (F1): variación anual por componente (columnas alineadas por mes).
    if ipc_series:
        _comp_cols = list(ipc.COMPONENTES)
        _ipc_map = {c: dict(ipc.serie(c, "var_anual")) for c in _comp_cols}
        _ipc_fechas = sorted({f for c in _comp_cols for f, _ in ipc.serie(c, "var_anual")})
        _write_dataset("ipc-vivienda", "IPC residencial — variación anual por componente",
                       "INE · IPC base 2025 (ECOICOP v2)", "mensual",
                       "INE — reutilización citando fuente",
                       ["periodo"] + _comp_cols,
                       [{"periodo": f, **{c: _ipc_map[c].get(f, "") for c in _comp_cols}}
                        for f in _ipc_fechas], datasets)
    if _serp_n:
        _serp_all = sqlite3.connect(f"file:{boeing.DB}?mode=ro", uri=True).execute(
            "SELECT codigo_ine,municipio,provincia,eur_m2,p25,p75,anio FROM serpavi "
            "ORDER BY eur_m2 DESC").fetchall()
        _write_dataset("alquiler-serpavi", "Alquiler de referencia por municipio (SERPAVI/MIVAU)",
                       "MIVAU · SERPAVI (contratos, fianzas Catastro/AEAT)", _serp_anio,
                       "MIVAU — reutilización citando la fuente",
                       ["codigo_ine", "municipio", "provincia", "eur_m2", "p25", "p75", "anio"],
                       [{"codigo_ine": r[0], "municipio": r[1], "provincia": r[2], "eur_m2": r[3],
                         "p25": r[4], "p75": r[5], "anio": r[6]} for r in _serp_all], datasets)
    with open(os.path.join(DATA_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"observatorio": "Observatorio de la vivienda",
                   "url": "https://vivienda.pruebapublica.com/", "generado": hoy, "series": datasets},
                  f, ensure_ascii=False, indent=1)
    # datapackage.json (Frictionless Data): recursos con bytes/md5, esquema y licencia
    _dp_res = []
    for _d in datasets:
        _b = open(os.path.join(DATA_DIR, _d["id"] + ".csv"), "rb").read()
        _dp_res.append({
            "name": _d["id"], "title": _d["titulo"], "path": "data/" + _d["id"] + ".csv",
            "format": "csv", "mediatype": "text/csv", "bytes": len(_b),
            "hash": "md5:" + hashlib.md5(_b).hexdigest(), "n": _d["n"],
            "sources": [{"title": _d["fuente"]}],
            "schema": {"fields": [{"name": c} for c in _d.get("columnas", [])]},
        })
    with open(os.path.join(DATA_DIR, "datapackage.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "vivienda-osint", "title": "Observatorio de la vivienda",
                   "description": "Datos oficiales de vivienda en España (INE, CGPJ, BOE, MIVAU).",
                   "homepage": "https://vivienda.pruebapublica.com/",
                   "license": "CC-BY-4.0", "created": hoy, "resources": _dp_res},
                  f, ensure_ascii=False, indent=1)
    distrib_json = json.dumps(
        [{"@type": "DataDownload", "name": d["titulo"], "encodingFormat": "text/csv",
          "contentUrl": f"https://vivienda.pruebapublica.com/data/{d['id']}.csv"} for d in datasets],
        ensure_ascii=False)

    # instantánea combinada con el último dato de cada indicador
    _uni = {"ipv": "%", "ipva": "%", "lz": "lanzamientos", "eh": "ejecuciones", "vut": "viviendas"}
    _tm = {"ipv": (tend, "var"), "ipva": (tend_ia, "var"), "lz": (tend_lz, "nivel"),
           "eh": (tend_eh, "nivel"), "vut": ("", "")}
    indicadores = {}
    for k, tp, tt, src in _IND:
        val, per = _vp(ind_now.get(k))
        t, tipo = _tm.get(k, ("", ""))
        etq = _etq_var(t) if tipo == "var" else _etq_nivel(t) if tipo == "nivel" else ""
        _e = est.get(src.lower(), {}) or {}
        indicadores[k] = {"indicador": tt, "valor": val, "periodo": per, "unidad": _uni.get(k, ""),
                          "fuente": src, "tendencia": etq,
                          "actualizado": _e.get("actualizado"), "edad_dias": _e.get("edad_dias")}
    with open(os.path.join(DATA_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump({"observatorio": "Observatorio de la vivienda",
                   "url": "https://vivienda.pruebapublica.com/", "generado": hoy,
                   "referencia_decretos": {"fecha": "2026-09-29",
                                           "detalle": "RDL 26/2026 y 27/2026 (vivienda)"},
                   "indicadores": indicadores,
                   "catalogo": "https://vivienda.pruebapublica.com/data/index.json"},
                  f, ensure_ascii=False, indent=1)

    llms = f"""# Observatorio de la vivienda

> Observatorio cívico e independiente que publica datos oficiales de vivienda en España
> (INE, CGPJ, BOE). Encuadre neutral: sin puntuaciones compuestas ni atribuciones; cada
> cifra lleva unidad, fuente y fecha.

## Páginas
- Panel: https://vivienda.pruebapublica.com/
- Fuentes, método y límites: https://vivienda.pruebapublica.com/fuentes.html
- Propiedad y grandes tenedores: https://vivienda.pruebapublica.com/propiedad.html
- Datos y descargas: https://vivienda.pruebapublica.com/datos.html

## Datos abiertos (CSV / JSON, sin registro)
- Catálogo completo: https://vivienda.pruebapublica.com/data/index.json
- Último dato de cada indicador: https://vivienda.pruebapublica.com/data/latest.json
- Una serie por indicador; cada una en `/data/<serie>.csv` y `/data/<serie>.json`:
  precios-ipv · alquiler-ipva · ejecuciones-hipotecarias-ccaa · ejecuciones-hipotecarias-nacional ·
  lanzamientos-ccaa · lanzamientos-cronologia · viviendas-turisticas-ccaa ·
  boe-vivienda · punto-control

## Fuentes
- INE: IPV (tabla 80270), IPVA (59056), ejecuciones hipotecarias (10740), viviendas turísticas (46141).
- CGPJ: «Efecto de la crisis en los órganos judiciales» (lanzamientos, Excel trimestral).
- BOE: sumario diario, sección I (disposiciones generales).

## Alcance de los datos
- Todas las series proceden de organismos públicos y son reproducibles por su endpoint.
- <b>No se publica precio del alquiler por municipio ni por provincia.</b> La muestra de
  anuncios disponible no alcanza para una cifra defendible y se retiró de forma deliberada.
- El único indicador de alquiler es el <b>IPVA del INE</b> (índice anual de variación, no un
  nivel de precio): su último dato disponible es de 2024 y así se indica siempre junto a la cifra.

## Licencia y cita
- Observatorio: CC BY 4.0. Fuentes: reutilización citando al organismo.
- Cita sugerida: «Observatorio de la vivienda (pruebapublica.com), {hoy}».

## Límites
- No se afirma causalidad; el punto de control usa la referencia por periodo de cada serie.
- Los datos publicados describen periodos anteriores a los RDL de 29-sep-2026. El Congreso
  acordó su derogación el 2-oct-2026 (art. 86.2 CE): sus medidas quedan sin efecto. La primera
  lectura posterior a los RDL (4T-2026) llegará en ~feb-2027.
- El IPVA (alquiler) es un índice anual: describe la variación, no un precio por m², y su
  último dato es de 2024.
"""
    with open(os.path.join(OUT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(llms)

    _ccaa_links = " · ".join(f'<a href="/ccaa/{_slug(_n)}.html">{E(_n)}</a>'
                             for _c, _n in territorios.NOMBRE.items())
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="google-site-verification" content="mlyuKtDMOhZ2x2lMrqr-MHT9LeUW8i6uEJw1Sv6AzNY">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Observatorio de la vivienda — datos oficiales</title>
<meta name="description" content="Qué dicen los datos oficiales de vivienda (INE, CGPJ, BOE), sin puntuaciones ni atribuciones. Compraventas, alquiler, ejecuciones hipotecarias, lanzamientos y viviendas turísticas, con fuente y fecha.">
<link rel="canonical" href="https://vivienda.pruebapublica.com/">
<link rel="alternate" type="application/rss+xml" title="Cambios en el observatorio" href="/cambios.xml">
<meta property="og:title" content="Observatorio de la vivienda">
<meta property="og:description" content="Datos oficiales de vivienda con fuente y fecha. Sin puntuaciones ni atribuciones.">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#0f766e">
<meta property="og:type" content="website">
<meta property="og:url" content="https://vivienda.pruebapublica.com/">
<meta property="og:site_name" content="Observatorio de la vivienda">
<meta property="og:locale" content="es_ES">
<meta property="og:image" content="https://vivienda.pruebapublica.com/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Observatorio de la vivienda">
<meta name="twitter:description" content="Evolución de precios (INE), ejecuciones hipotecarias, lanzamientos (CGPJ), viviendas turísticas y decretos (BOE).">
<meta name="twitter:image" content="https://vivienda.pruebapublica.com/og.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"Observatorio de la vivienda",
"description":"Datos oficiales de vivienda en España: evolución de precios de compraventa y del alquiler (INE), ejecuciones hipotecarias y lanzamientos por CCAA (INE/CGPJ), viviendas turísticas (INE) y registro de disposiciones sobre vivienda (BOE).",
"url":"https://vivienda.pruebapublica.com/","creator":{{"@type":"Organization","name":"pruebapublica.com"}},
"license":"https://creativecommons.org/licenses/by/4.0/","isAccessibleForFree":true,
"distribution":{distrib_json},
"keywords":["vivienda","alquiler","desahucios","lanzamientos","INE","CGPJ","BOE","España"]}}
</script>
<style>
:root{{--ink:#0f172a;--mut:#64748b;--accent:#0f766e;--line:#e2e8f0;--bg:#f8fafc;--card:#fff}}
*{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}}
.nav{{position:sticky;top:0;background:#0f766e;color:#fff;z-index:9}} .nav .in{{max-width:1060px;margin:0 auto;padding:10px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:.86rem}}
.nav a{{color:#fff;text-decoration:none;opacity:.9}} .nav a:hover{{opacity:1}} .nav b{{margin-right:auto}}
.hero{{background:linear-gradient(135deg,#0f766e,#0e7490 70%,#0369a1);color:#fff;padding:40px 20px 52px}}
.wrap{{max-width:1060px;margin:0 auto;padding:0 20px}} .hero h1{{font-size:2rem;margin:0 0 8px;letter-spacing:-.01em}} .hero p{{margin:0;opacity:.95;max-width:760px}}
.inds{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;max-width:1060px;margin:-32px auto 0;padding:0 20px}}
.ind{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:0 4px 14px #0f172a14}}
.ind .v{{font-size:1.45rem;font-weight:800;color:var(--ink)}} .ind .v small{{font-size:.7rem;color:var(--mut);font-weight:600}}
.ind .t{{font-size:.76rem;font-weight:700;color:var(--mut)}} .ind .t.up{{color:#b91c1c}} .ind .t.down{{color:#15803d}}
.ind .f{{font-size:.72rem;color:var(--mut);margin-top:4px}} .mut{{color:var(--mut)}}
main{{max-width:1060px;margin:0 auto;padding:34px 20px 60px}} h2{{font-size:1.2rem;margin:38px 0 10px}} h2 span{{color:var(--mut);font-weight:400;font-size:.85rem}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}}
.card .fecha{{font-size:.7rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.04em}} .card .tit{{font-size:.88rem}} .card .src{{font-size:.76rem;color:var(--accent);text-decoration:none}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}} th{{text-align:left;padding:8px 10px;border-bottom:2px solid var(--accent);color:var(--mut);font-size:.74rem;text-transform:uppercase}} td{{padding:8px 10px;border-bottom:1px solid var(--line)}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
.m{{padding:7px 0;border-bottom:1px solid var(--line);font-size:.88rem}} .m .d{{display:inline-block;min-width:96px;color:var(--mut);font-variant-numeric:tabular-nums}} .m .src{{color:var(--accent);text-decoration:none;font-size:.78rem}}
footer{{max-width:1060px;margin:0 auto;padding:24px 20px 50px;font-size:.8rem;color:var(--mut)}} footer a{{color:var(--accent)}}
@media(max-width:820px){{.inds{{grid-template-columns:repeat(2,1fr)}} .grid{{grid-template-columns:1fr}}}}
</style></head><body>
<nav class="nav"><div class="in"><b>🏠 Observatorio de la vivienda</b>
<a href="#indicadores">Indicadores</a><a href="#inflacion">Inflación</a><a href="#comparador">Comparador</a><a href="#calendario">Calendario</a><a href="#medidas">Medidas</a><a href="#zmrt">Zonas</a><a href="#metodo">Método</a><a href="#apoyar">Apoyar</a><a href="/fuentes.html">Fuentes</a><a href="/propiedad.html">Propiedad</a><a href="/datos.html">Datos</a><a href="/ccaa/">CCAA</a>
<a href="https://pruebapublica.com" style="opacity:.7">pruebapublica.com</a></div></nav>
<header class="hero"><div class="wrap">
<h1>Qué dicen los datos oficiales de vivienda, sin puntuaciones ni atribuciones</h1>
<p>Cada cifra lleva su unidad, su fuente y su fecha. Las medidas políticas se anotan sobre las series, pero el observatorio <b>no afirma</b> que una medida causara un cambio.</p>
</div></header>
<div class="inds" id="indicadores">{inds}</div>
<main>
<div class="panel" id="estado" style="margin-bottom:8px">
<p style="margin:0 0 6px;font-size:.9rem"><b>Estado de los datos</b> <span class="mut">· última incorporación correcta de cada fuente (diaria)</span></p>
{estado_datos}
<p class="mut" style="margin:8px 0 0;font-size:.78rem">Si una fuente no responde, el día no se actualiza y aquí aparece su <b>última versión válida</b>: la web nunca presenta datos viejos como recién publicados.</p>
</div>
<h2>Precio de compraventa de vivienda, variación anual <span>· IPV nacional (INE)</span></h2>
<div class="panel">{svg_line(ipv)}<p class="mut" style="font-size:.8rem">Índice de Precios de Vivienda (IPV), total nacional, variación anual (%). Fuente: <a href="https://www.ine.es/">INE</a>. Las medidas del BOE se registran abajo.</p>{_descarga("precios-ipv")}</div>

<h2>Ejecuciones hipotecarias de vivienda por CCAA <span>· INE{f" · {eh_anyo}" if eh_anyo else ""}</span></h2>
<div class="panel">
{bloque_barras(eh, color="#0f766e", fmt=lambda v: f"{int(v):,}".replace(",", "."), unidad="", grupo="comunidades autónomas")}
<p style="font-size:.85rem;margin:18px 0 2px"><b>Cronología nacional</b> · viviendas con ejecución iniciada, por año</p>
{svg_line([(str(a), v) for a, v in eh_nac], color="#0f766e", fmt=lambda v: f"{int(v):,}".replace(",", "."))}
<p class="mut" style="font-size:.8rem">Ejecuciones hipotecarias <b>iniciadas sobre vivienda</b>, por CCAA. <b>Total nacional {eh_tot_txt}</b>. Fuente: <a href="https://www.ine.es/">INE</a>.</p>
<p class="mut" style="font-size:.8rem">Nota: los <b>lanzamientos (desahucios)</b> los publica el <b>CGPJ</b> (trimestral; próximo 16-oct-2026).</p>{_descarga("ejecuciones-hipotecarias-ccaa")}</div>

<h2 id="hipotecas">Hipotecas constituidas de vivienda <span>· INE{f" · {per_hpt}" if hpt else ""}</span></h2>
<div class="panel">
{svg_line(hpt, color="#0f766e", fmt=lambda v: f"{int(v):,}".replace(",", "."))}
<p class="mut" style="font-size:.8rem">Hipotecas constituidas sobre <b>viviendas</b> (nacional, mensual). Último dato {E(per_hpt)}: <b>{hpt_tot_txt}</b>. Fuente: <a href="https://www.ine.es/">INE</a> (Estadística de Hipotecas).</p>{_descarga("hipotecas-nacional")}</div>

<h2 id="compraventas">Compraventas de vivienda por CCAA <span>· ETDP (INE){f" · {per_cv}" if cv_fecha else ""}</span></h2>
<div class="panel">
{bloque_barras(cv, color="#0369a1", fmt=lambda v: f"{int(v):,}".replace(",", "."), unidad="", grupo="comunidades autónomas")}
<p style="font-size:.85rem;margin:18px 0 2px"><b>Cronología nacional</b> · compraventas por año</p>
{svg_line([(str(a), v) for a, v in cv_serie], color="#0369a1", fmt=lambda v: f"{int(v):,}".replace(",", "."))}
<p class="mut" style="font-size:.8rem">Compraventas de vivienda <b>inscritas</b> (ETDP, INE), por CCAA. Total {per_cv}: <b>{cv_tot_txt}</b>. Fuente: <a href="https://www.ine.es/">INE</a>.</p>{_descarga("compraventas-ccaa")}</div>

<h2>Lanzamientos (desahucios) por CCAA <span>· CGPJ{f" · {lz_per}" if lz_per else ""}</span></h2>
<div class="panel">
{bloque_barras(lz, color="#c2410c", fmt=lambda v: f"{int(v):,}".replace(",", "."), unidad="", grupo="comunidades autónomas")}
<p style="font-size:.85rem;margin:18px 0 2px"><b>Cronología nacional</b> · lanzamientos por trimestre</p>
{svg_line([(str(a), v) for a, v in lz_serie], color="#c2410c", fmt=lambda v: f"{int(v):,}".replace(",", "."))}
<p class="mut" style="font-size:.8rem">Lanzamientos <b>practicados</b> (desalojo), por CCAA. Total {lz_per}: <b>{lz_tot_txt}</b>. Fuente: <a href="https://www.poderjudicial.es/">CGPJ</a> (trimestral).</p>{_descarga("lanzamientos-ccaa")}</div>

<h2>Viviendas turísticas por CCAA <span>· INE{f" · {vut_anyo}" if vut_anyo else ""}</span></h2>
<div class="panel">
{bloque_barras(vut, color="#7c3aed", fmt=lambda v: f"{int(v):,}".replace(",", "."), unidad="", grupo="comunidades autónomas")}
<p class="mut" style="font-size:.8rem">Viviendas de uso turístico (VUT) por <b>comunidad autónoma</b>, {E(str(vut_anyo))}. Total nacional: <b>{vut_tot_txt}</b>{" · " + f"{vut_pct:.2f}".replace(".", ",") + f" % ({E(str(vut_anyo))})" if vut_pct else ""} del total de viviendas censadas. Fuente: <a href="https://www.ine.es/">INE</a> (Estadística de Viviendas Turísticas).</p>{_descarga("viviendas-turisticas-ccaa")}</div>

<h2 id="tasas">Tasas por 1.000 viviendas <span>· comparables entre CCAA</span></h2>
<div class="panel">
<p style="font-size:.85rem;margin:0 0 10px">Para comparar comunidades de tamaños distintos se normaliza por el <b>total de viviendas censadas</b> (denominador derivado del % de viviendas turísticas que publica el INE). <b>Lanzamientos</b> {E(str(lz_per))} anualizados (×4) y <b>ejecuciones</b> {E(str(eh_anyo))} por 1.000 viviendas.</p>
<table><thead><tr><th>CCAA</th><th class="num">Lanzamientos ‰<br><span class="mut" style="font-weight:400">anualizado</span></th><th class="num">Ejecuciones ‰</th></tr></thead><tbody>{tasas_rows}</tbody></table>
<p class="mut" style="font-size:.78rem;margin:8px 0 0">Una tasa alta no implica por sí sola más problema social: depende del parque de viviendas y de la litigiosidad. La lectura correcta es <b>comparar</b> CCAA, no ordenarlas como un ranking.</p></div>

<h2 id="alquiler">Alquiler de referencia por municipio <span>· SERPAVI / MIVAU</span></h2>
<div class="panel">
<p style="font-size:.85rem;margin:0 0 10px">Mediana del alquiler de los <b>contratos</b> (fianzas Catastro/AEAT), no precio de oferta. {_serp_n} municipios, dato de {E(_serp_anio)}. Fuente: <a href="https://www.mivau.gob.es/">MIVAU (SERPAVI)</a>.</p>
<div class="grid">
<div><p class="mut" style="font-size:.8rem;margin:0 0 4px"><b>Más caros</b> (€/m²/mes)</p><table><tbody>{_serp_top_rows}</tbody></table></div>
<div><p class="mut" style="font-size:.8rem;margin:0 0 4px"><b>Más baratos</b> (€/m²/mes)</p><table><tbody>{_serp_bot_rows}</tbody></table></div>
</div>
<p class="mut" style="font-size:.78rem;margin:10px 0 0">⚠️ Es la mediana de <b>todos</b> los contratos (incluidos los antiguos con renta congelada), así que suele ser <b>más baja</b> que el precio de un contrato nuevo. El CSV oficial es agregado y <b>no publica el nº de contratos (n)</b> por municipio; MIVAU solo incluye municipios con datos suficientes. No se mezcla con precio de oferta.</p>{_descarga("alquiler-serpavi")}</div>

<h2 id="inflacion">Inflación residencial <span>· IPC (INE, base 2025)</span></h2>
<div class="panel">
<p style="font-size:.85rem;margin:0 0 10px"><b>Vivienda, agua, electricidad, gas y otros combustibles</b> (grupo 04): <b>12,26 %</b> de la cesta del IPC de 2026{f" · último dato {E(_etq_mes(ipc_viv_per))}, <b>{_pct(ipc_viv_ult)}</b>" if ipc_viv_ult is not None else ""}. Variación anual de cada componente:</p>
{ipc_multiline}
{ipc_tabla}
<p style="font-size:.85rem;margin:20px 0 2px"><b>¿Qué encarece el coste residencial?</b> Contribución de cada componente a la variación del grupo 04 (<b>variación anual × su peso</b>), en puntos porcentuales.</p>
{ipc_bars}
<p class="mut" style="font-size:.8rem">Fuente: <a href="https://www.ine.es/">INE</a>, IPC base 2025 (ECOICOP v2). Un <b>índice no es un precio</b>, y el grupo 04 <b>no</b> es el coste total del hogar (no incluye alimentación, transporte…). Solo variación anual: la base cambió en ene-2026 y <b>no</b> se cruza con la anterior.</p>{_descarga("ipc-vivienda")}</div>

<h2 id="control">Punto de control · decretos de sep–oct 2026</h2>
<div class="panel">
<p style="margin:0 0 12px">Los RDL 26/2026 y 27/2026 fueron aprobados el {_txt_ap} y publicados en el BOE el {_txt_bo}. <b>El Congreso acordó su derogación el 2-oct-2026</b> (art. 86.2 CE), de modo que <b>sus medidas quedan sin efecto</b>. La <b>referencia</b> es el último dato disponible de cada serie <b>en su propio periodo</b> (no una fecha de corte): precios (IPV/IPVA), lanzamientos (CGPJ), ejecuciones (INE) y viviendas turísticas (VUT).</p>
{_tabla_control}
<p class="mut" style="font-size:.8rem">⚠️ <b>Los RDL fueron derogados por el Congreso el 2-oct-2026</b>, por lo que <b>no cabe atribuir a sus medidas</b> ningún cambio posterior en las series; este bloque se conserva como registro metodológico. Los datos publicados describen periodos anteriores a los RDL; la primera lectura posterior (4T-2026) llegará en <b>~feb-2027</b>.</p>{_descarga("punto-control")}</div>

<h2 id="comparador"><span id="cmp-region">{E(region)}</span> frente a España</h2>
<div class="panel">
<p style="margin:0 0 10px"><label>Elige la comunidad: <select id="regsel">{_opts}</select></label></p>
<table><thead><tr><th>Indicador</th><th>Periodo</th><th class="num">España</th><th class="num">Región</th></tr></thead><tbody>{comp_rows}</tbody></table>
<p class="mut" style="font-size:.78rem;margin:8px 0 0">El IPV compara la variación anual de la región con la nacional; los lanzamientos, el trimestre más reciente del CGPJ.</p><p class="mut" style="font-size:.78rem;margin:8px 0 0">Páginas por comunidad: {_ccaa_links}.</p></div>

<h2 id="calendario">Calendario de publicaciones</h2>
<div class="panel">{cal}</div>

<h2 id="medidas">Normas registradas (BOE)</h2>
<div class="panel"><p class="mut" style="margin:0 0 12px;font-size:.85rem">Estado y fechas de cada norma registrada, con <b>aprobación</b>, <b>publicación</b> y <b>vigencia</b> por separado. El estado se actualiza solo con fuente oficial: la <b>Resolución del Congreso</b> —cuando se publica— sustituye a «pendiente» por el acuerdo real (convalidación o derogación).</p><p class="mut" style="margin:0 0 4px;font-size:.85rem"><b>Hitos</b> (fecha de aprobación):</p>{filas_med}<div class="grid" style="margin-top:12px">{ficha_html}</div>{marco_html}<p class="mut" style="margin:18px 0 8px;font-size:.85rem"><b>Otras disposiciones</b> del BOE (sección I) sobre vivienda, de los últimos 21 días.</p><div class="grid">{boe_html}</div>{_descarga("boe-vivienda")}</div>

<h2 id="zmrt">Zonas de mercado residencial tensionado <span>· Ley 12/2023, art. 18</span></h2>
<div class="panel">
<p style="font-size:.85rem;margin:0 0 10px">Una <b>ZMRT</b> la declara <b>cada comunidad autónoma</b> (habilita la contención de rentas de la Ley 12/2023). El Ministerio publica la relación <b>cada trimestre</b> en el BOE; no es una figura estatal única ni automática.</p>
<p style="font-size:.85rem;margin:0 0 6px"><b>CCAA que han declarado zonas</b> (acumulado): {_zm_decl}.</p>
{('<p style="font-size:.85rem;margin:0 0 4px"><b>Nuevas del último trimestre publicado</b>:</p><ul style="font-size:.85rem;margin:0 0 6px">' + _zm_nuevas + "</ul>") if _zm_nuevas else ""}
<p class="mut" style="font-size:.78rem;margin:8px 0 0">No se replica aquí la lista completa de municipios (es extensa y puede quedar desfasada): el dato oficial es la resolución {_zm_src} y el <a href="{E(_zm_mivau)}" target="_blank" rel="noopener">listado acumulado del MIVAU ↗</a>. Solo figuran las CCAA que han declarado; las demás, no constan.</p></div>

<h2 id="metodo">Método y límites</h2>
<div class="panel"><ul>
<li>Solo series <b>oficiales</b> con fuente, fecha y periodicidad visibles.</li>
<li>Precios notariales, registros y alquiler fiscal miden <b>momentos distintos</b>: no se combinan en un mismo gráfico.</li>
<li>El alquiler se publica como <b>(1) índice de variación (IPVA, INE)</b> —no es un precio por m²— y como <b>(2) alquiler de referencia por municipio (SERPAVI/MIVAU)</b>, que es la mediana de los <b>contratos/fianzas</b> (oficial), no el precio de oferta de los portales.</li>
<li><b>IRAV</b> (Índice de Referencia de Arrendamientos de Vivienda, INE, desde ene-2025): es el <b>índice legal para actualizar la renta</b> de contratos en zonas de mercado tensionado (Ley 12/2023), <b>no un precio</b>. Se cita en el calendario; el INE no lo expone aún en su API de datos, así que no se automatiza (fuente: <a href="https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&amp;cid=1254736177110&amp;menu=ultiDatos&amp;idp=1254735976607">INE</a>).</li>
<li><b>Precio de oferta de alquiler (portales):</b> no se publica. La muestra de anuncios disponible no permite una cifra defendible, y se prefiere no publicarla antes que publicar un número sin base suficiente. (Sí se publica el dato <b>oficial</b> de contratos, SERPAVI/MIVAU.)</li>
<li><b>Sin puntuaciones compuestas</b> ni atribuciones: «Subiendo/Estable/Bajando» compara el último dato con el anterior de la misma fuente.</li>
</ul>
<p class="mut" style="font-size:.82rem">Licencias: <b>INE</b> y datos del observatorio, CC BY 4.0; <b>CGPJ</b> (datos judiciales públicos), <b>BOE</b> y <b>MIVAU/SERPAVI</b>, reutilización citando la fuente. Generado {hoy}.</p></div>

<h2 id="apoyar">Apoyar</h2>
<div class="panel" style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
  <div style="flex:1;min-width:240px">Este observatorio es <b>independiente y sin publicidad</b>. Se mantiene con <b>donaciones puntuales</b> de quien lo encuentra útil. Sin ellas, no hay servicio.</div>
  <a href="https://ko-fi.com/m_castillo" target="_blank" rel="noopener" style="background:var(--accent);color:#fff;font-weight:700;padding:13px 24px;border-radius:10px;text-decoration:none;white-space:nowrap">☕ Apoyar en Ko-fi →</a>
</div>
</main>
<footer>Observatorio de la vivienda · microservicio de <a href="https://pruebapublica.com">pruebapublica.com</a> · datos solo de fuentes <b>públicas</b> (INE/CGPJ/BOE).<br>No analiza redes ni coordinación: solo hechos oficiales y su evolución · <a href="https://github.com/mcasrom/vivienda-osint" target="_blank" rel="noopener">código abierto</a> · v{VERSION}</footer>
<script>
var CMP={comp_json}, NAT={nat_json};
var sel=document.getElementById('regsel');
function f1(v){{return v.toFixed(1).replace('.',',')+' %';}}
function fi(v){{return v.toLocaleString('es-ES');}}
function upd(){{
  var d=CMP[sel.value]||{{}};
  document.getElementById('cmp-region').textContent=d.nombre||'';
  document.getElementById('cmp-ipv').innerHTML='<td>Compraventa (IPV, var. anual)</td><td>'+NAT.ipv_per+'</td><td class="num">'+NAT.ipv_txt+'</td><td class="num">'+(d.ipv!=null?f1(d.ipv):'sin dato')+'</td>';
  document.getElementById('cmp-lz').innerHTML='<td>Lanzamientos judiciales</td><td>'+NAT.lz_per+'</td><td class="num">'+NAT.lz_txt+'</td><td class="num">'+(d.lz!=null?fi(d.lz):'sin dato')+'</td>';
}}
sel.addEventListener('change',upd);
</script>
</body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    # robots + sitemap como ficheros reales
    with open(os.path.join(OUT_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: https://vivienda.pruebapublica.com/sitemap.xml\n")
    _urls = ["https://vivienda.pruebapublica.com/",
             "https://vivienda.pruebapublica.com/fuentes.html",
             "https://vivienda.pruebapublica.com/propiedad.html",
             "https://vivienda.pruebapublica.com/datos.html",
             "https://vivienda.pruebapublica.com/ccaa/"]
    _urls += [f"https://vivienda.pruebapublica.com/ccaa/{_slug(_n)}.html"
              for _c, _n in territorios.NOMBRE.items()]
    with open(os.path.join(OUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "".join(f"<url><loc>{u}</loc><lastmod>{hoy}</lastmod></url>\n" for u in _urls)
                + "</urlset>\n")
    with open(os.path.join(OUT_DIR, "fuentes.html"), "w", encoding="utf-8") as f:
        f.write(_fuentes_html())
    with open(os.path.join(OUT_DIR, "propiedad.html"), "w", encoding="utf-8") as f:
        f.write(_propiedad_html())
    with open(os.path.join(OUT_DIR, "datos.html"), "w", encoding="utf-8") as f:
        f.write(_datos_html(datasets))
    # páginas por CCAA + índice
    _cvd = {k: v for k, v in cv}
    _vtd = {k: v for k, v in vut}
    _tasd = {c: (l, e) for c, l, e in _tasas}
    _ccaa_pages = []
    for _cod, _nom in territorios.NOMBRE.items():
        _d = {"cv": _cvd.get(_nom), "lz": _lz_d.get(_nom), "eh": _eh_d.get(_nom), "vut": _vtd.get(_nom),
              "ipv": ine.ultimo(f"ipv_var_anual:{_cod}"), "lz_rate": _tasd.get(_nom, (None, None))[0],
              "eh_rate": _tasd.get(_nom, (None, None))[1], "per_cv": per_cv, "per_lz": per_lz,
              "per_eh": per_eh, "per_vut": per_vut, "per_ipv": per_ipv}
        _ccaa_pages.append((_cod, _nom, _d))
    os.makedirs(os.path.join(OUT_DIR, "ccaa"), exist_ok=True)
    for _cod, _nom, _d in _ccaa_pages:
        with open(os.path.join(OUT_DIR, "ccaa", _slug(_nom) + ".html"), "w", encoding="utf-8") as f:
            f.write(_ccaa_page(_nom, _d))
    with open(os.path.join(OUT_DIR, "ccaa", "index.html"), "w", encoding="utf-8") as f:
        f.write(_ccaa_index(_ccaa_pages))
    # RSS de cambios (normas + cambios de series)
    try:
        _hist = json.load(open(os.path.join(ROOT, "data", "historial.json"), encoding="utf-8"))
    except (OSError, ValueError):
        _hist = []
    with open(os.path.join(OUT_DIR, "cambios.xml"), "w", encoding="utf-8") as f:
        f.write(_cambios_xml(_REGN["normas"], _hist, hoy))
    print(f"[gen] index + fuentes + propiedad + datos + {len(datasets)} series (CSV/JSON) · IPV={len(ipv)} pts · EH CCAA={len(eh)} · alquiler SERPAVI {_serp_n} municipios (oferta de portales NO publicable: muestra de {v['n']})")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=_OUT_DIR_DEF,
                    help=f"directorio de salida relativo a ROOT (def. {_OUT_DIR_DEF}; staging: web_tmp)")
    a = ap.parse_args()
    if os.sep in a.out or a.out in ("..", ".", "/"):
        import sys as _sys
        print(f"[gen] --out no puede contener rutas: {a.out!r}", file=_sys.stderr)
        _sys.exit(2)
    globals().update(
        OUT_DIR=os.path.join(ROOT, a.out),
        OUT=os.path.join(ROOT, a.out, "index.html"),
        DATA_DIR=os.path.join(ROOT, a.out, "data"))
    build()
