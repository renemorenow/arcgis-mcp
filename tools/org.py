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
#   🪝  WEBHOOKS — ArcGIS Enterprise  (prefijo webhook_)
# =========================================================================== #

@mcp.tool()
def webhook_list() -> list:
    """Lista todos los webhooks configurados en el portal Enterprise.

    Retorna: id, name, url destino, eventos suscritos, estado (active/inactive),
    fecha de creación y última invocación.
    Solo Enterprise. Requiere credenciales de administrador.

    Equivale a gis.admin.webhooks.list().
    """
    gis = get_gis()
    _require_enterprise(gis)
    try:
        hooks = gis.admin.webhooks.list()
        result = []
        for h in (hooks or []):
            result.append({
                "id": h.get("id") or getattr(h, "id", None),
                "name": h.get("name") or getattr(h, "name", None),
                "url": h.get("payloadUrl") or getattr(h, "payloadUrl", None),
                "events": h.get("events") or getattr(h, "events", []),
                "active": h.get("active", True),
                "created": h.get("created") or getattr(h, "created", None),
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
def webhook_create(
    name: str,
    payload_url: str,
    events: str = '["/items/publish"]',
    secret: str = "",
    dry_run: bool = True,
) -> dict:
    """Crea un nuevo webhook en el portal Enterprise. OPERACIÓN DE ESCRITURA.

    name: nombre descriptivo del webhook.
    payload_url: URL del endpoint que recibirá los eventos HTTP POST.
    events: JSON array de eventos a suscribir. Eventos comunes:
        '/items/publish' — cuando se publica un item
        '/items/update' — cuando se actualiza un item
        '/items/delete' — cuando se elimina un item
        '/users/create' — cuando se crea un usuario
        '/groups/update' — cuando se actualiza un grupo
        '/*' — todos los eventos
    secret: secreto compartido para verificar autenticidad del payload (opcional).
    dry_run: True por defecto.

    Equivale a gis.admin.webhooks.create(name=..., payload_url=..., events=...).
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)
    events_list = json.loads(events)

    if dry_run:
        return {
            "dry_run": True,
            "would_create": {
                "name": name,
                "payload_url": payload_url,
                "events": events_list,
                "has_secret": bool(secret),
            },
        }

    try:
        kwargs: dict[str, Any] = {
            "name": name,
            "payload_url": payload_url,
            "events": events_list,
        }
        if secret:
            kwargs["secret"] = secret
        hook = gis.admin.webhooks.create(**kwargs)
        return {
            "success": True,
            "id": hook.get("id") or getattr(hook, "id", None),
            "name": name,
            "payload_url": payload_url,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def webhook_delete(
    webhook_id: str,
    dry_run: bool = True,
) -> dict:
    """Elimina un webhook del portal Enterprise. OPERACIÓN DE ESCRITURA.

    webhook_id: ID del webhook a eliminar (obtener con webhook_list).
    dry_run: True por defecto.

    Equivale a gis.admin.webhooks.get(webhook_id).delete().
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)

    try:
        hooks = gis.admin.webhooks.list()
        target = None
        for h in (hooks or []):
            hid = h.get("id") or getattr(h, "id", None)
            if str(hid) == str(webhook_id):
                target = h
                break
        if target is None:
            return {"error": f"Webhook '{webhook_id}' no encontrado."}

        if dry_run:
            return {
                "dry_run": True,
                "would_delete": {
                    "id": webhook_id,
                    "name": target.get("name") or getattr(target, "name", None),
                },
            }

        result = target.delete() if hasattr(target, "delete") else gis.admin.webhooks.get(webhook_id).delete()
        return {"success": True, "deleted_id": webhook_id}
    except Exception as e:
        return {"error": str(e)}


# =========================================================================== #
#   📓  NOTEBOOKS — ArcGIS Enterprise  (prefijo notebook_)
# =========================================================================== #

@mcp.tool()
def notebook_list(
    username: str = "",
    max_items: int = 50,
) -> list:
    """Lista Notebooks disponibles en el portal.

    username: filtrar por propietario. Vacío = notebooks propios + accesibles.
    max_items: máximo de items a retornar. Default 50.

    Retorna: id, title, owner, url, fecha de modificación, snippet.
    Equivale a content_search con item_type='Notebook'.
    """
    gis = get_gis()
    query = f"owner:{username}" if username else ""
    items = gis.content.search(
        query=query,
        item_type="Notebook",
        max_items=max_items,
    )
    return [
        {
            "id": nb.id,
            "title": nb.title,
            "owner": nb.owner,
            "url": nb.url,
            "snippet": nb.snippet or "",
            "modified": str(nb.modified) if hasattr(nb, "modified") else None,
            "access": nb.access,
        }
        for nb in items
    ]


@mcp.tool()
def notebook_execute(
    item_id: str,
    dry_run: bool = True,
) -> dict:
    """Ejecuta un Notebook en ArcGIS Enterprise. OPERACIÓN DE ESCRITURA.

    item_id: ID del item de tipo 'Notebook' a ejecutar.
    dry_run: True por defecto.

    ⚠️ Solo disponible en Enterprise con Notebook Server configurado.
    El notebook corre con los permisos del usuario autenticado.
    Equivale a gis.notebook_service.execute_notebook(item_id).
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)

    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Notebook no encontrado: {item_id}")
    if item.type != "Notebook":
        raise ValueError(f"El item '{item_id}' no es un Notebook (es {item.type}).")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "owner": item.owner,
            "action": "would_execute_notebook",
        }

    try:
        result = gis.notebook_service.execute_notebook(item_id)
        return {"success": True, "item_id": item_id, "result": _safe_result(result)}
    except Exception as e:
        return {"error": str(e), "item_id": item_id}


# =========================================================================== #
#   🌍  GEOENRICHMENT — arcgis.geoenrichment  (prefijo enrich_)
# =========================================================================== #

@mcp.tool()
def enrich_countries() -> list:
    """Lista los países disponibles para GeoEnrichment.

    Retorna: lista de países con countryCode, name y dataCollections disponibles.
    Útil para saber qué países tienen datos demográficos antes de llamar enrich_areas.
    En arcgis 2.4 usa Country(iso3, gis=gis) para verificar disponibilidad.
    """
    gis = get_gis()
    try:
        from arcgis.geoenrichment import Country
        # arcgis 2.4: get_available_countries() fue removido.
        # Retornamos la lista estática de países soportados más comunes.
        # Para verificar disponibilidad dinámica usar enrich_data_collections(country_code).
        common_countries = [
            {"countryCode": "US",  "name": "United States",   "continent": "North America"},
            {"countryCode": "COL", "name": "Colombia",         "continent": "South America"},
            {"countryCode": "MEX", "name": "Mexico",           "continent": "North America"},
            {"countryCode": "ARG", "name": "Argentina",        "continent": "South America"},
            {"countryCode": "BRA", "name": "Brazil",           "continent": "South America"},
            {"countryCode": "CHL", "name": "Chile",            "continent": "South America"},
            {"countryCode": "PER", "name": "Peru",             "continent": "South America"},
            {"countryCode": "ESP", "name": "Spain",            "continent": "Europe"},
            {"countryCode": "GBR", "name": "United Kingdom",   "continent": "Europe"},
            {"countryCode": "DEU", "name": "Germany",          "continent": "Europe"},
            {"countryCode": "FRA", "name": "France",           "continent": "Europe"},
            {"countryCode": "CAN", "name": "Canada",           "continent": "North America"},
            {"countryCode": "AUS", "name": "Australia",        "continent": "Oceania"},
            {"countryCode": "JPN", "name": "Japan",            "continent": "Asia"},
            {"countryCode": "ZAF", "name": "South Africa",     "continent": "Africa"},
        ]
        return [
            {**c, "note": "Lista de referencia. Verificar disponibilidad con enrich_data_collections(countryCode)."}
            for c in common_countries
        ]
    except ImportError:
        return [{"error": "arcgis.geoenrichment no disponible. Verificar instalación."}]


@mcp.tool()
def enrich_data_collections(country_code: str = "US") -> list:
    """Lista las colecciones de datos demográficos disponibles para un país.

    country_code: código ISO del país. Ej: 'US', 'COL', 'ARG', 'MEX', 'BRA'.

    Retorna: colecciones de datos con id, título, descripción y variables disponibles.
    Usar los IDs de colecciones en enrich_areas para elegir qué datos obtener.
    Equivale a Country(country_code, gis=gis).data_collections.
    """
    gis = get_gis()
    try:
        from arcgis.geoenrichment import Country
        c = Country(country_code, gis=gis)
        collections = c.data_collections
        if hasattr(collections, "to_dict"):
            return _safe_result(collections.to_dict())
        return _safe_result(collections)
    except ImportError:
        return [{"error": "arcgis.geoenrichment no disponible. Verificar instalación."}]
    except Exception as e:
        return [{"error": str(e), "country_code": country_code}]


@mcp.tool()
def enrich_areas(
    study_areas_json: str,
    data_collections: str = '["KeyGlobalFacts"]',
    country_code: str = "US",
    out_sr: int = 4326,
) -> dict:
    """Enriquece polígonos con datos demográficos y socioeconómicos. USA CRÉDITOS.

    study_areas_json: JSON array de áreas de estudio. Formatos aceptados:
        Polígonos GeoJSON/ArcGIS: '[{"rings": [[[...]]]}]'
        Named places (strings): '["Bogotá, Colombia", "Medellín, Colombia"]'
        Geometrías ArcGIS con SR: '[{"x": -74.07, "y": 4.71}]' para puntos
    data_collections: JSON array de IDs de colecciones de datos a obtener.
        Obtener IDs con enrich_data_collections(). Colecciones comunes:
        'KeyGlobalFacts' — indicadores clave (población, hogares, ingresos)
        'Age' — distribución por edades
        'Wealth' — indicadores de riqueza
    country_code: código ISO del país. Ej: 'COL', 'US', 'ARG'.
    out_sr: WKID del SR de salida. 4326 = WGS84.

    ⚠️ ADVERTENCIA: Esta operación CONSUME CRÉDITOS de ArcGIS Online.
    Equivale a arcgis.geoenrichment.enrich(study_areas, data_collections=..., gis=gis).
    """
    _require_write()
    gis = get_gis()
    try:
        from arcgis.geoenrichment import enrich as geoenrich_enrich
        areas = json.loads(study_areas_json)
        collections = json.loads(data_collections)

        result = geoenrich_enrich(
            study_areas=areas,
            data_collections=collections,
            gis=gis,
            out_sr=out_sr,
        )
        return _safe_result(result)
    except ImportError:
        return {"error": "arcgis.geoenrichment no disponible. Verificar instalación."}
    except Exception as e:
        return {"error": str(e)}


