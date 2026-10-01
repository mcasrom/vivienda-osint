"""OG de Vivienda — opción B: ILUSTRACIÓN (casa) + cifra grande. 1200x630."""
from __future__ import annotations
import os, sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
OUT = os.path.join(ROOT, "web", "og.png")


def datos():
    c = sqlite3.connect(DB)
    per = c.execute("SELECT MAX(periodo) FROM lanzamientos").fetchone()[0]
    tot = c.execute("SELECT valor FROM lanzamientos WHERE ambito='TOTAL' AND periodo=?", (per,)).fetchone()
    ipv = c.execute("SELECT etiqueta, valor FROM ine_serie WHERE serie='ipv_var_anual' "
                    "ORDER BY fecha DESC LIMIT 1").fetchone()
    return per, (tot[0] if tot else None), (ipv if ipv else (None, None))


def build():
    per, tot, (ipv_per, ipv_val) = datos()
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1), extent=[0, 1, 0, 1], aspect="auto",
              cmap=LinearSegmentedColormap.from_list("b", ["#0b3b4a", "#0e7490", "#0ea5b7"]), origin="lower", zorder=0)
    ax.fill([0.6, 1.02, 1.02, 0.7], [0, 0, 1.05, 1.05], color="#ffffff", alpha=0.05, zorder=1)

    # --- ILUSTRACIÓN: casa grande ---
    amber = "#fbbf24"; amber2 = "#f59e0b"; roof = "#fde68a"
    # cuerpo
    ax.add_patch(Rectangle((0.10, 0.30), 0.22, 0.30, facecolor=amber, edgecolor="none", zorder=3))
    # tejado
    ax.add_patch(Polygon([[0.07, 0.60], [0.21, 0.79], [0.35, 0.60]], closed=True, facecolor=roof, edgecolor="none", zorder=3))
    # puerta
    ax.add_patch(Rectangle((0.185, 0.30), 0.05, 0.15, facecolor="#0b3b4a", edgecolor="none", zorder=4))
    # ventana
    ax.add_patch(Rectangle((0.125, 0.44), 0.05, 0.07, facecolor="#0b3b4a", edgecolor="none", zorder=4))
    ax.add_patch(Rectangle((0.245, 0.44), 0.05, 0.07, facecolor="#0b3b4a", edgecolor="none", zorder=4))
    # chimenea
    ax.add_patch(Rectangle((0.29, 0.66), 0.025, 0.10, facecolor=amber2, edgecolor="none", zorder=3))

    # --- TEXTO ---
    ax.text(0.045, 0.905, "VIVIENDA · DATOS OFICIALES", color="#67e8f9", fontsize=15, fontweight="bold", zorder=5)
    if ipv_val is not None:
        num = f"{ipv_val:+.1f}".replace(".", ",")
        t1 = ax.text(0.40, 0.60, num, color="#fbbf24", fontsize=100, fontweight="bold", va="top", zorder=5)
        t2 = ax.text(0.828, 0.49, "%", color="#fbbf24", fontsize=58, fontweight="bold", va="center", zorder=5)
        t3 = ax.text(0.41, 0.235, "variación anual del precio", color="#a5f3fc", fontsize=23, zorder=5)
        t4 = ax.text(0.41, 0.155, f"de compraventa · INE · {ipv_per}", color="#a5f3fc", fontsize=17, zorder=5)
        _checks = ((t1, t2, "numero vs %"), (t1, t3, "numero vs etiqueta"), (t4, t3, "etiquetas"),)
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        for a, b, nombre in _checks:
            ba, bb = a.get_window_extent(r), b.get_window_extent(r)
            if ba.overlaps(bb):
                raise SystemExit(f"OG: solape {nombre} ({ba.x0:.0f}-{ba.x1:.0f} vs {bb.x0:.0f}-{bb.x1:.0f})")
        ancho = fig.get_size_inches()[0] * fig.dpi
        for a in (t1, t2, t3, t4):
            bb = a.get_window_extent(r)
            if bb.x1 > ancho or bb.x0 < 0 or bb.y1 > fig.get_size_inches()[1] * fig.dpi or bb.y0 < 0:
                raise SystemExit(f"OG: texto fuera de lienzo x0={bb.x0:.0f} x1={bb.x1:.0f} «{a.get_text()}»")
        print(f"[og] sin solapes ni desbordes (num '{num}', lienzo {ancho:.0f}px)")
    ax.text(0.045, 0.085, "pruebapublica.com", color="#fde047", fontsize=22, fontweight="bold", zorder=5)
    fig.savefig(OUT, facecolor="#0b3b4a")
    print("[og] ok | ipv", ipv_val, ipv_per, "| tot", tot, "| per", per)


if __name__ == "__main__":
    build()
