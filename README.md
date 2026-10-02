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

## Estado de las normas registradas (BOE)
`data/normas.json` es la **única fuente** del estado de cada norma registrada: aprobación,
publicación, vigencia y estado, con las fechas **separadas** (no se confunde la aprobación
con la publicación). Los títulos oficiales completos **no** se duplican ahí: se leen de la
tabla `boe` (`ingest/boe.py`).

Vocabulario de `estado`: `publicada` · `en_votacion` · `convalidada` · `derogada`.

**Para actualizar el estado tras una votación** (p. ej. la convalidación o derogación de un
real decreto-ley):
1. Consultar la **Resolución del Congreso** en el BOE, sección I (es donde se publica; art.
   86.2 CE obliga al Congreso a pronunciarse expresamente sobre la convalidación o derogación).
2. Editar `data/normas.json`: `estado`, `resultado` (texto neutral) y `resultado_fecha`.
3. `./venv/bin/python gen/gen_vivienda.py` y `./venv/bin/python tests/test_datos.py`.
4. Purgar Cloudflare (zona `pruebapublica`) para que se vea en producción.

El test de contratos **falla si**: una norma registrada no está en la tabla `boe`, si su fecha
BOE no coincide con la BD, si el estado está fuera de vocabulario, si se declara un resultado
sin `resultado` + `resultado_fecha`, si una norma pendiente tiene resultado, si la cronología
(aprobación < BOE < vigencia) se rompe, o si el CSV publicado deja alguna fila sin `estado`.

En `en_votacion` la página **no anticipa el resultado**: muestra la fecha y hora de la votación
y lo declara pendiente.

## Tests (contratos de datos)
```bash
./venv/bin/python tests/test_datos.py   # sin dependencias; sale con 1 si algo falla
```

## Cron (diario, hora distinta a FIMI)
```
15 6 * * * /home/deploy/vivienda-osint/scripts/cron_vivienda.sh >> /home/deploy/vivienda-osint/logs/cron.log 2>&1
```

## Alcance / encuadre
- **MVP:** decretos (BOE) · precios por municipio · cómo participar · fuentes.
- **Fase 2:** API JSON · panel admin.
- **Retirado del alcance (2-oct-2026):** cronología de la protesta y cobertura de prensa (el observatorio es un registro descriptivo de datos y normas, sin activismo).
- **Fuera de alcance:** coordinación/amplificación · atribución · datos personales.

## Licencia
AGPL-3.0 — ver `LICENSE`.
