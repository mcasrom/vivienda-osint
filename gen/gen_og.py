"""OG de Vivienda: poster visual (número grande + gráfico), legible en miniatura. 1200x630."""
from __future__ import annotations
import os, sqlite3
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "vivienda.db")
VDB = "/home/deploy/municipal-intel/dashboard/data/via/via.db"
OUT = os.path.join(ROOT, "web", "og.png")


def _datos():
    c = sqlite3.connect(DB)
    lz = c.execute("SELECT ambito, valor FROM lanzamientos WHERE ambito<>'TOTAL' AND periodo=(SELECT MAX(periodo) FROM lanzamientos) ORDER BY valor DESC LIMIT 6").fetchall()
    per = c.execute("SELECT MAX(periodo) FROM lanzamientos").fetchone()[0]
    tot = c.execute("SELECT valor FROM lanzamientos WHERE ambito='TOTAL' AND periodo=?", (per,)).fetchone()
    med = None
    try:
        v = sqlite3.connect(f"file:{VDB}?mode=ro", uri=True)
        f = v.execute("SELECT MAX(fecha) FROM via_index").fetchone()[0]
        med = v.execute("SELECT eur_m2_mediana FROM via_index WHERE fecha=? AND eur_m2_mediana IS NOT NULL ORDER BY eur_m2_mediana LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM via_index WHERE fecha=? AND eur_m2_mediana IS NOT NULL)", (f, f)).fetchone()
        med = med[0] if med else None
    except Exception:
        pass
    return lz, per, (tot[0] if tot else None), med


def build():
    lz, per, tot, med = _datos()
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    # fondo degradado
    import numpy as np
    g = np.linspace(0, 1, 256).reshape(1, -1)
    ax.imshow(g, extent=[0, 1, 0, 1], aspect="auto", cmap=matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#0b4f4a", "#0f766e", "#0e7490", "#0369a1"]), origin="lower", zorder=0)
    # marca + título
    ax.text(0.045, 0.90, "VIVIENDA · DATOS OFICIALES", color="#a7f3d0", fontsize=22, fontweight="bold", zorder=2)
    ax.text(0.045, 0.72, "Observatorio\nde la vivienda", color="#ffffff", fontsize=40, fontweight="bold", va="top", zorder=2)
    ax.text(0.045, 0.40, "Datos oficiales · INE · CGPJ · BOE", color="#d1fae5", fontsize=17, zorder=2)
    # número grande (mediana €/m²)
    if med:
        ax.text(0.045, 0.16, f"{med:.0f} €/m²", color="#ffffff", fontsize=46, fontweight="bold", zorder=2)
        ax.text(0.045, 0.075, "alquiler mediano en España", color="#a7f3d0", fontsize=15, zorder=2)
    # gráfico de barras (lanzamientos por CCAA)
    axb = fig.add_axes([0.55, 0.16, 0.41, 0.62])
    nombres = [a.replace(", COMUNIDAD", "").replace(", REGIÓN", "").title().replace(" De ", " de ").replace(" La ", " la ") for a, _ in lz][::-1]
    vals = [v for _, v in lz][::-1]
    axb.barh(nombres, vals, color="#fbbf24")
    axb.set_title(f"Desahucios (lanzamientos) · {per}", color="#ffffff", fontsize=13, pad=6)
    axb.tick_params(colors="#e8fff7", labelsize=11)
    for s in axb.spines.values():
        s.set_visible(False)
    axb.set_xticks([])
    for i, v in enumerate(vals):
        axb.text(v + max(vals) * 0.02, i, f"{int(v):,}".replace(",", "."), va="center", color="#ffffff", fontsize=11, fontweight="bold")
    axb.set_xlim(0, max(vals) * 1.18)
    fig.savefig(OUT, facecolor="#0f766e")
    print("[og]", OUT, "| lz", len(lz), "| med", med)


if __name__ == "__main__":
    build()
