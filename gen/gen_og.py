"""Genera la imagen OG (1200x630) con PIL: título + mediana €/m²."""
from __future__ import annotations
import os, sys
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ingest import via  # noqa: E402

OUT = os.path.join(ROOT, "web", "og.png")
W, H = 1200, 630


def _font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def build():
    v = via.resumen()
    med = v["mediana"] or 0
    img = Image.new("RGB", (W, H), (15, 118, 110))
    d = ImageDraw.Draw(img)
    for i in range(H):  # gradiente suave
        c = (int(15 + (3 - 15) * i / H), int(118 + (105 - 118) * i / H), int(110 + (161 - 110) * i / H))
        d.line([(0, i), (W, i)], fill=c)
    d.text((70, 70), "🏠 Vivienda · pruebapublica.com", font=_font(30), fill=(255, 255, 255))
    d.text((70, 150), "La vivienda en España,", font=_font(74), fill=(255, 255, 255))
    d.text((70, 240), "en datos", font=_font(74), fill=(255, 255, 255))
    d.text((70, 370), f"{med:.0f} €/m²".replace(",", ".") + "  ·  mediana del alquiler", font=_font(46), fill=(204, 251, 241))
    d.text((70, 440), f"{v['n']} municipios · decretos BOE · evolución INE", font=_font(32), fill=(240, 253, 250))
    d.text((70, 545), "Datos abiertos · cívico y neutral", font=_font(26), fill=(153, 246, 228))
    img.save(OUT)
    print("[og]", OUT)


if __name__ == "__main__":
    build()
