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
VDB = "/home/deploy/municipal-intel/dashboard/data/via/via.db"
OUT = os.path.join(ROOT, "web", "og.png")


def datos():
    c = sqlite3.connect(DB)
    per = c.execute("SELECT MAX(periodo) FROM lanzamientos").fetchone()[0]
    tot = c.execute("SELECT valor FROM lanzamientos WHERE ambito='TOTAL' AND periodo=?", (per,)).fetchone()
    med = None
    try:
        v = sqlite3.connect(f"file:{VDB}?mode=ro", uri=True)
        f = v.execute("SELECT MAX(fecha) FROM via_index").fetchone()[0]
        vals = sorted(x[0] for x in v.execute("SELECT eur_m2_mediana FROM via_index WHERE fecha=? AND eur_m2_mediana IS NOT NULL", (f,)))
        med = vals[len(vals) // 2] if vals else None
    except Exception:
        pass
    return per, (tot[0] if tot else None), med


def build():
    per, tot, med = datos()
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
    if med:
        ax.text(0.40, 0.60, f"{med:.0f}", color="#fbbf24", fontsize=148, fontweight="bold", va="top", zorder=5)
        ax.text(0.63, 0.455, "€/m²", color="#fbbf24", fontsize=52, fontweight="bold", va="center", zorder=5)
        ax.text(0.41, 0.235, "alquiler mediano en España", color="#a5f3fc", fontsize=23, zorder=5)
    ax.text(0.045, 0.085, "pruebapublica.com", color="#fde047", fontsize=22, fontweight="bold", zorder=5)
    fig.savefig(OUT, facecolor="#0b3b4a")
    print("[og] ok | med", med, "| tot", tot, "| per", per)


if __name__ == "__main__":
    build()
