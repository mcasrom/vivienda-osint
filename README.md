<div align="center">

# Observatorio de la vivienda · vivienda-osint

**Datos oficiales de vivienda en España, con método, contrato y auditoría.**

[![Licencia](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/badge/dynamic/json?url=https://api.github.com/repos/mcasrom/vivienda-osint/releases/latest&label=release&query=$.tag_name)](https://github.com/mcasrom/vivienda-osint/releases)
[![Tests](https://img.shields.io/badge/tests-pre--push%20(local)-blue)](https://github.com/mcasrom/vivienda-osint/blob/master/scripts/pre-push)

[Panel en vivo](https://vivienda.pruebapublica.com/) ·
[Catálogo de datos](https://vivienda.pruebapublica.com/datos.html) ·
[Fuentes y auditoría](https://vivienda.pruebapublica.com/fuentes.html) ·
[/llms.txt](https://vivienda.pruebapublica.com/llms.txt)

</div>

---

## Qué es

Un **observatorio cívico e independiente** que publica datos oficiales de vivienda en
España: **precios de compraventa (IPV), alquiler (IPVA), lanzamientos judiciales,
ejecuciones hipotecarias, viviendas de uso turístico y las disposiciones del BOE** con
impacto en vivienda, junto con el **estado real de cada real-decreto ley** (publicada,
en votación, convalidada o derogada).

Reglas editoriales duras:

- **Solo hechos con fuente enlazada** (INE, CGPJ, BOE). Nada de datos inventados ni
  estimaciones sin origen.
- **Sin puntuaciones compuestas ni atribuciones.** Cada cifra lleva unidad, fuente y
  período. El sitio **no** analiza coordinación, amplificación ni autoría.
- **El denominador va en la tabla**: si una serie tiene pocas observaciones, se dice,
  no se maquilla.

> ⚠️ **Lección aprendida**: un dato "derivado" que no se sostiene se retira, no se
> maquilla. El precio del alquiler en €/m² se descartó en octubre-2026 al medir que la
> muestra no lo hacía defendible (fuentes mezcladas y scraper topado). Solo vuelve con
> n suficiente, fuente declarada y cada columna con su origen verificado. El alquiler se
> publica como **IPVA (índice anual del INE)**, no como precio por m².

## Por qué existe

Los datos de vivienda existen, pero están **dispersos en portales oficiales con formatos
incompatibles** entre CCAA, tablas y ministerios. Este microservicio los **consolida**,
los **normaliza** (nombres de CCAA canónicos con código INE) y los **publica como datos
abiertos** (CSV+JSON) que cualquier persona, periodista o herramienta puede descargar y
verificar.

## Qué publica (datos abiertos, CSV + JSON)

Además del catálogo, la portada incluye secciones de contexto regulatorio: **normas del BOE** (ficha por norma, con estado y fechas) y **zonas de mercado residencial tensionado** (Ley 12/2023 art. 18: CCAA que las han declarado, con fuente BOE/MIVAU). El sitio genera además **una página por comunidad autónoma** (`/ccaa/`) y un **feed RSS de cambios** de normas y series (`/cambios.xml`).


| Serie | Qué mide | Fuente | Periocidad |
|---|---|---|---|
| `precios-ipv` | Precio de compraventa (IPV), variación anual | INE · tabla 80270 | trimestral |
| `alquiler-ipva` | Índice de precios del alquiler | INE · tabla 59056 | anual |
| `alquiler-serpavi` | Alquiler de referencia por municipio (contratos/fianzas) | MIVAU · SERPAVI (VDP001) | 2024 |
| `ejecuciones-hipotecarias-ccaa` · `-nacional` | Ejecuciones hipotecarias iniciadas | INE · tabla 10740 | anual |
| `compraventas-ccaa` · `-nacional` | Compraventas de vivienda inscritas | INE · ETDP (tabla 49280) | anual |
| `hipotecas-nacional` | Hipotecas constituidas de vivienda | INE · HPT (tabla 3200) | mensual |
| `lanzamientos-ccaa` · `-cronologia` | Lanzamientos (desahucios) | CGPJ | trimestral |
| `viviendas-turisticas-ccaa` | Viviendas de uso turístico | INE · tabla 46141 | anual |
| `boe-vivienda` | Disposiciones del BOE sobre vivienda (sección I) | BOE | diario |
| `ipc-vivienda` | IPC residencial: variación anual por componente (grupo 04) | INE · IPC base 2025 (ECOICOP v2) | mensual |
| `punto-control` | Referencia (último dato publicado) vs último dato del panel | INE/CGPJ | diario |
| `estado-fuentes` | Estado de actualización de cada fuente (ok, fecha, antigüedad) | cron | diaria |

Todo se descarga desde [/datos.html](https://vivienda.pruebapublica.com/datos.html):

- `web/data/<serie>.csv` y `.json`, **UTF-8 con coma y punto decimal** (machine-readable).
- `web/data/latest.json` — el último dato de cada indicador, para consumidores ligeros
  (incluye, por indicador, `actualizado` y `edad_dias`: de cuándo es nuestra última incorporación).
- `web/data/index.json` — catálogo con fuente, período, licencia y **n** por serie.
- `web/data/datapackage.json` — descriptor **Frictionless Data**: por serie, `bytes`, `md5`, esquema de columnas y fuente.
- `web/data/changelog.json` — **historial de cambios** (md5 por serie; auditable, solo registra cuando cambia).
- `web/llms.txt` — guía para asistentes de IA.
- JSON-LD `Dataset` con `distribution`/`DataDownload` por serie en la portada.

**Frescura visible:** la portada tiene un bloque **«Estado de datos»** con ✓/⚠ por fuente
(INE, CGPJ, BOE). Si una ingesta falla, muestra su **última versión válida** y su antigüedad:
la web nunca presenta datos viejos como recién publicados. El estado vive en
`data/frescura.json` (generado por el cron, fuera de git) y se publica como `estado-fuentes`.

**IPC residencial:** la portada incluye la sección **«Inflación residencial»** con la variación
anual del **grupo 04** (Vivienda, agua, electricidad, gas y otros combustibles; **12,26 %** de la
cesta del IPC de 2026) y la **contribución** de cada componente (variación anual × su peso) a la
subida del grupo. Un **índice no es un precio**, y el grupo 04 **no** es el coste total del hogar.

## Cómo está construido

**Arquitectura estática: RAM ≈ 0.** No hay API propia ni backend: un build diario ingiere
datos oficiales, genera HTML/CSV/JSON y se sirve por nginx + Cloudflare.

```
ingest/         boe.py · cgpj.py · ine.py · via.py · territorios.py
gen/            gen_vivienda.py → web/index.html   ·   gen_og.py → tarjeta social
tests/          test_datos.py · test_territorios.py · test_watchdog_rdl.py
scripts/        cron_vivienda.sh (ingesta + regen diarias) · watchdog_rdl.py
data/           vivienda.db (SQLite) · normas.json (única fuente del estado legal)
web/             salida (ignorada en git, regenerada por el build)
```

### Fuentes de datos
- **INE** — webservice `wstempus` (datos abiertos): tablas 80270 (IPV), 59056 (IPVA),
  10740 (ejecuciones), 46141 (viviendas turísticas).
- **CGPJ** — lanzamientos por CCAA y cronología nacional.
- **BOE** — sumario diario (sección I), de donde también se leen los títulos oficiales
  completos de cada norma (no se duplican en el repo).

## Estado legal de los decretos (el preciso y difícil de lo que nos piden)

El estado de cada norma registrada vive en **una única fuente oficial**: `data/normas.json`.
Vasculación por ley: el **art. 86.2 CE** obliga al Congreso a pronunciarse sobre cada
real decreto-ley, y su acuerdo se publica como **Resolución del Congreso en el BOE
(sección I)** — con precedentes reales `BOE-A-2023-8221` (convalidación) y
`BOE-A-2026-4667` (derogación).

Reglas:
- La página **no anticipa** el resultado: mientras se vota, muestra «pendiente» con la
  fecha y hora de la votación.
- Actualizar el estado solo con prueba oficial (la Resolución publicada), con un
  **watchdog automático** (`scripts/watchdog_rdl.py`) que consulta el BOE **cada 30 min**:
  cuando aparece la Resolución, **transcribe el acuerdo a `data/normas.json`** (convalidación
  o derogación) y **regenera solo** por la puerta de staging —protegida por `test_datos`—,
  además de avisar por Telegram. No es «decidir»: es transcribir un hecho oficial con fuente.

## Calidad: contratos y tests

Tres capas de test, ejecutadas **antes de publicar y de pushear** por el **hook local
`scripts/pre-push`** (y por la puerta de staging del cron, `regen_publicar.sh`) — **no
dependen de GitHub Actions**, que está deshabilitado a nivel de cuenta. El workflow de GitHub queda **desactivado** (`.github/workflows/tests.yml.disabled`) hasta que se habilite Actions/billing.

- `tests/test_datos.py` — contratos de datos **sin dependencias**: vocabulario de
  estados, consistencia de fechas (aprobación < BOE ≤ vigencia), nombres de CCAA
  canónicos sin duplicados, **contrato CSV ↔ HTML** (lo que se descarga es lo que se
  ve; muerde: manipular una etiqueta → 3 fallos) y **contrato de ingesta** (suma de CCAA
  = nacional para ejecuciones, lanzamientos, VUT y compraventas; §15/§16).
- `tests/test_territorios.py` — canonización y huecos declarados del CGPJ
  (p. ej. Ceuta/Melilla no publican lanzamientos).
- `tests/test_watchdog_rdl.py` — precedentes de convalidación/derogación y controles
  negativos del watchdog.

Ejecución local:
```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m ingest.boe   # sumario diario del BOE
./venv/bin/python -m ingest.ine   # IPV / IPVA / ejecuciones / turísticas
./venv/bin/python -m ingest.cgpj  # lanzamientos
./venv/bin/python gen/gen_vivienda.py && /usr/bin/python3 gen/gen_og.py
./venv/bin/python tests/test_datos.py
```

## ¿Cómo se actualiza?

```cron
15 6 * * *  /home/deploy/vivienda-osint/scripts/cron_vivienda.sh
```

El cron ingiere + regenera y **corre los tests después de cada build**: si la regen
sale mal, se oye (el fallo va a `logs/` y no solo se ignora).

## Reproducibilidad y honestidad

- Las salidas generadas (`web/`) están **ignoradas en git** a propósito: el repo es la
  **receta**, y la web se regenera desde datos oficiales + código versionado.
- Cada serie del catálogo declara su **fuente, período y n** — y en el panel, el período
  real de cada punto de control.
- No hay métricas "bonitas": si un agregado no aguanta la auditoría, se retira.

## Licencia

**AGPL-3.0** — ver [LICENSE](LICENSE). Uso libre citando fuente; las series del INE/CGPJ/
BOE tienen sus propias condiciones de reutilización (declaradas en el catálogo).