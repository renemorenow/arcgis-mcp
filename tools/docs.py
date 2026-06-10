from __future__ import annotations
import importlib
import inspect
import re

from _server import mcp

# =========================================================================== #
#   📚 ARCGIS API DOCS — Introspección en vivo del paquete instalado
#   Usa inspect sobre el paquete arcgis real → exacto para la versión activa.
# =========================================================================== #

_ARCGIS_ROOT = "arcgis"

# Módulos principales y sus aliases descriptivos (para orientación del usuario)
_MODULE_INDEX: dict[str, str] = {
    "arcgis.gis":               "Portal, usuarios, grupos, items, contenido",
    "arcgis.features":          "FeatureLayer, FeatureSet, edición y consulta de features",
    "arcgis.mapping":           "WebMap, WebScene, MapImageLayer, capas",
    "arcgis.geometry":          "Point, Polygon, Polyline, MultiPoint, SpatialReference",
    "arcgis.geocoding":         "geocode, reverse_geocode, localizadores",
    "arcgis.geoprocessing":     "Geoprocesamiento: import_toolbox, linear_unit",
    "arcgis.raster":            "Raster, ImageryLayer, análisis de imágenes",
    "arcgis.network":           "Análisis de redes: rutas, áreas de servicio, OD matrix",
    "arcgis.geoenrichment":     "GeoEnrichment: variables demográficas y del entorno",
    "arcgis.realtime":          "Streaming y capas en tiempo real",
    "arcgis.learn":             "Deep learning, modelos, inferencia",
    "arcgis.env":               "Variables de entorno del API (proxy, token, output_sr…)",
    "arcgis.tools":             "Herramientas de análisis (analysis, data_management…)",
    "arcgis.widgets":           "MapView y widgets para Jupyter Notebook",
    "arcgis.apps":              "Aplicaciones: StoryMaps, Workforce, Hub, etc.",
    "arcgis.schematics":        "Diagramas de red esquemáticos",
    "arcgis.geometry.functions":"Operaciones geométricas del servicio REST",
}


def _safe_import(module_path: str):
    """Importa un módulo por su dotted path; retorna None si falla."""
    try:
        return importlib.import_module(module_path)
    except Exception:
        return None


def _clean_doc(doc: str | None, max_chars: int = 2000) -> str:
    if not doc:
        return "(sin documentación)"
    # Normalizar indentación excesiva
    doc = inspect.cleandoc(doc)
    if len(doc) > max_chars:
        doc = doc[:max_chars] + f"\n…(truncado, usa arcgis_docs_get para ver completo)"
    return doc


# =========================================================================== #
#   Tool 1: listar módulos disponibles
# =========================================================================== #

@mcp.tool()
def arcgis_docs_modules() -> dict:
    """Lista los módulos principales del ArcGIS API for Python con su descripción.

    Punto de entrada para saber qué módulo contiene la funcionalidad que buscás.
    Retorna el path de importación y una descripción breve de cada módulo.

    Ejemplo de uso:
        arcgis_docs_modules()
        → {"arcgis.gis": "Portal, usuarios, grupos, items, contenido", ...}
    """
    return _MODULE_INDEX


# =========================================================================== #
#   Tool 2: listar símbolos públicos de un módulo
# =========================================================================== #

@mcp.tool()
def arcgis_docs_list(module_path: str) -> dict:
    """Lista las clases y funciones públicas de un módulo del ArcGIS API for Python.

    module_path: dotted path del módulo, ej: 'arcgis.gis', 'arcgis.features',
                 'arcgis.geometry'. Debe comenzar con 'arcgis.'.

    Retorna un dict con dos listas:
        classes: [(nombre, primera_línea_docstring), ...]
        functions: [(nombre, primera_línea_docstring), ...]

    Ejemplo:
        arcgis_docs_list("arcgis.gis")
        → {"classes": [["GIS", "Represents an ArcGIS Online…"], ...], "functions": [...]}
    """
    if not module_path.startswith("arcgis"):
        return {"error": "module_path debe comenzar con 'arcgis'. Ej: 'arcgis.gis'"}

    mod = _safe_import(module_path)
    if mod is None:
        return {"error": f"No se pudo importar '{module_path}'. Verificá el nombre del módulo."}

    classes: list[list[str]] = []
    functions: list[list[str]] = []

    for name, obj in inspect.getmembers(mod):
        if name.startswith("_"):
            continue
        # Solo miembros definidos en este módulo (no re-exports de otros)
        obj_module = getattr(obj, "__module__", "") or ""
        if obj_module and not obj_module.startswith("arcgis"):
            continue

        first_line = ""
        if obj.__doc__:
            first_line = inspect.cleandoc(obj.__doc__).split("\n")[0][:120]

        if inspect.isclass(obj):
            classes.append([name, first_line])
        elif inspect.isfunction(obj) or inspect.isbuiltin(obj):
            functions.append([name, first_line])

    return {
        "module": module_path,
        "classes": sorted(classes, key=lambda x: x[0]),
        "functions": sorted(functions, key=lambda x: x[0]),
    }


# =========================================================================== #
#   Tool 3: obtener documentación completa de clase / función / método
# =========================================================================== #

@mcp.tool()
def arcgis_docs_get(symbol_path: str) -> dict:
    """Obtiene la documentación completa de una clase, función o método del ArcGIS API.

    symbol_path: dotted path completo al símbolo. Formatos válidos:
        'arcgis.gis.GIS'              → clase GIS
        'arcgis.gis.GIS.content'      → propiedad/atributo content
        'arcgis.features.FeatureLayer.query'  → método query
        'arcgis.geocoding.geocode'    → función geocode

    Retorna:
        symbol:    nombre del símbolo
        type:      'class' | 'function' | 'method' | 'property' | 'attribute'
        module:    módulo donde está definido
        signature: firma del callable (si aplica)
        doc:       docstring completo (hasta 4000 caracteres)
        methods:   lista de métodos públicos con primera línea (solo para clases)
        url_hint:  URL aproximada en la documentación oficial

    Ejemplo:
        arcgis_docs_get("arcgis.gis.GIS")
        arcgis_docs_get("arcgis.features.FeatureLayer.query")
    """
    if not symbol_path.startswith("arcgis"):
        return {"error": "symbol_path debe comenzar con 'arcgis'."}

    parts = symbol_path.split(".")
    # Intentar importar el módulo más profundo posible, luego navegar atributos
    obj = None
    last_mod_idx = 1
    for i in range(len(parts), 1, -1):
        candidate_mod = ".".join(parts[:i])
        mod = _safe_import(candidate_mod)
        if mod is not None:
            obj = mod
            last_mod_idx = i
            break

    if obj is None:
        return {"error": f"No se encontró ningún módulo importable en '{symbol_path}'."}

    # Navegar los atributos restantes
    attr_chain = parts[last_mod_idx:]
    for attr in attr_chain:
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            return {
                "error": (
                    f"Atributo '{attr}' no encontrado. "
                    f"Verificá con arcgis_docs_list('{'.'.join(parts[:last_mod_idx])}')"
                )
            }

    # Determinar tipo
    if inspect.isclass(obj):
        sym_type = "class"
    elif inspect.ismethod(obj) or inspect.isfunction(obj):
        sym_type = "method" if attr_chain else "function"
    elif isinstance(obj, property):
        sym_type = "property"
    else:
        sym_type = "attribute"

    # Firma
    signature = ""
    if callable(obj) and not isinstance(obj, property):
        try:
            sig = inspect.signature(obj)
            signature = str(sig)
        except (ValueError, TypeError):
            signature = "(no disponible)"

    # Métodos públicos si es clase
    methods: list[list[str]] = []
    if inspect.isclass(obj):
        sym_type = "class"
        for mname, mobj in inspect.getmembers(obj):
            if mname.startswith("_"):
                continue
            first_line = ""
            if mobj.__doc__:
                first_line = inspect.cleandoc(mobj.__doc__).split("\n")[0][:100]
            methods.append([mname, first_line])
        methods.sort(key=lambda x: x[0])

    # Docstring completo (hasta 4000 chars para evitar flooding)
    doc = _clean_doc(getattr(obj, "__doc__", None), max_chars=4000)

    # URL aproximada en la docs oficial
    mod_name = getattr(obj, "__module__", ".".join(parts[:-len(attr_chain)]) if attr_chain else symbol_path)
    url_hint = f"https://developers.arcgis.com/python/latest/api-reference/{mod_name}/"

    return {
        "symbol": parts[-1],
        "full_path": symbol_path,
        "type": sym_type,
        "module": mod_name,
        "signature": signature,
        "doc": doc,
        "methods": methods[:50] if methods else [],  # limitar para no saturar
        "url_hint": url_hint,
    }


# =========================================================================== #
#   Tool 4: buscar en docstrings de todo el API
# =========================================================================== #

@mcp.tool()
def arcgis_docs_search(
    query: str,
    module_filter: str = "",
    max_results: int = 20,
) -> list[dict]:
    """Busca texto en los docstrings del ArcGIS API for Python instalado.

    Útil para encontrar qué clase o función hace lo que necesitás sin conocer
    el nombre exacto.

    query:         texto a buscar (case-insensitive). Ej: 'buffer', 'export csv',
                   'publish feature service'.
    module_filter: prefijo de módulo para acotar la búsqueda.
                   Ej: 'arcgis.features', 'arcgis.mapping'. Vacío = todo el API.
    max_results:   número máximo de resultados (default 20, max 50).

    Retorna lista de matches con:
        path:       dotted path del símbolo
        type:       'class' | 'function' | 'method'
        first_line: primera línea del docstring
        snippet:    fragmento donde aparece el query

    Ejemplo:
        arcgis_docs_search("export features", module_filter="arcgis.features")
        arcgis_docs_search("publish csv", max_results=10)
    """
    if not query or len(query.strip()) < 2:
        return [{"error": "query debe tener al menos 2 caracteres"}]

    max_results = min(max_results, 50)
    pattern = re.compile(re.escape(query.strip()), re.IGNORECASE)

    # Módulos a inspeccionar
    target_modules = [
        m for m in _MODULE_INDEX
        if not module_filter or m.startswith(module_filter)
    ]

    results: list[dict] = []

    for mod_path in target_modules:
        if len(results) >= max_results:
            break
        mod = _safe_import(mod_path)
        if mod is None:
            continue

        for name, obj in inspect.getmembers(mod):
            if name.startswith("_"):
                continue
            if len(results) >= max_results:
                break

            obj_module = getattr(obj, "__module__", "") or ""
            if obj_module and not obj_module.startswith("arcgis"):
                continue

            doc = getattr(obj, "__doc__", None)
            if not doc:
                continue

            clean = inspect.cleandoc(doc)
            m = pattern.search(clean)
            if not m:
                continue

            # Extraer snippet con contexto alrededor del match
            start = max(0, m.start() - 60)
            end = min(len(clean), m.end() + 120)
            snippet = ("…" if start > 0 else "") + clean[start:end] + ("…" if end < len(clean) else "")
            snippet = snippet.replace("\n", " ")

            first_line = clean.split("\n")[0][:120]
            sym_type = "class" if inspect.isclass(obj) else "function"

            results.append({
                "path": f"{mod_path}.{name}",
                "type": sym_type,
                "first_line": first_line,
                "snippet": snippet,
            })

            # Buscar también en métodos si es clase
            if inspect.isclass(obj) and len(results) < max_results:
                for mname, mobj in inspect.getmembers(obj):
                    if mname.startswith("_"):
                        continue
                    if len(results) >= max_results:
                        break
                    mdoc = getattr(mobj, "__doc__", None)
                    if not mdoc:
                        continue
                    mclean = inspect.cleandoc(mdoc)
                    mm = pattern.search(mclean)
                    if not mm:
                        continue
                    mstart = max(0, mm.start() - 60)
                    mend = min(len(mclean), mm.end() + 120)
                    msnippet = ("…" if mstart > 0 else "") + mclean[mstart:mend] + ("…" if mend < len(mclean) else "")
                    msnippet = msnippet.replace("\n", " ")
                    results.append({
                        "path": f"{mod_path}.{name}.{mname}",
                        "type": "method",
                        "first_line": inspect.cleandoc(mclean).split("\n")[0][:120],
                        "snippet": msnippet,
                    })

    return results if results else [{"info": f"No se encontraron resultados para '{query}'"}]
