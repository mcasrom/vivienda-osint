# Registro de cambios · vivienda-osint

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