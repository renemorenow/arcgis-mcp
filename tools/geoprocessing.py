from __future__ import annotations
import inspect
import json
from typing import Any

from arcgis.geoprocessing import import_toolbox

from _server import mcp
from _auth import (
    get_gis, _safe_result,
)

# =========================================================================== #
#   GEOPROCESAMIENTO DINÁMICO  (GP Services)
# =========================================================================== #
@mcp.tool()
def gp_discover(gp_url_or_item: str) -> dict:
    """Descubre los tools disponibles en un GP Service y sus parámetros.

    gp_url_or_item: URL del GPServer o item ID del Geoprocessing Toolbox.
    Retorna lista de tools con nombre, docstring y parámetros.
    """
    gis = get_gis()
    tbx = import_toolbox(gp_url_or_item, gis=gis)
    tools = []
    for name in dir(tbx):
        if name.startswith("_"):
            continue
        func = getattr(tbx, name, None)
        if not callable(func):
            continue
        sig = str(inspect.signature(func)) if hasattr(func, "__wrapped__") or callable(func) else ""
        tools.append({
            "name": name,
            "signature": sig,
            "doc": (func.__doc__ or "")[:500],
        })
    return {"toolbox": gp_url_or_item, "tools": tools}


@mcp.tool()
def gp_run(
    gp_url_or_item: str,
    tool_name: str,
    params_json: str = "{}",
) -> dict:
    """Ejecuta un tool de un GP Service con parámetros dinámicos.

    gp_url_or_item: URL del GPServer o item ID.
    tool_name: nombre del tool (obtenido de discover_gp_tools).
    params_json: JSON con parámetros clave-valor del tool.

    IMPORTANTE: usar discover_gp_tools primero para conocer parámetros válidos.
    """
    gis = get_gis()
    tbx = import_toolbox(gp_url_or_item, gis=gis)
    func = getattr(tbx, tool_name, None)
    if func is None or not callable(func):
        available = [n for n in dir(tbx) if not n.startswith("_") and callable(getattr(tbx, n, None))]
        raise ValueError(
            f"Tool '{tool_name}' no encontrado. Disponibles: {available}"
        )
    params = json.loads(params_json) if params_json else {}
    result = func(**params)
    return _safe_result(result)


@mcp.tool()
def gp_run_async(
    gp_url_or_item: str,
    tool_name: str,
    params_json: str = "{}",
) -> dict:
    """Ejecuta un GP tool y espera a que complete.

    gp_url_or_item: URL del GPServer o item ID.
    tool_name: nombre del tool (obtenido de discover_gp_tools).
    params_json: JSON con parámetros clave-valor del tool.

    La API de ArcGIS maneja automáticamente el polling para GP tools asíncronos.
    Según documentación oficial: https://developers.arcgis.com/python/latest/guide/using-geoprocessing-tools/
    
    Para tools asíncronos, result.result() bloquea hasta que el job complete.
    """
    gis = get_gis()
    tbx = import_toolbox(gp_url_or_item, gis=gis)
    func = getattr(tbx, tool_name, None)
    if func is None or not callable(func):
        available = [n for n in dir(tbx) if not n.startswith("_") and callable(getattr(tbx, n, None))]
        raise ValueError(
            f"Tool '{tool_name}' no encontrado. Disponibles: {available}"
        )
    
    params = json.loads(params_json) if params_json else {}
    
    # Ejecutar el tool
    result = func(**params)
    
    # Para GP tools asíncronos, result.result() maneja el polling automáticamente
    # y bloquea hasta que el job complete o falle
    if hasattr(result, 'result') and callable(result.result):
        try:
            final_result = result.result()
            return {
                "status": "completed",
                "result": _safe_result(final_result)
            }
        except Exception as e:
            # El tool falló durante ejecución
            return {
                "status": "failed",
                "error": str(e),
                "job_id": result.jobid if hasattr(result, 'jobid') else None
            }
    
    # Tool síncrono - devolver resultado directo
    return _safe_result(result)


# =========================================================================== #
#   GEOPROCESAMIENTO — herramientas extendidas (gp_*)
# =========================================================================== #

@mcp.tool()
def gp_tool_help(
    gp_url_or_item: str,
    tool_name: str,
) -> dict:
    """Retorna ayuda completa y firma de un tool específico de un GP Service.

    gp_url_or_item: URL del GPServer o item ID del Geoprocessing Toolbox.
    tool_name: nombre exacto del tool (obtener con discover_gp_tools).

    Retorna: docstring completo, firma con tipos de parámetros, y tipo de retorno.
    USAR SIEMPRE antes de llamar run_gp_tool para conocer parámetros exactos.
    Los tipos de parámetros pueden ser: str, int, float, bool, FeatureSet,
    LinearUnit, DataFile, RasterData, o listas de estos.
    """
    gis = get_gis()
    tbx = import_toolbox(gp_url_or_item, gis=gis)
    func = getattr(tbx, tool_name, None)
    if func is None or not callable(func):
        available = [
            n for n in dir(tbx)
            if not n.startswith("_") and callable(getattr(tbx, n, None))
        ]
        raise ValueError(f"Tool '{tool_name}' no encontrado. Disponibles: {available}")

    sig = inspect.signature(func)
    params_detail = []
    for pname, param in sig.parameters.items():
        if pname == "gis":
            continue
        annotation = (
            str(param.annotation) if param.annotation is not inspect.Parameter.empty else "unknown"
        )
        default = (
            repr(param.default) if param.default is not inspect.Parameter.empty else "(required)"
        )
        params_detail.append({
            "name": pname,
            "type": annotation,
            "default": default,
            "required": param.default is inspect.Parameter.empty,
        })

    return {
        "tool_name": tool_name,
        "toolbox": gp_url_or_item,
        "signature": str(sig),
        "docstring": func.__doc__ or "(sin documentación)",
        "parameters": params_detail,
        "return_type": str(sig.return_annotation) if sig.return_annotation is not inspect.Parameter.empty else "unknown",
    }


@mcp.tool()
def gp_search_services(
    query: str = "",
    max_results: int = 20,
    org_only: bool = True,
) -> list:
    """Busca GP Services y Geoprocessing Toolboxes en el portal.

    query: palabras clave de búsqueda (vacío = todos los GP services accesibles).
    max_results: máximo de resultados a retornar.
    org_only: True = solo items de la organización; False = incluye public.

    Retorna items con id, título, tipo, propietario y URL.
    Usar el id o la URL con discover_gp_tools / run_gp_tool.
    """
    gis = get_gis()
    base_query = query.strip() if query.strip() else "*"
    search_scope = {"outside_org": not org_only}

    results = gis.content.search(
        query=base_query,
        item_type="Geoprocessing Service",
        max_items=max_results,
        **search_scope,
    )

    return [
        {
            "id": item.id,
            "title": item.title,
            "type": item.type,
            "owner": item.owner,
            "url": item.url,
            "snippet": item.snippet,
            "access": item.access,
        }
        for item in results
    ]


@mcp.tool()
def gp_service_info(gp_url_or_item: str) -> dict:
    """Describe un GP Service a nivel REST: tipo de ejecución, tasks y versión.

    gp_url_or_item: URL del GPServer o item ID.

    Retorna: nombre del servicio, versión del servidor, execution type
    (esriExecutionTypeSynchronous / esriExecutionTypeAsynchronous),
    lista de tasks disponibles con sus nombres y displayNames, y helpUrl.

    CRÍTICO: si executionType=Asynchronous → usar run_gp_tool_and_wait.
    Si Synchronous → usar run_gp_tool.
    """
    gis = get_gis()

    # Resolver item ID a URL si no es una URL directa
    url = gp_url_or_item
    if not gp_url_or_item.startswith("http"):
        item = gis.content.get(gp_url_or_item)
        if item is None:
            raise ValueError(f"Item no encontrado: {gp_url_or_item}")
        url = item.url

    # Consultar el endpoint REST del GPServer
    from arcgis._impl.common._mixins import PropertyMap
    try:
        params = {"f": "json", "token": gis._con.token}
        response = gis._con.get(url, params)
    except Exception as e:
        raise RuntimeError(f"Error consultando GP service '{url}': {e}") from e

    tasks = response.get("tasks", [])
    task_list = [{"name": t} if isinstance(t, str) else t for t in tasks]

    return {
        "url": url,
        "service_description": response.get("serviceDescription", ""),
        "current_version": response.get("currentVersion"),
        "execution_type": response.get("executionType"),
        "results_updated": response.get("resultsUpdated"),
        "max_record_count": response.get("maxRecordCount"),
        "tasks": task_list,
        "help_url": response.get("helpUrl"),
        "use_async": response.get("executionType") == "esriExecutionTypeAsynchronous",
    }


@mcp.tool()
def gp_linear_unit(
    distance: float,
    units: str = "esriMeters",
) -> dict:
    """Construye un objeto LinearUnit para usar como parámetro en GP tools.

    distance: valor numérico de la distancia.
    units: unidad de medida. Valores válidos:
        esriMeters, esriKilometers, esriFeet, esriMiles, esriYards,
        esriNauticalMiles, esriDecimalDegrees.

    Ejemplo de uso: pasar el dict retornado como valor de parámetro en run_gp_tool.
    El API de ArcGIS también acepta strings como "5 Miles" o "100 Meters".

    Equivalente a: arcgis.geoprocessing.LinearUnit(distance, units)
    """
    valid_units = {
        "esriMeters", "esriKilometers", "esriFeet", "esriMiles",
        "esriYards", "esriNauticalMiles", "esriDecimalDegrees",
    }
    if units not in valid_units:
        raise ValueError(f"Unidad '{units}' inválida. Válidas: {sorted(valid_units)}")

    return {
        "distance": distance,
        "units": units,
        "_type": "LinearUnit",
        "_string_form": f"{distance} {units.replace('esri', '')}",
        "_note": "Pasar el dict completo a run_gp_tool como valor del parámetro, "
                 "o usar el _string_form (ej. '5 Miles').",
    }


@mcp.tool()
def gp_data_file(
    url: str = "",
    item_id: str = "",
) -> dict:
    """Construye un objeto DataFile para referenciar archivos en GP tools.

    url: URL directa al archivo (ej. en ArcGIS Server directories).
    item_id: ID de un item en el portal que contiene el archivo.
    Uno de los dos es requerido.

    DataFile se usa en parámetros de tipo 'Data File' en GP tools.
    Equivalente a: arcgis.geoprocessing.DataFile(url=url, item_id=item_id)
    """
    if not url and not item_id:
        raise ValueError("Se requiere 'url' o 'item_id'.")

    result: dict[str, Any] = {"_type": "DataFile"}
    if url:
        result["url"] = url
    if item_id:
        result["itemID"] = item_id

    return result


@mcp.tool()
def gp_raster_data(
    url: str = "",
    item_id: str = "",
    format: str = "",
) -> dict:
    """Construye un objeto RasterData para referenciar rasters en GP tools.

    url: URL directa al servicio o archivo raster.
    item_id: ID de un item raster en el portal.
    format: formato del raster. Ejemplos: 'tif', 'jpg', 'png', 'img'.
    Uno de url o item_id es requerido.

    RasterData se usa en parámetros de tipo 'Raster Data Layer' en GP tools.
    Equivalente a: arcgis.geoprocessing.RasterData(url=url, item_id=item_id, format=format)
    """
    if not url and not item_id:
        raise ValueError("Se requiere 'url' o 'item_id'.")

    result: dict[str, Any] = {"_type": "RasterData"}
    if url:
        result["url"] = url
    if item_id:
        result["itemID"] = item_id
    if format:
        result["format"] = format

    return result


@mcp.tool()
def gp_run_with_env(
    gp_url_or_item: str,
    tool_name: str,
    params_json: str = "{}",
    out_spatial_reference: int = 4326,
    analysis_extent_json: str = "",
    process_spatial_reference: int = 0,
) -> dict:
    """Ejecuta un GP tool con configuración de entorno (arcgis.env). AVANZADO.

    gp_url_or_item: URL del GPServer o item ID.
    tool_name: nombre del tool (obtener con discover_gp_tools).
    params_json: JSON con parámetros del tool.
    out_spatial_reference: WKID del sistema de referencia de salida.
        4326 = WGS84, 102100 = Web Mercator, 0 = usar SR del servicio.
    analysis_extent_json: extent JSON para limitar el área de análisis.
        Ejemplo: '{"xmin":-77.5,"ymin":3.9,"xmax":-76.0,"ymax":5.0}'
        Vacío = sin restricción de extent.
    process_spatial_reference: WKID del SR de procesamiento interno.
        0 = usar el default del servicio.

    El entorno se aplica globalmente a arcgis.env antes de ejecutar y se
    restaura a los valores anteriores al finalizar.
    Equivalente a configurar arcgis.env.out_spatial_reference, etc.
    """
    import arcgis

    # Guardar valores anteriores
    prev_out_sr = getattr(arcgis.env, "out_spatial_reference", None)
    prev_extent = getattr(arcgis.env, "analysis_extent", None)
    prev_process_sr = getattr(arcgis.env, "process_spatial_reference", None)

    try:
        # Configurar entorno
        if out_spatial_reference != 0:
            arcgis.env.out_spatial_reference = out_spatial_reference
        if analysis_extent_json:
            arcgis.env.analysis_extent = json.loads(analysis_extent_json)
        if process_spatial_reference != 0:
            arcgis.env.process_spatial_reference = process_spatial_reference

        # Ejecutar tool
        gis = get_gis()
        tbx = import_toolbox(gp_url_or_item, gis=gis)
        func = getattr(tbx, tool_name, None)
        if func is None or not callable(func):
            available = [
                n for n in dir(tbx)
                if not n.startswith("_") and callable(getattr(tbx, n, None))
            ]
            raise ValueError(f"Tool '{tool_name}' no encontrado. Disponibles: {available}")

        params = json.loads(params_json) if params_json else {}
        result = func(**params)

        # Manejar resultado async
        if hasattr(result, "result") and callable(result.result):
            final_result = result.result()
            return {
                "status": "completed",
                "env_applied": {
                    "out_spatial_reference": out_spatial_reference if out_spatial_reference != 0 else None,
                    "analysis_extent": json.loads(analysis_extent_json) if analysis_extent_json else None,
                    "process_spatial_reference": process_spatial_reference if process_spatial_reference != 0 else None,
                },
                "result": _safe_result(final_result),
            }

        return {
            "status": "completed",
            "env_applied": {
                "out_spatial_reference": out_spatial_reference if out_spatial_reference != 0 else None,
            },
            "result": _safe_result(result),
        }

    finally:
        # Restaurar entorno anterior
        arcgis.env.out_spatial_reference = prev_out_sr
        arcgis.env.analysis_extent = prev_extent
        arcgis.env.process_spatial_reference = prev_process_sr


