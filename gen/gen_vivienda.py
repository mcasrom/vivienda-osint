"""Observatorio de la vivienda — página estática (aproxima la maqueta, cívico y neutral).

Estructura: Indicadores · IPV · Alquiler · Mapa de calor provincial · Comparador España↔región ·
Calendario · Registro de medidas · Método y límites. Sin puntuaciones compuestas.
"""
from __future__ import annotations
import os, sys, sqlite3, html, json
from datetime import date
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import boe as boeing, via, ine, cgpj  # noqa: E402

OUT = os.path.join(ROOT, "web", "index.html")
E = html.escape

# Registro de medidas (se anotan sobre las series; NO se afirma causalidad).
MEDIDAS = [
    ("2023-05-25", "Ley 12/2023 por el derecho a la vivienda", "https://www.boe.es/buscar/act.php?id=BOE-A-2023-12203"),
    ("2026-09-29", "RDL 26/2026 — función social de la vivienda", "https://www.boe.es/"),
    ("2026-09-29", "RDL 27/2026 — medidas urgentes de vivienda", "https://www.boe.es/"),
]
CALENDARIO = [
    ("16/10/2026", "CGPJ — lanzamientos del 2.º trimestre"),
    ("14/12/2026", "CGPJ — lanzamientos del 3.er trimestre"),
    ("Cada mes", "INE — compraventas inscritas e IRAV (el de agosto, 15/09)"),
]


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


def _ind(valor, unidad, tend, etq_tend, fuente, periodo):
    cls = {"subiendo": "up", "bajando": "down", "estable": ""}.get(tend, "")
    fl = {"subiendo": "▲", "bajando": "▼", "estable": "▬"}.get(tend, "")
    return (f'<div class="ind"><div class="v">{valor}<small>{unidad}</small></div>'
            f'<div class="t {cls}">{fl} {etq_tend}</div><div class="f">{etiqueta_src(fuente, periodo)}</div></div>')


def etiqueta_src(f, p):
    return f'{f}<br><span class="mut">{p}</span>'


def svg_line(serie, color="#0f766e", w=780, h=210, marcas=()):
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
    out.append(f'<text x="{pts[-1][0]+6:.0f}" y="{pts[-1][1]+4:.0f}" font-size="12" fill="{color}" font-weight="700">{_pct(ys[-1])}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_bars(pares, color="#0f766e", h=200, w=780):
    if not pares:
        return "<p class='mut'>sin datos</p>"
    mx = max(v for _, v in pares) or 1
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    rowh = h / len(pares)
    bw = w * 0.5
    for i, (lab, v) in enumerate(pares):
        y = i * rowh + rowh * 0.16
        bh = rowh * 0.68
        ww = max(2, v / mx * bw)
        c = "#dc2626" if v >= 8 else "#f59e0b" if v >= 5 else "#16a34a"
        out.append(f'<rect x="0" y="{y:.1f}" width="{ww:.1f}" height="{bh:.1f}" rx="3" fill="{c}"/>')
        out.append(f'<text x="6" y="{y+bh*0.72:.1f}" font-size="11" fill="#fff" font-weight="600">{E(lab)}</text>')
        out.append(f'<text x="{ww+6:.1f}" y="{y+bh*0.72:.1f}" font-size="11" fill="#334155">{_eur(v)}/m²</text>')
    out.append("</svg>")
    return "".join(out)


def heatmap_provincias(rows, w=780):
    """Rejilla de provincias coloreada por mediana €/m²."""
    prov = defaultdict(list)
    for m, p, e, a, s, c in rows:
        if e:
            prov[p].append(e)
    dat = sorted(((p, sorted(v)[len(v) // 2]) for p, v in prov.items()), key=lambda x: -x[1])
    if not dat:
        return "<p class='mut'>sin datos</p>"
    mx = max(v for _, v in dat) or 1
    mn = min(v for _, v in dat)
    cols = 6
    cell = 118
    rowh = 46
    rh = ((len(dat) + cols - 1) // cols) * rowh + 8
    out = [f'<svg viewBox="0 0 {w} {rh}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    for i, (p, v) in enumerate(dat):
        r, cc = divmod(i, cols)
        t = (v - mn) / ((mx - mn) or 1)
        R = int(22 + t * (220 - 22)); G = int(163 - t * (163 - 38)); B = int(74 - t * (74 - 38))
        x = cc * (w / cols); y = r * rowh
        out.append(f'<rect x="{x+2:.0f}" y="{y+2:.0f}" width="{w/cols-4:.0f}" height="{rowh-4}" rx="5" fill="rgb({R},{G},{B})"/>')
        lbl = E(p if len(p) <= 16 else p[:15] + "…")
        out.append(f'<text x="{x+8:.0f}" y="{y+rowh*0.55:.0f}" font-size="10.5" fill="#fff" font-weight="600">{lbl}</text>')
        out.append(f'<text x="{x+8:.0f}" y="{y+rowh*0.85:.0f}" font-size="9.5" fill="#ffffffcc">{_eur(v)}/m²</text>')
    out.append("</svg>")
    return "".join(out)


def build():
    v = via.resumen()
    rows = v["rows"]
    hoy = date.today().isoformat()
    region = "Murcia"

    ipv = ine.serie("ipv_var_anual")
    ipv_ult = ine.ultimo("ipv_var_anual")
    nueva = ine.ultimo("ipv_nueva_var")
    seg = ine.ultimo("ipv_segunda_var")
    eh, eh_anyo, eh_total = ine.eh_ccaa()
    lz, lz_per, lz_total = cgpj.por_ccaa()
    lz_crono = " · ".join(f"{p} <b>{int(v):,}</b>".replace(",", ".") for p, v in cgpj.cronologia() if v)
    lz_bars = "".join(f'<tr><td>{E(a)}</td><td class="num">{int(v):,}</td></tr>'.replace(",", ".") for a, v in lz[:12])
    eh_nac = ine.eh_nacional()
    eh_crono = " · ".join(f"{a} <b>{int(v):,}</b>".replace(",", ".") for a, v in eh_nac)
    ipva = ine.serie("ipva_indice")

    tend, _ = _tendencia(ipv)
    ipva_s = ine.serie("ipva_var_anual")
    ipva_var = ipva_s[-1][1] if ipva_s else None
    tend_ia, _ = _tendencia(ipva_s)
    inds = "".join([
        _ind(_pct(ipv_ult), "", tend, {"subiendo": "Subiendo", "bajando": "Bajando", "estable": "Estable"}[tend],
             "INE · IPV (compraventa)", "variación anual" + (f" · nueva {_pct(nueva)}, 2.ª mano {_pct(seg)}" if nueva and seg else "")),
        _ind(_pct(ipva_var), "", tend_ia, {"subiendo": "Subiendo", "bajando": "Bajando", "estable": "Estable"}[tend_ia],
             "INE · IPVA (alquiler)", "variación anual"),
        _ind((f"{int(lz_total):,}".replace(",", ".") if lz_total else "—"), "", "estable",
             (lz_per or "—"), "CGPJ · lanzamientos (desahucios)", "trimestral"),
        _ind((f"{int(eh_total):,}".replace(",", ".") if eh_total else "—"), "", "estable",
             (str(eh_anyo) if eh_anyo else "—"), "INE · ejecuciones hipotecarias", "anual"),
        _ind(_eur(v["mediana"]) + "<small>/m²</small>", "", "estable", "Actual", "VIA · alquiler mediano", "anual"),
    ])

    eh_bars = "".join(
        f'<tr><td>{E(k)}</td><td class="num">{int(v):,}</td>'.replace(",", ".") + "</tr>"
        for k, v in eh[:12])

    # comparador España vs región
    prov = defaultdict(list)
    for m, p, e, a, s, c in rows:
        if e:
            prov[p].append(e)
    esp_med = v["mediana"]
    reg_provs = sorted([p for p in prov if region.lower() in p.lower()]) or [region]
    reg_med = None
    for p in reg_provs:
        if prov[p]:
            reg_med = sorted(prov[p])[len(prov[p]) // 2]
    comp_rows = "".join(
        f'<tr><td>Alquiler €/m² (anuncios)</td><td>{E(str(v["fecha"]))}</td><td class="num">{_eur(esp_med)}</td><td class="num">{_eur(reg_med) if reg_med else "sin dato"}</td></tr>'
        f'<tr><td>Compraventa (IPV, var. anual)</td><td>trimestral</td><td class="num">{_pct(ipv_ult)}</td><td class="num mut">pendiente CCAA</td></tr>'
        f'<tr><td>Lanzamientos judiciales</td><td>2T 2026</td><td class="num mut">—</td><td class="num mut">16/10/2026</td></tr>')

    filas_med = "".join(
        f'<div class="m"><span class="d">{E(d)}</span> <b>{E(t)}</b> '
        + (f'<a class="src" href="{E(u)}" target="_blank" rel="noopener">fuente ↗</a>' if u else "")
        + "</div>" for d, t, u in MEDIDAS)
    cal = "".join(f'<div class="m"><span class="d">{E(d)}</span> {E(t)}</div>' for d, t in CALENDARIO)
    # medidas nuevas del BOE
    c = sqlite3.connect(boeing.DB)
    boe_rows = c.execute("SELECT fecha, titulo, url FROM boe ORDER BY fecha DESC LIMIT 8").fetchall()
    boe_html = "".join(
        f'<div class="card"><div class="fecha">{E(f)}</div><div class="tit">{E(t)}</div>'
        + (f'<a class="src" href="{E(u)}" target="_blank" rel="noopener">BOE ↗</a>' if u else "")
        + "</div>" for f, t, u in boe_rows)

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Observatorio de la vivienda — datos oficiales</title>
<meta name="description" content="Qué dicen los datos oficiales de vivienda (INE, CGPJ, MIVAU, BOE), sin puntuaciones ni atribuciones. Precio, alquiler, compraventas, lanzamientos y medidas. Mapa de calor y comparador.">
<link rel="canonical" href="https://vivienda.pruebapublica.com/">
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
<meta name="twitter:description" content="Precio del alquiler por municipio, evolución (INE), decretos (BOE) y desahucios (CGPJ) por CCAA.">
<meta name="twitter:image" content="https://vivienda.pruebapublica.com/og.png">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Dataset","name":"Observatorio de la vivienda",
"description":"Datos oficiales de vivienda en España: precio del alquiler por municipio (VIA), evolución de precios (INE), ejecuciones hipotecarias y lanzamientos por CCAA (INE/CGPJ), y registro de medidas (BOE).",
"url":"https://vivienda.pruebapublica.com/","creator":{{"@type":"Organization","name":"pruebapublica.com"}},
"license":"https://creativecommons.org/licenses/by/4.0/","isAccessibleForFree":true,
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
<a href="#indicadores">Indicadores</a><a href="#mapa">Mapa</a><a href="#comparador">Comparador</a><a href="#calendario">Calendario</a><a href="#medidas">Medidas</a><a href="#metodo">Método</a><a href="#apoyar">Apoyar</a>
<a href="https://pruebapublica.com" style="opacity:.7">pruebapublica.com</a></div></nav>
<header class="hero"><div class="wrap">
<h1>Qué dicen los datos oficiales de vivienda, sin puntuaciones ni atribuciones</h1>
<p>Cada cifra lleva su unidad, su fuente y su fecha. Las medidas políticas se anotan sobre las series, pero el observatorio <b>no afirma</b> que una medida causara un cambio.</p>
</div></header>
<div class="inds" id="indicadores">{inds}</div>
<main>
<h2>Precio de compraventa de vivienda, variación anual <span>· IPV nacional (INE)</span></h2>
<div class="panel">{svg_line(ipv)}<p class="mut" style="font-size:.8rem">Índice de Precios de Vivienda (IPV), total nacional, variación anual (%). Fuente: <a href="https://www.ine.es/">INE</a>. Las medidas del BOE se registran abajo.</p></div>

<h2>Mapa de calor: precio del alquiler por provincia <span>· €/m²</span></h2>
<div class="panel">{heatmap_provincias(rows)}<p class="mut" style="font-size:.8rem">Mediana de anuncios activos por provincia (Índice VIA). Verde = más barato · rojo = más caro.{" Datos a " + E(str(v["fecha"])) + "." if v["fecha"] else ""} <a href="https://municipal.viajeinteligencia.com/alquiler.html">Detalle por municipio ↗</a></p></div>

<h2>Ejecuciones hipotecarias de vivienda por CCAA <span>· INE{f" · {eh_anyo}" if eh_anyo else ""}</span></h2>
<div class="panel"><table><thead><tr><th>Comunidad autónoma</th><th class="num">Viviendas</th></tr></thead><tbody>{eh_bars or "<tr><td>sin datos</td><td></td></tr>"}</tbody></table>
<p style="font-size:.85rem;margin:8px 0"><b>Cronología nacional:</b> {eh_crono or "sin serie"}</p>
<p class="mut" style="font-size:.8rem">Ejecuciones hipotecarias <b>iniciadas sobre vivienda</b>, por comunidad autónoma. <b>Total nacional {int(eh_total):,}</b>. Fuente: <a href="https://www.ine.es/">INE</a> (Estadística de Ejecuciones Hipotecarias).</p>
<p class="mut" style="font-size:.8rem">Nota: los <b>lanzamientos (desahucios)</b> los publica el <b>CGPJ</b> (trimestral; próximo dato 16-oct-2026) — pendiente de conectar. Aquí se usa la serie INE de ejecuciones hipotecarias (oficial y abierta).</p></div>

<h2>Lanzamientos (desahucios) por CCAA <span>· CGPJ{f" · {lz_per}" if lz_per else ""}</span></h2>
<div class="panel"><table><thead><tr><th>Comunidad autónoma</th><th class="num">Lanzamientos</th></tr></thead><tbody>{lz_bars or "<tr><td>sin datos</td><td></td></tr>"}</tbody></table>
<p style="font-size:.85rem;margin:8px 0"><b>Cronología nacional:</b> {lz_crono or "sin serie"}</p>
<p class="mut" style="font-size:.8rem">Lanzamientos <b>practicados</b> (acto material de desalojo), por comunidad autónoma. Total {lz_per}: <b>{int(lz_total):,}</b>. Fuente: <a href="https://www.poderjudicial.es/">CGPJ</a> (Efecto de la crisis en los órganos judiciales, trimestral).</p></div>

<h2 id="comparador">{E(region)} frente a España</h2>
<div class="panel"><table><thead><tr><th>Indicador</th><th>Periodo</th><th class="num">España</th><th class="num">{E(region)}</th></tr></thead><tbody>{comp_rows}</tbody></table></div>

<h2 id="calendario">Calendario de publicaciones</h2>
<div class="panel">{cal}</div>

<h2 id="medidas">Registro de medidas (BOE)</h2>
<div class="panel">{filas_med}<div class="grid" style="margin-top:12px">{boe_html}</div></div>

<h2 id="metodo">Método y límites</h2>
<div class="panel"><ul>
<li>Solo series <b>oficiales</b> con fuente, fecha y periodicidad visibles.</li>
<li>Precios notariales, registros y alquiler fiscal miden <b>momentos distintos</b>: no se combinan en un mismo gráfico.</li>
<li>El alquiler oficial procede de datos <b>tributarios</b> (retraso anual). <b>No</b> se usan precios de oferta de portales en las series oficiales.</li>
<li><b>Sin puntuaciones compuestas</b> ni atribuciones: «Subiendo/Estable/Bajando» compara el último dato con el anterior de la misma fuente.</li>
</ul>
<p class="mut" style="font-size:.82rem">El mapa de calor usa anuncios de alquiler activos (Índice VIA) — es indicativo, no una serie oficial. Licencias de reutilización de INE/CGPJ/MIVAU por confirmar. Generado {hoy}.</p></div>

<h2 id="apoyar">Apoyar</h2>
<div class="panel" style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
  <div style="flex:1;min-width:240px">Este observatorio es <b>independiente y sin publicidad</b>. Se mantiene con <b>donaciones puntuales</b> de quien lo encuentra útil. Sin ellas, no hay servicio.</div>
  <a href="https://ko-fi.com/m_castillo" target="_blank" rel="noopener" style="background:var(--accent);color:#fff;font-weight:700;padding:13px 24px;border-radius:10px;text-decoration:none;white-space:nowrap">☕ Apoyar en Ko-fi →</a>
</div>
</main>
<footer>Observatorio de la vivienda · microservicio de <a href="https://pruebapublica.com">pruebapublica.com</a> · datos solo de fuentes <b>públicas</b> (INE/CGPJ/MIVAU/BOE/VIA).<br>No analiza redes ni coordinación: solo hechos oficiales y su evolución.</footer>
</body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    # robots + sitemap como ficheros reales
    with open(os.path.join(ROOT, "web", "robots.txt"), "w", encoding="utf-8") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: https://vivienda.pruebapublica.com/sitemap.xml\n")
    with open(os.path.join(ROOT, "web", "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                f'<url><loc>https://vivienda.pruebapublica.com/</loc><lastmod>{hoy}</lastmod></url>\n</urlset>\n')
    print(f"[gen] {OUT} · IPV={len(ipv)} pts · EH CCAA={len(eh)} · provincias · {v['n']} municipios")


if __name__ == "__main__":
    build()
