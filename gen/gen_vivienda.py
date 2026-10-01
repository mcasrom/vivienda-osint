"""Genera la página estática del microservicio Vivienda (HTML self-contained)."""
from __future__ import annotations
import os, sys, sqlite3, html
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import boe as boeing, via  # noqa: E402

OUT = os.path.join(ROOT, "web", "index.html")
E = html.escape


def decretos(limite=12):
    c = sqlite3.connect(boeing.DB)
    rows = c.execute("SELECT fecha, titulo, url FROM boe ORDER BY fecha DESC LIMIT ?", (limite,)).fetchall()
    return rows


def _eur(v):
    return f"{v:,.0f} €".replace(",", ".") if v is not None else "—"


def build():
    b = decretos()
    v = via.resumen()
    hoy = date.today().isoformat()

    filas_b = "\n".join(
        f'<li><b>{E(f)}</b> — {"<a href='" + E(u) + "' target=_blank rel=noopener>BOE ↗</a>" if u else ""}<br><span class="t">{E(t)}</span></li>'
        for f, t, u in b) or "<li>Aún sin disposiciones de vivienda capturadas.</li>"

    top = v["rows"][:15]
    filas_v = "\n".join(
        f'<tr><td>{E(m)}</td><td class="mut">{E(p)}</td><td class="num">{_eur(e)}</td><td class="num">{_eur(a)}</td></tr>'
        for m, p, e, a, _s, _c in top) or "<tr><td colspan=4>Sin datos de precios.</td></tr>"

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vivienda en España — información cívica</title>
<meta name="description" content="Qué cambian los decretos de vivienda, cuánto cuesta el alquiler por municipio y cómo participar. Información cívica neutral, con fuentes (BOE/INE).">
<style>
:root{{--ink:#1e293b;--mut:#64748b;--accent:#0f766e;--line:#e2e8f0;--bg:#f8fafc}}
*{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--ink);background:var(--bg);line-height:1.6}}
.wrap{{max-width:880px;margin:0 auto;padding:28px 20px 60px}} .brand{{font-size:.85rem;color:var(--mut);margin-bottom:22px}}
.brand a{{color:var(--accent);text-decoration:none;font-weight:600}}
h1{{font-size:1.7rem;margin:0 0 4px}} h2{{font-size:1.1rem;margin:30px 0 8px;padding-bottom:5px;border-bottom:2px solid var(--line)}}
p,li,td{{font-size:.94rem}} .lead{{color:#334155}}
table{{width:100%;border-collapse:collapse;font-size:.86rem;margin:8px 0}} th{{text-align:left;padding:7px 10px;border-bottom:2px solid var(--accent);background:#f1f5f9}}
td{{padding:7px 10px;border-bottom:1px solid var(--line)}} .num{{text-align:right;font-variant-numeric:tabular-nums}} .mut{{color:var(--mut)}}
.t{{color:var(--mut)}} ul{{padding-left:20px}} .box{{margin:14px 0;padding:12px 16px;background:#ecfdf5;border-left:4px solid var(--accent);border-radius:6px;font-size:.9rem}}
footer{{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);font-size:.8rem;color:var(--mut)}}
</style></head><body><div class="wrap">
<div class="brand">🏠 <b>Vivienda</b> · pruebapublica.com · <a href="https://municipal.viajeinteligencia.com/alquiler.html">precios por municipio ↗</a></div>
<h1>La vivienda en España, en datos</h1>
<p class="lead">Qué cambian los decretos, cuánto cuesta el alquiler y dónde, y cómo participar.
Información <b>cívica y neutral</b>: solo hechos con <b>fuente enlazada</b> (BOE/INE). Sin análisis de quién lo mueve.</p>

<h2>1. Decretos y disposiciones sobre vivienda (BOE)</h2>
<ul>{filas_b}</ul>
<p class="mut" style="font-size:.82rem">Fuente: <a href="https://www.boe.es/datosabiertos/">BOE — datos abiertos</a>. Se listan las disposiciones del sumario diario que mencionan vivienda/alquiler/desahucio.</p>

<h2>2. Precio del alquiler por municipio (€/m²)</h2>
<table><thead><tr><th>Municipio</th><th>Provincia</th><th class="num">€/m²</th><th class="num">Piso 80 m²</th></tr></thead>
<tbody>{filas_v}</tbody></table>
<p class="mut" style="font-size:.82rem">Fuente: anuncios de alquiler activos (Índice VIA).{" · datos a " + E(str(v["fecha"])) if v["fecha"] else ""}.
Mediana estatal ≈ <b>{_eur(v["mediana"])}</b> €/m² · {v["n"]} municipios. <a href="https://municipal.viajeinteligencia.com/alquiler.html">Ver todos ↗</a></p>

<h2>3. Cómo participar</h2>
<ul>
<li><b>Alegaciones y consulta pública</b>: los proyectos normativos se publican en <a href="https://www.mivau.gob.es/">MIVAU</a> y en el <a href="https://www.boe.es/">BOE</a>.</li>
<li><b>Defensa de derechos</b>: consumo (OCU/FACUA), servicios sociales municipales.</li>
<li><b>Transparencia</b>: solicitudes vía <a href="https://transparencia.gob.es/">portal de transparencia</a>.</li>
</ul>

<footer>Microservicio <b>Vivienda</b> · información cívica neutral, datos solo de fuentes <b>públicas</b> ·
generado {hoy} · <a href="https://pruebapublica.com">pruebapublica.com</a><br>
Esto <b>no</b> analiza redes ni coordinación: solo hechos y su impacto.</footer>
</div></body></html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[gen] {OUT} · {len(b)} decretos · {v['n']} municipios")


if __name__ == "__main__":
    build()
