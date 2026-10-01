# Microservicio **Vivienda** (pruebapublica.com)

> Información **cívica y neutral** sobre la vivienda en España: qué cambian los decretos (BOE),
> cuánto cuesta el alquiler por municipio, cómo participar. **Solo hechos con fuente enlazada.**
> **No** es FIMI: **no** analiza coordinación, amplificación ni «quién lo mueve».

**Marca y dominio propios.** Comparte *datos* con `municipal-intel` (precios), **no ejecución**.
Arquitectura **estática** (build → HTML, nginx) → **RAM ≈ 0**.

## Estructura
```
ingest/       boe.py (decretos, BOE datos abiertos) · via.py (precios, via.db) · ine.py (WIP)
gen/          gen_vivienda.py  → web/index.html
data/         vivienda.db (SQLite)
scripts/      cron_vivienda.sh (ingesta diaria + regenera)
```

## Uso
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m ingest.boe        # ingesta BOE (últimos 21 días)
./venv/bin/python gen/gen_vivienda.py  # genera web/index.html
```

## Cron (diario, hora distinta a FIMI)
```
15 6 * * * /home/deploy/vivienda-osint/scripts/cron_vivienda.sh >> /home/deploy/vivienda-osint/logs/cron.log 2>&1
```

## Alcance / encuadre
- **MVP:** decretos (BOE) · precios por municipio · cómo participar · fuentes.
- **Fase 2:** API JSON · panel admin · cronología de la protesta · cobertura de prensa.
- **Fuera de alcance:** coordinación/amplificación · atribución · datos personales.

## Licencia
AGPL-3.0 — ver `LICENSE`.
