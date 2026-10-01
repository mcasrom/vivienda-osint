"""OG de Vivienda — poster ATREVIDO (cifra gigante + barras gruesas). 1200x630."""
from __future__ import annotations
import os, sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
VDB = "/home/deploy/municipal-intel/dashboard/data/via/via.db"
OUT = os.path.join(ROOT, "web", "og.png")


def datos():
    c = sqlite3.connect(DB)
    per = c.execute("SELECT MAX(periodo) FROM lanzamientos").fetchone()[0]
    tot = c.execute("SELECT valor FROM lanzamientos WHERE ambito='TOTAL' AND periodo=?", (per,)).fetchone()
    lz = c.execute("SELECT ambito, valor FROM lanzamientos WHERE ambito<>'TOTAL' AND periodo=? ORDER BY valor DESC LIMIT 5", (per,)).fetchall()
    med = None
    try:
        v = sqlite3.connect(f"file:{VDB}?mode=ro", uri=True)
        f = v.execute("SELECT MAX(fecha) FROM via_index").fetchone()[0]
        vals = sorted(x[0] for x in v.execute("SELECT eur_m2_mediana FROM via_index WHERE fecha=? AND eur_m2_mediana IS NOT NULL", (f,)))
        med = vals[len(vals) // 2] if vals else None
    except Exception:
        pass
    return lz, per, (tot[0] if tot else None), med


def build():
    lz, per, tot, med = datos()
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.imshow(np.linspace(0, 1, 256).reshape(1, -1), extent=[0, 1, 0, 1], aspect="auto",
              cmap=LinearSegmentedColormap.from_list("b", ["#083344", "#0e7490", "#0891b2"]), origin="lower", zorder=0)
    # acento diagonal
    ax.fill([0.62, 1.02, 1.02, 0.72], [0, 0, 1.05, 1.05], color="#ffffff", alpha=0.06, zorder=1)
    # marca
    ax.text(0.045, 0.905, "VIVIENDA · DATOS OFICIALES", color="#67e8f9", fontsize=17, fontweight="bold", zorder=3)
    # cifra GIGANTE (alquiler mediano)
    if med:
        ax.text(0.04, 0.70, f"{med:.0f}", color="#ffffff", fontsize=122, fontweight="bold", va="top", ha="left", zorder=3)
        ax.text(0.215, 0.585, "€/m²", color="#67e8f9", fontsize=44, fontweight="bold", va="center", zorder=3)
        ax.text(0.045, 0.315, "alquiler mediano en España", color="#a5f3fc", fontsize=22, zorder=3)
    ax.text(0.045, 0.205, "Precio por municipio · evolución INE · decretos BOE", color="#e0f2fe", fontsize=13.5, zorder=3)
    ax.text(0.045, 0.09, "pruebapublica.com", color="#fde047", fontsize=19, fontweight="bold", zorder=3)
    # panel de barras gruesas
    axb = fig.add_axes([0.55, 0.20, 0.41, 0.60])
    axb.patch.set_visible(False)
    nom = [a.split(",")[0].title() for a, _ in lz][::-1]
    val = [v for _, v in lz][::-1]
    bars = axb.barh(nom, val, color="#facc15", height=0.62)
    axb.set_title(f"Desahucios · {per}", color="#ffffff", fontsize=18, fontweight="bold", pad=10)
    axb.tick_params(colors="#ffffff", labelsize=15)
    for s in axb.spines.values():
        s.set_visible(False)
    axb.set_xticks([])
    for b, v in zip(bars, val):
        axb.text(v + max(val) * 0.02, b.get_y() + b.get_height() / 2, f"{int(v):,}".replace(",", "."),
                 va="center", color="#ffffff", fontsize=15, fontweight="bold")
    axb.set_xlim(0, max(val) * 1.22)
    fig.savefig(OUT, facecolor="#083344")
    print("[og] ok | med", med, "| tot", tot)


if __name__ == "__main__":
    build()
