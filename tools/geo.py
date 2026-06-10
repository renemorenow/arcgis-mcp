from __future__ import annotations

import inspect
import json
import sys
import traceback
from typing import Any, Optional

from arcgis.features import FeatureLayer, FeatureLayerCollection, FeatureSet
from arcgis.features import FeatureCollection
from arcgis.geoprocessing import import_toolbox
from arcgis.mapping import MapImageLayer
from arcgis import geocoding as arcgis_geocoding
from arcgis.geometry import functions as geom_functions

from _server import mcp
from _auth import (
    get_gis, detect_platform, WRITE_ENABLED,
    _require_write, _require_enterprise, _resolve_layer, _safe_result,
)

# =========================================================================== #
#   📍 GEOCODIFICACIÓN — arcgis.geocoding  (prefijo geocode_)
# =========================================================================== #

@mcp.tool()
def geocode(
    address: str,
    max_locations: int = 5,
    out_sr: int = 4326,
    source_country: str = "",
) -> list:
    """Geocodifica una dirección o descripción de lugar a coordenadas.

    address: texto de la dirección o descripción. Ej: 'Carrera 7 # 32-33, Bogotá'
    max_locations: número máximo de candidatos a retornar (default 5).
    out_sr: WKID del sistema de referencia de salida. 4326 = WGS84.
    source_country: código ISO del país para mejorar precisión. Ej: 'COL', 'ARG', 'MEX'.
        Vacío = búsqueda global.

    Retorna lista de candidatos con: address, score (0-100), x, y, y extent.
    Usa el localizador de ArcGIS Online por defecto.
    Equivale a arcgis.geocoding.geocode(address, geocoder=geocoder, ...).
    """
    gis = get_gis()
    geocoders = arcgis_geocoding.get_geocoders(gis)
    geocoder = geocoders[0] if geocoders else None
    kwargs: dict[str, Any] = {
        "address": address,
        "max_locations": max_locations,
        "as_featureset": False,
        "geocoder": geocoder,
    }
    if out_sr != 4326:
        kwargs["out_sr"] = {"wkid": out_sr}
    if source_country:
        kwargs["source_country"] = source_country

    results = arcgis_geocoding.geocode(**kwargs)
    return [
        {
            "address": r.get("address", ""),
            "score": r.get("score", 0),
            "x": r.get("location", {}).get("x"),
            "y": r.get("location", {}).get("y"),
            "extent": r.get("extent"),
            "attributes": r.get("attributes", {}),
        }
        for r in (results or [])
    ]


@mcp.tool()
def reverse_geocode(
    x: float,
    y: float,
    sr: int = 4326,
    distance: float = 100.0,
) -> dict:
    """Convierte coordenadas a una dirección (geocodificación inversa).

    x: longitud (si sr=4326) o coordenada X en el SR especificado.
    y: latitud (si sr=4326) o coordenada Y en el SR especificado.
    sr: WKID del sistema de referencia de las coordenadas. Default 4326 (WGS84).
    distance: radio de búsqueda en metros (default 100).

    Retorna: dirección completa, ciudad, región, código postal, país y coordenadas exactas.
    Equivale a arcgis.geocoding.reverse_geocode(location, geocoder=geocoder, ...).
    """
    gis = get_gis()
    geocoders = arcgis_geocoding.get_geocoders(gis)
    geocoder = geocoders[0] if geocoders else None
    location = {"x": x, "y": y, "spatialReference": {"wkid": sr}}
    result = arcgis_geocoding.reverse_geocode(location=location, distance=distance, geocoder=geocoder)
    if result is None:
        return {"error": f"No se encontró dirección para ({x}, {y})"}
    return {
        "address": result.get("address", {}),
        "location": result.get("location", {}),
    }


@mcp.tool()
def geocode_suggest(
    text: str,
    max_suggestions: int = 5,
    source_country: str = "",
    location_x: float = 0.0,
    location_y: float = 0.0,
) -> list:
    """Retorna sugerencias de autocompletado para un texto parcial de dirección.

    text: texto parcial de la dirección. Ej: 'Calle 100 Bog'
    max_suggestions: número máximo de sugerencias.
    source_country: código ISO del país. Ej: 'COL'. Vacío = global.
    location_x: longitud WGS84 del centro de búsqueda (0 = sin centro).
    location_y: latitud WGS84 del centro de búsqueda (0 = sin centro).

    Retorna lista de sugerencias con text, magicKey (para pasar a geocode) y isCollection.
    Equivale a arcgis.geocoding.suggest(text, geocoder=geocoder, ...).
    """
    gis = get_gis()
    geocoders = arcgis_geocoding.get_geocoders(gis)
    geocoder = geocoders[0] if geocoders else None
    kwargs: dict[str, Any] = {"text": text, "max_suggestions": max_suggestions, "geocoder": geocoder}
    if source_country:
        kwargs["country_code"] = source_country  # renombrado en arcgis 2.4
    if location_x != 0.0 and location_y != 0.0:
        kwargs["location"] = {"x": location_x, "y": location_y, "spatialReference": {"wkid": 4326}}

    result = arcgis_geocoding.suggest(**kwargs)
    # En 2.4 suggest retorna dict con clave 'suggestions'
    if isinstance(result, dict):
        return result.get("suggestions", [])
    return result if isinstance(result, list) else []


@mcp.tool()
def batch_geocode(
    addresses_json: str,
    source_country: str = "",
    out_sr: int = 4326,
) -> list:
    """Geocodifica una lista de direcciones en lote. USA CRÉDITOS en ArcGIS Online.

    addresses_json: JSON array de strings o dicts con campos de dirección.
        Formato string: '["Calle 10 # 5-20 Bogotá", "Av Caracas 45 Bogotá"]'
        Formato dict: '[{"Address": "Calle 10", "City": "Bogotá", "CountryCode": "COL"}]'
    source_country: código ISO del país para mejorar precisión. Ej: 'COL'.
    out_sr: WKID del SR de salida. 4326 = WGS84.

    ⚠️ ADVERTENCIA: Esta operación consume créditos de ArcGIS Online.
    Equivale a arcgis.geocoding.batch_geocode(addresses, geocoder=geocoder, ...).
    """
    _require_write()
    gis = get_gis()
    geocoders = arcgis_geocoding.get_geocoders(gis)
    geocoder = geocoders[0] if geocoders else None
    addresses = json.loads(addresses_json)
    kwargs: dict[str, Any] = {"addresses": addresses, "geocoder": geocoder}
    if out_sr != 4326:
        kwargs["out_sr"] = {"wkid": out_sr}
    if source_country:
        kwargs["source_country"] = source_country

    results = arcgis_geocoding.batch_geocode(**kwargs)
    output = []
    for r in (results or []):
        loc = r.get("location") or {}
        output.append({
            "address": r.get("address", ""),
            "score": r.get("score", 0),
            "status": r.get("status", ""),
            "x": loc.get("x"),
            "y": loc.get("y"),
            "attributes": r.get("attributes", {}),
        })
    return output


# =========================================================================== #
#   📐 GEOMETRÍA — arcgis.geometry.functions  (prefijo geometry_)
# =========================================================================== #

@mcp.tool()
def geometry_project(
    geometries_json: str,
    in_sr: int,
    out_sr: int,
) -> list:
    """Reproyecta geometrías de un sistema de referencia a otro (server-side).

    geometries_json: JSON array de geometrías ArcGIS. Ej:
        '[{"x": -74.07, "y": 4.71, "spatialReference": {"wkid": 4326}}]'
        '[{"rings": [[[...]]]}]'
    in_sr: WKID del SR de entrada. Ej: 4326 (WGS84), 3116 (MAGNA-SIRGAS / Colombia), 102100.
    out_sr: WKID del SR de salida.

    Retorna lista de geometrías en el nuevo SR.
    Equivale a arcgis.geometry.functions.project(geometries, in_sr, out_sr, gis=gis).
    """
    gis = get_gis()
    geoms = json.loads(geometries_json)
    result = geom_functions.project(
        geometries=geoms,
        in_sr=in_sr,
        out_sr=out_sr,
        gis=gis,
    )
    return _safe_result(result)


@mcp.tool()
def geometry_buffer(
    geometries_json: str,
    distances: str,
    unit: str = "esriMeters",
    in_sr: int = 4326,
    out_sr: int = 4326,
) -> list:
    """Genera buffers alrededor de geometrías (server-side).

    geometries_json: JSON array de geometrías ArcGIS.
        Puntos: '[{"x": -74.07, "y": 4.71}]'
        Polígonos: '[{"rings": [[[...]]]}]'
    distances: JSON array de distancias. Ej: '[500]' o '[500, 1000, 2000]'.
        Si hay menos distancias que geometrías, se reutiliza la última.
    unit: unidad de medida. Valores comunes:
        'esriMeters', 'esriKilometers', 'esriFeet', 'esriMiles'.
    in_sr: WKID del SR de las geometrías de entrada. Default 4326.
    out_sr: WKID del SR de las geometrías de salida. Default 4326.

    Retorna lista de polígonos buffer.
    Equivale a arcgis.geometry.functions.buffer(geometries, distances, unit, ..., gis=gis).
    """
    gis = get_gis()
    geoms = json.loads(geometries_json)
    dists = json.loads(distances)
    result = geom_functions.buffer(
        geometries=geoms,
        distances=dists,
        unit=unit,
        in_sr=in_sr,
        out_sr=out_sr,
        gis=gis,
    )
    return _safe_result(result)


@mcp.tool()
def geometry_area_length(
    geometries_json: str,
    length_unit: str = "esriMeters",
    area_unit: str = "esriSquareMeters",
    sr: int = 4326,
) -> list:
    """Calcula áreas y longitudes de geometrías (server-side).

    geometries_json: JSON array de geometrías ArcGIS (polígonos o polilíneas).
    length_unit: unidad de longitud. Ej: 'esriMeters', 'esriKilometers', 'esriFeet'.
    area_unit: unidad de área. Ej: 'esriSquareMeters', 'esriHectares', 'esriAcres', 'esriSquareKilometers'.
    sr: WKID del SR de las geometrías. Default 4326 (WGS84).

    Retorna lista de dicts con 'area' y 'length' para cada geometría.
    Equivale a arcgis.geometry.functions.areas_and_lengths(geometries, ..., gis=gis).
    """
    gis = get_gis()
    geoms = json.loads(geometries_json)
    result = geom_functions.areas_and_lengths(
        polygons=geoms,
        length_unit=length_unit,
        area_unit={"areaUnit": area_unit},
        calculation_type="geodesic",
        spatial_ref=sr,
        gis=gis,
    )
    return _safe_result(result)


@mcp.tool()
def geometry_simplify(
    geometries_json: str,
    sr: int = 4326,
) -> list:
    """Simplifica geometrías para que sean topológicamente correctas (server-side).

    geometries_json: JSON array de geometrías ArcGIS.
    sr: WKID del SR de las geometrías. Default 4326.

    Simplify hace que los polígonos sean válidos (sin auto-intersecciones, etc.).
    Útil antes de operaciones espaciales o de edición.
    Equivale a arcgis.geometry.functions.simplify(geometries, spatial_ref=sr, gis=gis).
    """
    gis = get_gis()
    geoms = json.loads(geometries_json)
    result = geom_functions.simplify(
        spatial_ref=sr,
        geometries=geoms,
        gis=gis,
    )
    return _safe_result(result)


