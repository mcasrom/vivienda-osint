"""Genera la página estática del microservicio Vivienda (visual: KPIs + gráficos SVG)."""
from __future__ import annotations
import os, sys, sqlite3, html
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import boe as boeing, via, ine  # noqa: E402

OUT = os.path.join(ROOT, "web", "index.html")
E = html.escape


def decretos(limite=12):
    c = sqlite3.connect(boeing.DB)
    return c.execute("SELECT fecha, titulo, url FROM boe ORDER BY fecha DESC LIMIT ?", (limite,)).fetchall()


def n_boe():
    c = sqlite3.connect(boeing.DB)
    return c.execute("SELECT COUNT(*) FROM boe").fetchone()[0]


def _eur(v):
    return f"{v:,.0f} €".replace(",", ".") if v is not None else "—"


def _kpi(valor, etiqueta, extra=""):
    return f'<div class="kpi"><div class="k">{valor}</div><div class="l">{etiqueta}</div>{extra}</div>'


def svg_bars(pares, color="#0f766e", h=200, w=780):
    if not pares:
        return "<p class='mut'>sin datos</p>"
    mx = max(v for _, v in pares) or 1
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    rowh = h / len(pares)
    bw = w * 0.52
    for i, (lab, v) in enumerate(pares):
        y = i * rowh + rowh * 0.16
        bh = rowh * 0.68
        ww = max(2, v / mx * bw)
        out.append(f'<rect x="0" y="{y:.1f}" width="{ww:.1f}" height="{bh:.1f}" rx="3" fill="{color}"/>')
        out.append(f'<text x="6" y="{y+bh*0.72:.1f}" font-size="11" fill="#fff" font-weight="600">{E(lab)}</text>')
        out.append(f'<text x="{ww+6:.1f}" y="{y+bh*0.72:.1f}" font-size="11" fill="#334155">{_eur(v)}/m²</text>')
    out.append("</svg>")
    return "".join(out)


def svg_line(serie, color="#0f766e", w=780, h=200):
    if len(serie) < 2:
        return "<p class='mut'>sin serie</p>"
    ys = [v for _, v in serie]
    mn, mx = min(ys), max(ys)
    rng = (mx - mn) or 1
    n = len(serie)
    pts = []
    for i, (a, v) in enumerate(serie):
        x = 40 + i * (w - 80) / (n - 1)
        y = h - 30 - (v - mn) / rng * (h - 60)
        pts.append((x, y, a, v))
    poly = " ".join(f"{x:.0f},{y:.0f}" for x, y, _, _ in pts)
    area = f"40,{h-30} " + poly + f" {pts[-1][0]:.0f},{h-30}"
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="width:100%">']
    out.append(f'<polygon points="{area}" fill="{color}18"/>')
    out.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    for x, y, a, v in pts:
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="2.6" fill="{color}"/>')
    for k, (x, y, a, v) in enumerate(pts):
        if k % max(1, n // 7) == 0 or k == n - 1:
            out.append(f'<text x="{x:.0f}" y="{h-10}" font-size="10" fill="#64748b" text-anchor="middle">{a}</text>')
    out.append(f'<text x="40" y="{h-30-(ys[-1]-mn)/rng*(h-60)-8:.0f}" font-size="11" fill="{color}" font-weight="700">{ys[-1]:.1f}</text>')
    out.append("</svg>")
    return "".join(out)


def build():
    b = decretos()
    v = via.resumen()
    rows = v["rows"]
    hoy = date.today().isoformat()
    top = rows[:14]
    caro = rows[0] if rows else ("—", "", None, None, "", "")
    ipva = ine.serie("ipva_indice")
    var = ine.serie("ipva_var_anual")
    var_ult = var[-1][1] if var else None
    flecha = ""
    if var_ult is not None:
        flecha = f'<div class="trend {"up" if var_ult>=0 else "down"}">{"▲" if var_ult>=0 else "▼"} {abs(var_ult):.1f}% anual</div>'

    kpis = "".join([
        _kpi(_eur(v["mediana"]) + "<small>/m²</small>", "Alquiler mediana (España)"),
        _kpi(str(v["n"]), "Municipios con dato"),
        _kpi(str(n_boe()), "Disposiciones de vivienda (BOE)"),
        _kpi(E(caro[0]) + f"<small>{_eur(caro[2])}/m²</small>", "Municipio más caro"),
        _kpi(_eur(v["mediana"] * 80 if v["mediana"] else None), "Piso 80 m² (mediana)", flecha),
    ])

    filas_b = "\n".join(
        f'<div class="card"><div class="fecha">{E(f)}</div><div class="tit">{E(t)}</div>'
        + (f'<a class="src" href="{E(u)}" target="_blank" rel="noopener">BOE ↗</a>' if u else "")
        + "</div>" for f, t, u in b) or "<p>Aún sin disposiciones capturadas.</p>"

    filas_v = "\n".join(
        f'<tr><td><b>{E(m)}</b></td><td class="mut">{E(p)}</td><td class="num">{_eur(e)}</td><td class="num">{_eur(a)}</td></tr>'
        for m, p, e, a, _s, _c in top)

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vivienda en España — datos y decretos</title>
<meta name="description" content="Cuánto cuesta el alquiler por municipio, la evolución de los precios (INE), los decretos de vivienda (BOE) y cómo participar. Datos abiertos, cívico y neutral.">
<link rel="canonical" href="https://vivienda.pruebapublica.com/">
<meta property="og:title" content="Vivienda en España — datos y decretos">
<meta property="og:description" content="Precio del alquiler por municipio, evolución INE, decretos BOE y cómo participar.">
<meta property="og:type" content="website">
<meta property="og:image" content="https://vivienda.pruebapublica.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<style>
:root{{--ink:#0f172a;--mut:#64748b;--accent:#0f766e;--line:#e2e8f0;--bg:#f1f5f9;--card:#fff}}
*{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}}
.hero{{background:linear-gradient(135deg,#0f766e,#0e7490 70%,#0369a1);color:#fff;padding:44px 20px 56px}}
.wrap{{max-width:1040px;margin:0 auto;padding:0 20px}} .hero h1{{font-size:2.1rem;margin:0 0 8px;letter-spacing:-.01em}} .hero p{{margin:0;opacity:.94;max-width:700px;font-size:1.02rem}}
.brand{{font-size:.82rem;opacity:.9;margin-bottom:16px}} .brand a{{color:#fff;font-weight:600;text-decoration:none}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;max-width:1040px;margin:-34px auto 0;padding:0 20px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:0 4px 14px #0f172a14}}
.kpi .k{{font-size:1.3rem;font-weight:800;color:var(--accent);line-height:1.2}} .kpi .k small{{font-size:.68rem;color:var(--mut);font-weight:600}}
.kpi .l{{font-size:.74rem;color:var(--mut)}} .trend{{font-size:.72rem;font-weight:700;margin-top:2px}} .trend.up{{color:#b91c1c}} .trend.down{{color:#15803d}}
main{{max-width:1040px;margin:0 auto;padding:34px 20px 60px}}
h2{{font-size:1.2rem;margin:36px 0 12px}} h2 span{{color:var(--mut);font-weight:400;font-size:.85rem}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} .mut{{color:var(--mut)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}}
.card .fecha{{font-size:.7rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.04em}}
.card .tit{{font-size:.88rem}} .card .src{{font-size:.76rem;color:var(--accent);text-decoration:none}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}} th{{text-align:left;padding:8px 10px;border-bottom:2px solid var(--accent);color:var(--mut);font-size:.74rem;text-transform:uppercase}}
td{{padding:8px 10px;border-bottom:1px solid var(--line)}} .num{{text-align:right;font-variant-numeric:tabular-nums}}
footer{{max-width:1040px;margin:0 auto;padding:24px 20px 50px;font-size:.8rem;color:var(--mut)}} footer a{{color:var(--accent)}}
@media(max-width:820px){{.kpis{{grid-template-columns:repeat(2,1fr)}} .grid{{grid-template-columns:1fr}}}}
</style></head><body>
<header class="hero"><div class="wrap">
<div class="brand">🏠 <b>Vivienda</b> · <a href="https://pruebapublica.com">pruebapublica.com</a> · datos abiertos, cívico y neutral</div>
<h1>La vivienda en España, en datos</h1>
<p>Cuánto cuesta el alquiler y <b>dónde</b>, cómo <b>evoluciona</b>, qué cambian los <b>decretos</b> (con enlace al BOE) y cómo participar. Solo hechos, con fuente. Sin análisis de quién lo mueve.</p>
</div></header>
<div class="kpis">{kpis}</div>
<main>
<h2>Precio del alquiler por municipio <span>· €/m² · top 14</span></h2>
<div class="panel">{svg_bars([(m, e) for m, p, e, a, s, c in top])}</div>
<table style="margin-top:14px"><thead><tr><th>Municipio</th><th>Provincia</th><th class="num">€/m²</th><th class="num">Piso 80 m²</th></tr></thead><tbody>{filas_v}</tbody></table>
<p class="mut" style="font-size:.8rem">Fuente: anuncios de alquiler activos (Índice VIA).{" Datos a " + E(str(v["fecha"])) + "." if v["fecha"] else ""} {v["n"]} municipios. <a href="https://municipal.viajeinteligencia.com/alquiler.html">Ver el mapa completo ↗</a></p>

<h2>Evolución de los precios (INE)</h2>
<div class="panel">{svg_line(ipva) if ipva else "<p class='mut'>serie sin cargar</p>"}
<p class="mut" style="font-size:.8rem">Índice de Precios de Vivienda (IPVA, base 2015=100), nivel nacional. Fuente: <a href="https://www.ine.es/">INE</a>.</p></div>

<h2>Decretos y disposiciones de vivienda (BOE)</h2>
<div class="grid">{filas_b}</div>

<h2>Cómo participar</h2>
<div class="panel"><ul>
<li><b>Alegaciones y consulta pública</b>: en <a href="https://www.mivau.gob.es/">MIVAU</a> y el <a href="https://www.boe.es/">BOE</a>.</li>
<li><b>Defensa de derechos</b>: consumo (OCU/FACUA) y servicios sociales municipales.</li>
<li><b>Transparencia</b>: <a href="https://transparencia.gob.es/">portal de transparencia</a>.</li>
</ul></div>
</main>
<footer>Microservicio <b>Vivienda</b> · información cívica neutral · datos solo de fuentes <b>públicas</b> (BOE/INE/VIA) · generado {hoy}.<br>
Esto <b>no</b> analiza redes ni coordinación: solo hechos y su impacto.</footer>
</body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[gen] {OUT} · {len(b)} decretos · {v['n']} municipios · IPVA={len(ipva)} pts")


if __name__ == "__main__":
    build()
