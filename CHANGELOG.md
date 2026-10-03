# Registro de cambios · vivienda-osint

## [Sin publicar] — 2026-10-03
- **Esfuerzo de acceso al alquiler por municipio** (`esfuerzo-alquiler-municipio`): cruce de la
  **renta neta media por hogar** (INE · **ADRH**, 2023, por código INE) con el **alquiler de
  referencia** (MIVAU · **SERPAVI**, 2024). Nueva fuente `ingest/renta.py` (mapa provincia→tabla
  cacheado en `data/adrh_tablas.json`); datos anuales, fuera del cron diario. Bloque nuevo en la
  portada y dataset; `test_datos` **§27** (cobertura ≥100 municipios y rangos plausibles). Es una
  **estimación descriptiva** (piso de 80 m², contrato nuevo), no un ranking.

## [0.1.1] — 2026-10-03
- **`status.json` público** (`web/data/status.json`): estado operativo por fuente — última OK,
  último intento, `edad_dias`, nº de **filas** y `sha256` de su serie. Amplía el bloque «Estado
  de datos» (transparencia/auditoría).
- **σ-quarantine pre-publicación** (`test_datos` §26): un salto **anómalo** (z robusto con MAD
  > 5 sobre las diferencias de la serie nacional) o **periodos duplicados** **bloquean** la
  publicación (la web conserva la última versión buena y avisa por Telegram); los atípicos
  moderados (z > 3.5) se registran. Umbrales calibrados sobre los datos reales (los z actuales
  son < 1).
- **Lanzamientos (desahucios) por causa**: el Excel del CGPJ desglosa los lanzamientos
  practicados en **ejecución hipotecaria + LAU + otras**. Se ingestan las tres hojas
  (`ingest/cgpj.py`, tabla `lanzamientos_causa`), se publica un bloque **«Desglose por causa»**
  y dos datasets: `lanzamientos-causa` (nacional, histórico) y `lanzamientos-causa-ccaa`
  (último trimestre, por CCAA). **Validado**: hipotecaria + LAU + otras = total, nacional y por
  CCAA (`test_datos` §25). ⚠️ El CGPJ **etiqueta mal** la última columna de la hoja LAU (repite
  «25-T1»): los periodos se alinean por **posición** con la hoja total para no asignar el dato
  al trimestre equivocado.
- **`CITATION.cff`** (CFF 1.2.0) para citabilidad; DOI de Zenodo pendiente (ver README §Citar).

## [0.1.0] — 2026-10-02
Primera versión etiquetada tras la auditoría externa del alquiler €/m².

### Correcto (2-oct)
- **Ficha de las normas (RDL 26/2026 y 27/2026)** con estado y fechas separadas
  (aprobación ≠ publicación BOE ≠ vigencia), basada en el art. 86.2 CE y en cómo el
  Congreso publica después el acuerdo (Resolución en el BOE, sección I). Nueva fuente
  única `data/normas.json`.
- **Nombres de CCAA canónicos**: nueva tabla `ingest/territorios.py` (nombre oficial
  del INE + código INE, alias del CGPJ). «MURCIA, REGIÓN» y «Murcia, Región de» ya no
  conviven en la misma página; las tres series por CCAA salen en el mismo orden.
- **Flecha de tendencia honesta**: «se modera» ya no se pinta como bajada (▼/verde);
  es una deceleración de una subida y usa marcador neutro. El IPV publica «+12,2 %
  ▬ se modera», no «▼».
- **Watchdog del RDL**: `scripts/watchdog_rdl.py` busca cada 30 min la Resolución del
  Congreso en el BOE y avisa por Telegram una sola vez; la web nunca vuelve a decir
  «pendiente» por descuido. Comprobado contra los precedentes reales convalidación/
  derogación (`test_watchdog_rdl.py`).
- **Causa raíz del error silencioso del BOE**: los `HTTPError` eran domingos (no hay
  sumario). Ahora el 404 de domingo se ignora como lo normal y cualquier otro fallo
  queda en el log (`ingest/boe.py`).

### Calidad
- `requirements.txt` fijado (incluye `openpyxl`, que se usaba sin declarar).
- Contratos de datos ejecutables: nombres canónicos, huecos declarados, CSV↔HTML,
  tarjeta↔`latest.json` (`tests/test_datos.py`).
- CI (GitHub Actions) ejecuta los tests que no dependen de artefactos generados;
  la verificación completa de la web generada se hace en cada cron diario.

### Cambio de comportamiento
- El cron diario genera y además ejecuta los contratos: un fallo de regeneración
  ahora se oye (`test_datos FALLO` en `logs/gen.log`), no solo queda en el log.