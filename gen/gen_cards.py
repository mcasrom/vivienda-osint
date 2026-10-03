"""Tarjetas por indicador (1200x630) + manifiesto para redes.

Genera una imagen por indicador en web/og/<slug>.png y un manifiesto
web/og/cards.json con el dato, la fuente/periodo y el texto sugerido para
Mastodon/Bluesky y para X (recordando que X cuenta el enlace como 23 chars).

Reutiliza el estilo del OG principal (gradiente + casa + cifra grande) y, como
aquel, comprueba que no hay solapes ni desbordes antes de aceptar la tarjeta.
"""
from __future__ import annotations
import os
import sys
import json
from datetime import date

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import ine, cgpj  # noqa: E402

OUT_DEF = "web"
SITE = "vivienda.pruebapublica.com"
X_LINK = 23  # X cuenta cualquier enlace como 23 chars


def _es_int(v):
    return f"{int(round(v)):,}".replace(",", ".")


def _es_dec(v):
    return f"{v:.1f}".replace(".", ",")


def indicadores():
    out = []
    s = ine.serie("ipv_var_anual")
    if s:
        out.append(dict(slug="ipv", kicker="PRECIO DE COMPRAVENTA", num=f"{s[-1][1]:+.1f} %".replace(".", ","),
                        label="variación anual del precio (IPV)",
                        source=f"INE · {s[-1][0]}",
                        frase=f"El precio de la vivienda sube un {_es_dec(s[-1][1])} % interanual"))
    s = ine.serie("ipva_var_anual")
    if s:
        out.append(dict(slug="ipva", kicker="ALQUILER", num=f"{s[-1][1]:+.1f} %".replace(".", ","),
                        label="variación anual del alquiler (IPVA)",
                        source=f"INE · {s[-1][0]}",
                        frase=f"El alquiler sube un {_es_dec(s[-1][1])} % interanual"))
    cv, cv_f, cv_tot = ine.cv_ccaa()
    if cv_tot:
        out.append(dict(slug="compraventas", kicker="COMPRAVENTAS", num=_es_int(cv_tot), label="compraventas de vivienda en España",
                        source=f"INE · {cv_f}",
                        frase=f"Se registraron {_es_int(cv_tot)} compraventas de vivienda ({cv_f})"))
    lz, lz_per, lz_tot = cgpj.por_ccaa()
    if lz_tot:
        out.append(dict(slug="lanzamientos", kicker="LANZAMIENTOS", num=_es_int(lz_tot), label="lanzamientos judiciales (desahucios)",
                        source=f"CGPJ · {lz_per}",
                        frase=f"{_es_int(lz_tot)} lanzamientos judiciales ({lz_per})"))
    eh, eh_anyo, eh_tot = ine.eh_ccaa()
    if eh_tot:
        out.append(dict(slug="ejecuciones", kicker="EJECUCIONES HIPOTECARIAS", num=_es_int(eh_tot), label="ejecuciones hipotecarias en España",
                        source=f"INE · {eh_anyo}",
                        frase=f"{_es_int(eh_tot)} ejecuciones hipotecarias ({eh_anyo})"))
    vut, vut_anyo, vut_tot, vut_pct = ine.vte_ccaa()
    if vut_tot:
        out.append(dict(slug="vut", kicker="VIVIENDAS TURÍSTICAS", num=_es_int(vut_tot), label="viviendas de uso turístico",
                        source=f"INE · {vut_anyo}",
                        frase=f"{_es_int(vut_tot)} viviendas de uso turístico en España ({vut_anyo})"))
    hpt = ine.hpt_serie()
    if hpt:
        out.append(dict(slug="hipotecas", kicker="HIPOTECAS", num=_es_int(hpt[-1][1]), label="hipotecas constituidas sobre viviendas",
                        source=f"INE · {hpt[-1][0]}",
                        frase=f"{_es_int(hpt[-1][1])} hipotecas sobre viviendas en un mes ({hpt[-1][0]})"))
    return out


def _texto(c):
    url = f"https://{SITE}/"
    masto = f"{c['frase']}.\n\nDato oficial con fuente y periodo: {url}\n#vivienda #datosabiertos"
    x_txt = f"{c['frase']}. Dato oficial: {url}"
    x_len = len(x_txt) - len(url) + X_LINK
    return masto, x_txt, x_len


def _card(out_path, c):
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1), extent=[0, 1, 0, 1], aspect="auto",
              cmap=LinearSegmentedColormap.from_list("b", ["#0b3b4a", "#0e7490", "#0ea5b7"]),
              origin="lower", zorder=0)
    ax.fill([0.6, 1.02, 1.02, 0.7], [0, 0, 1.05, 1.05], color="#ffffff", alpha=0.05, zorder=1)
    amber, roof = "#fbbf24", "#fde68a"
    ax.add_patch(Rectangle((0.085, 0.31), 0.145, 0.20, facecolor=amber, edgecolor="none", zorder=3))
    ax.add_patch(Polygon([[0.065, 0.51], [0.1575, 0.635], [0.25, 0.51]], closed=True,
                         facecolor=roof, edgecolor="none", zorder=3))
    ax.add_patch(Rectangle((0.141, 0.31), 0.033, 0.10, facecolor="#0b3b4a", edgecolor="none", zorder=4))
    ax.add_patch(Rectangle((0.107, 0.40), 0.033, 0.05, facecolor="#0b3b4a", edgecolor="none", zorder=4))
    ax.add_patch(Rectangle((0.176, 0.40), 0.033, 0.05, facecolor="#0b3b4a", edgecolor="none", zorder=4))

    ax.text(0.045, 0.905, c["kicker"], color="#67e8f9", fontsize=20, fontweight="bold", zorder=5)
    num = c["num"]
    fs = 100 if len(num) <= 4 else (80 if len(num) <= 6 else 64)
    t1 = ax.text(0.35, 0.66, num, color="#fbbf24", fontsize=fs, fontweight="bold", va="top", zorder=5)
    texts = [t1]
    t3 = ax.text(0.352, 0.30, c["label"], color="#a5f3fc", fontsize=24, zorder=5)
    t4 = ax.text(0.352, 0.205, c["source"], color="#a5f3fc", fontsize=18, zorder=5)
    texts += [t3, t4]
    ax.text(0.045, 0.075, SITE, color="#fde047", fontsize=22, fontweight="bold", zorder=5)

    fig.canvas.draw(); r = fig.canvas.get_renderer()
    W = fig.get_size_inches()[0] * fig.dpi
    H = fig.get_size_inches()[1] * fig.dpi
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a.get_window_extent(r).overlaps(b.get_window_extent(r)):
                ea, eb = a.get_window_extent(r), b.get_window_extent(r)
                raise SystemExit(f"card {c['slug']}: solape «{a.get_text()}» "
                                 f"({ea.x0:.0f},{ea.y0:.0f}-{ea.x1:.0f},{ea.y1:.0f}) / "
                                 f"«{b.get_text()}» ({eb.x0:.0f},{eb.y0:.0f}-{eb.x1:.0f},{eb.y1:.0f})")
    house = (0.055 * W, 0.29 * H, 0.265 * W, 0.655 * H)
    for a in texts:
        bb = a.get_window_extent(r)
        if bb.x1 > W or bb.x0 < 0 or bb.y1 > H or bb.y0 < 0:
            raise SystemExit(f"card {c['slug']}: texto fuera de lienzo «{a.get_text()}»")
        if bb.x0 < house[2] and bb.x1 > house[0] and bb.y0 < house[3] and bb.y1 > house[1]:
            raise SystemExit(f"card {c['slug']}: texto «{a.get_text()}» pisa la ilustración")
    fig.savefig(out_path, facecolor="#0b3b4a")
    plt.close(fig)


def build(out_dir=OUT_DEF):
    od = os.path.join(ROOT, out_dir, "og")
    os.makedirs(od, exist_ok=True)
    cards = []
    for c in indicadores():
        _card(os.path.join(od, c["slug"] + ".png"), c)
        masto, x_txt, x_len = _texto(c)
        cards.append({"slug": c["slug"], "img": f"/og/{c['slug']}.png", "kicker": c["kicker"],
                      "value": c["num"],
                      "label": c["label"], "source": c["source"],
                      "mastodon": masto, "x": x_txt, "x_len": x_len})
    man = {"generado": date.today().isoformat(), "sitio": SITE, "cards": cards}
    with open(os.path.join(od, "cards.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"[cards] {len(cards)} tarjetas -> {out_dir}/og/ · " + ", ".join(c["slug"] for c in cards))
    return cards


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEF)
    a = ap.parse_args()
    if os.sep in a.out or a.out in ("..", ".", "/"):
        print(f"[cards] --out no puede contener rutas: {a.out!r}", file=sys.stderr)
        raise SystemExit(2)
    build(a.out)
