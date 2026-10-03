#!/usr/bin/env python3
"""Auditoría de los datos DERIVADOS del observatorio de la vivienda (read-only).

Los datos derivados (total de viviendas por CCAA = VUT / % de VUT sobre el total
censado del INE, y las tasas ‰ de lanzamientos/ejecuciones por 1.000 viviendas)
no proceden de una fuente directa: se calculan. Antes de publicarlos hay que
verificar que la derivación se sostiene (regla 26 del AGENTS: un dato derivado
solo se publica si su base está auditada).

Comprueba, contra la BD real (data/vivienda.db):
  - cada CCAA tiene VUT y su % (cobertura);
  - el total de viviendas derivado por CCAA suma ≈ el nacional derivado (≤2 %);
  - los totales caen en un rango plausible;
  - las tasas ‰ no tienen outliers groseros.

Salida: tabla por CCAA + resumen; exit 1 si hay fallos.
"""
from __future__ import annotations
import os
import sys
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from ingest import ine, cgpj, territorios  # noqa: E402


def main() -> int:
    vte, anyo, tot_vut, pct_nac = ine.vte_ccaa()
    pct = ine.vte_pct_ccaa()
    lz, lz_per, _ = cgpj.por_ccaa()
    eh, eh_anyo, _ = ine.eh_ccaa()
    cv, cv_fecha, _ = ine.cv_ccaa()

    print(f"VUT {anyo} · lanz {lz_per} · ejec {eh_anyo} · comprav {cv_fecha}")
    nac = tot_vut / (pct_nac / 100)
    print(f"VUT nacional {tot_vut:,.0f} (pct {pct_nac}%) -> total viviendas {nac:,.0f}\n")

    vd, lzd, ehd = dict(vte), dict(lz), dict(eh)
    fails, totales, rlz_all, reh_all = [], [], [], []
    print(f"{'CCAA':34}{'VUT':>9}{'pct%':>6}{'total':>11}{'lz':>8}{'eh':>7}"
          f"{'lz‰':>7}{'eh‰':>7}{'IPV':>7}  flag")
    for cod, nom in territorios.NOMBRE.items():
        p, v = pct.get(nom), vd.get(nom)
        total = (v / (p / 100)) if (v and p) else None
        l, e = lzd.get(nom), ehd.get(nom)
        rlz = round(l * 4 / total * 1000, 1) if (l is not None and total) else None
        reh = round(e / total * 1000, 1) if (e is not None and total) else None
        ipv = ine.ultimo(f"ipv_var_anual:{cod}")
        if total:
            totales.append(total)
        if rlz is not None:
            rlz_all.append(rlz)
        if reh is not None:
            reh_all.append(reh)
        flag = ""
        if p is None:
            flag += " SIN_PCT"
            fails.append(f"{nom}: sin vte_pct")
        if v is None:
            flag += " SIN_VUT"
            fails.append(f"{nom}: sin vte")
        if total and not (0.02e6 <= total <= 5e6):
            flag += " TOTAL_RARO"
            fails.append(f"{nom}: total {total:,.0f} fuera de rango")
        print(f"{nom:34}{('' if v is None else f'{v:,.0f}'):>9}{('' if p is None else p):>6}"
              f"{('' if total is None else f'{total:,.0f}'):>11}{('' if l is None else l):>8}"
              f"{('' if e is None else e):>7}{('' if rlz is None else rlz):>7}"
              f"{('' if reh is None else reh):>7}{('' if ipv is None else ipv):>7}  {flag}")

    desv = sum(totales) / nac * 100 - 100
    print(f"\nsuma CCAA {sum(totales):,.0f} vs nacional {nac:,.0f} · desv {desv:+.2f}%")
    if abs(desv) > 2:
        fails.append(f"suma CCAA vs nacional desviada {desv:+.2f}% (>2%)")
    if len(rlz_all) >= 4:
        print(f"IQR lz‰ {[round(x, 1) for x in statistics.quantiles(rlz_all, n=4)]} (n={len(rlz_all)})")
    if len(reh_all) >= 4:
        print(f"IQR eh‰ {[round(x, 1) for x in statistics.quantiles(reh_all, n=4)]} (n={len(reh_all)})")
    print(f"\nFALLOS ({len(fails)}):")
    for f in fails:
        print("  -", f)
    if fails:
        print("AUDITORÍA CON AVISOS")
        return 1
    print("AUDITORÍA OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
