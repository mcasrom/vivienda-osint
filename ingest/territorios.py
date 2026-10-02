"""Territorios: tabla canónica de comunidades autónomas (nombre oficial INE + código).

Única fuente de nombres para TODA serie por CCAA (INE y CGPJ). El nombre canónico es
la etiqueta oficial del INE, que es lo que ya publican las series `eh:*` y `vte:*` de
la tabla `ine_serie`. El CGPJ usa otro criterio (mayúsculas y abreviaturas: «MADRID,
COMUNIDAD», «NAVARRA, COM. FORAL»); aquí se traduce con `ALIAS_CGPJ`.

Motivo: el 2-oct-2026 la misma tabla mostraba «Murcia, Región de» (INE) y «MURCIA,
REGIÓN» (CGPJ) en páginas distintas, lo que rompía cualquier unión por nombre.

Los títulos oficiales completos (boletines, ordenanzas) no se meten aquí: solo el
nombre del territorio. Para el mapa provincial están los códigos INE en `gen_vivienda`.
"""
from __future__ import annotations

# (código INE, nombre oficial del INE)
CCAA: tuple[tuple[str, str], ...] = (
    ("01", "Andalucía"),
    ("02", "Aragón"),
    ("03", "Asturias, Principado de"),
    ("04", "Balears, Illes"),
    ("05", "Canarias"),
    ("06", "Cantabria"),
    ("07", "Castilla - La Mancha"),
    ("08", "Castilla y León"),
    ("09", "Cataluña"),
    ("10", "Comunitat Valenciana"),
    ("11", "Extremadura"),
    ("12", "Galicia"),
    ("13", "Madrid, Comunidad de"),
    ("14", "Murcia, Región de"),
    ("15", "Navarra, Comunidad Foral de"),
    ("16", "País Vasco"),
    ("17", "Rioja, La"),
    ("18", "Ceuta"),
    ("19", "Melilla"),
)

NOMBRES: tuple[str, ...] = tuple(n for _c, n in CCAA)
CODIGO: dict[str, str] = {n: c for c, n in CCAA}          # nombre -> código INE
NOMBRE: dict[str, str] = {c: n for c, n in CCAA}          # código -> nombre
NORMAL: dict[str, str] = {n.lower(): n for _c, n in CCAA}  # para filtrar etiquetas
ORDEN: dict[str, int] = {n: i for i, (_c, n) in enumerate(CCAA)}

# Etiquetas del XLSX del CGPJ -> nombre canónico. Verificadas contra la hoja
# «Lanzamientos practic. total TSJ» (17 CCAA; el CGPJ no publica Ceuta ni Melilla).
ALIAS_CGPJ: dict[str, str] = {
    "ANDALUCÍA": "Andalucía",
    "ARAGÓN": "Aragón",
    "ASTURIAS, PRINCIPADO": "Asturias, Principado de",
    "ILLES BALEARS": "Balears, Illes",
    "CANARIAS": "Canarias",
    "CANTABRIA": "Cantabria",
    "CASTILLA - LA MANCHA": "Castilla - La Mancha",
    "CASTILLA Y LEÓN": "Castilla y León",
    "CATALUÑA": "Cataluña",
    "COMUNITAT VALENCIANA": "Comunitat Valenciana",
    "EXTREMADURA": "Extremadura",
    "GALICIA": "Galicia",
    "MADRID, COMUNIDAD": "Madrid, Comunidad de",
    "MURCIA, REGIÓN": "Murcia, Región de",
    "NAVARRA, COM. FORAL": "Navarra, Comunidad Foral de",
    "PAÍS VASCO": "País Vasco",
    "LA RIOJA": "Rioja, La",
}

# Series que no cubren las 19 CCAA, con el motivo declarado (2-oct-2026).
# El hueco se declara aquí a propósito: si el CGPJ empieza a publicar Ceuta o
# Melilla, esta constante avisa en vez de dejar el hueco silencioso.
HUECOS: dict[str, tuple[tuple[str, str], ...]] = {
    "lanzamientos-ccaa": (("Ceuta", "CGPJ no publica lanzamientos por Ciudad Autónoma"),
                          ("Melilla", "CGPJ no publica lanzamientos por Ciudad Autónoma")),
}


def canonico(etiqueta: str) -> str | None:
    """Etiqueta de cualquier fuente -> nombre canónico, o None si no se reconoce."""
    if not etiqueta:
        return None
    e = etiqueta.strip()
    if e in CODIGO:                 # ya canónico (p. ej. serie del INE)
        return e
    if e.upper() in ALIAS_CGPJ:     # mayúsculas/abreviaturas del CGPJ
        return ALIAS_CGPJ[e.upper()]
    return NORMAL.get(e.lower())    # por si llega en otro formato


def ordenar(pares):
    """Ordena [(nombre, valor)] por el orden territorial canónico (comparables entre series)."""
    return sorted(pares, key=lambda kv: ORDEN.get(kv[0], 999))


def comprobar_etiquetas(etiquetas) -> tuple[list[str], list[str]]:
    """([reconocidas], [desconocidas]) — para no descartar nada en silencio."""
    ok, ko = [], []
    for e in etiquetas:
        c = canonico(e)
        (ok if c else ko).append(e)
    return ok, ko