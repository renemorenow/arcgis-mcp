from __future__ import annotations
import json
from typing import Any

from arcgis.mapping import MapImageLayer

from _server import mcp
from _auth import (
    get_gis, _require_write, _safe_result,
)

# =========================================================================== #
#   🗺️  WEB MAPS — item.get_data() / item.update(data=...)  (prefijo webmap_)
#
#   arcgis 2.4 eliminó WebMap de arcgis.mapping. La forma canónica server-side
#   es leer/modificar el JSON del item directamente sin widgets de Jupyter.
# =========================================================================== #


def _webmap_data(item) -> dict:
    """Lee el JSON completo del Web Map desde el portal."""
    data = item.get_data()
    if isinstance(data, str):
        data = json.loads(data)
    return data or {}


@mcp.tool()
def webmap_get(item_id: str) -> dict:
    """Retorna la estructura completa de un Web Map: capas, basemap y extent.

    item_id: ID del item de tipo 'Web Map' en el portal.

    Retorna: título, descripción, basemap, extent, número de capas operacionales
    y layers simplificadas (id, title, url, type, visibility, definitionExpression).
    Usa item.get_data() para leer el JSON del WebMap directamente (arcgis 2.4+).
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    data = _webmap_data(item)
    op_layers = data.get("operationalLayers", [])
    layers = [
        {
            "id": lyr.get("id"),
            "title": lyr.get("title"),
            "url": lyr.get("url"),
            "layerType": lyr.get("layerType"),
            "visibility": lyr.get("visibility", True),
            "opacity": lyr.get("opacity", 1.0),
            "definitionExpression": lyr.get("definitionExpression", ""),
        }
        for lyr in op_layers
    ]
    basemap = data.get("baseMap", {})
    return {
        "item_id": item_id,
        "title": item.title,
        "description": item.description or "",
        "basemap": basemap.get("title", ""),
        "version": data.get("version", ""),
        "layers_count": len(layers),
        "layers": layers,
    }


@mcp.tool()
def webmap_layers(item_id: str) -> list:
    """Lista todas las capas operacionales de un Web Map con sus propiedades.

    item_id: ID del item de tipo 'Web Map'.

    Retorna lista con: id, title, url, layerType, visibility, opacity,
    definitionExpression, itemId (si es una capa hosted), popupEnabled.
    Útil para auditar qué capas componen un mapa antes de editarlo.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    data = _webmap_data(item)
    result = []
    for lyr in data.get("operationalLayers", []):
        result.append({
            "id": lyr.get("id"),
            "title": lyr.get("title"),
            "url": lyr.get("url"),
            "layerType": lyr.get("layerType"),
            "visibility": lyr.get("visibility", True),
            "opacity": lyr.get("opacity", 1.0),
            "definitionExpression": lyr.get("definitionExpression", ""),
            "itemId": lyr.get("itemId"),
            "popupEnabled": lyr.get("popupInfo") is not None,
            "minScale": lyr.get("minScale", 0),
            "maxScale": lyr.get("maxScale", 0),
        })
    return result


@mcp.tool()
def webmap_add_layer(
    item_id: str,
    layer_item_id: str,
    title: str = "",
    visibility: bool = True,
    dry_run: bool = True,
) -> dict:
    """Agrega una capa a un Web Map existente. OPERACIÓN DE ESCRITURA.

    item_id: ID del Web Map al que agregar la capa.
    layer_item_id: ID del item del portal que contiene la capa (Feature Layer, Map Service, etc.).
    title: título personalizado para la capa en el mapa. Vacío = usa el título del item.
    visibility: True = visible por defecto.
    dry_run: True por defecto — simula sin guardar.

    Equivale a WebMap(item).add_layer(layer_item) + WebMap.update().
    """
    _require_write()
    gis = get_gis()
    map_item = gis.content.get(item_id)
    if map_item is None:
        raise ValueError(f"Web Map no encontrado: {item_id}")
    layer_item = gis.content.get(layer_item_id)
    if layer_item is None:
        raise ValueError(f"Layer item no encontrado: {layer_item_id}")

    if dry_run:
        return {
            "dry_run": True,
            "webmap_id": item_id,
            "would_add": {"item_id": layer_item_id, "title": title or layer_item.title, "visibility": visibility},
        }

    data = _webmap_data(map_item)
    import uuid
    new_layer: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": title or layer_item.title,
        "itemId": layer_item_id,
        "url": layer_item.url or "",
        "visibility": visibility,
        "opacity": 1.0,
        "layerType": "ArcGISFeatureLayer" if "Feature" in (layer_item.type or "") else "ArcGISMapServiceLayer",
    }
    data.setdefault("operationalLayers", []).append(new_layer)
    success = map_item.update(item_properties={}, data=json.dumps(data))
    return {"success": success, "webmap_id": item_id, "added_layer": layer_item_id}


@mcp.tool()
def webmap_remove_layer(
    item_id: str,
    layer_title: str,
    dry_run: bool = True,
) -> dict:
    """Remueve una capa de un Web Map por su título. OPERACIÓN DE ESCRITURA.

    item_id: ID del Web Map.
    layer_title: título exacto de la capa a remover (obtener con webmap_layers).
    dry_run: True por defecto — simula sin guardar.

    Equivale a WebMap(item).remove_layer(layer) + WebMap.update().
    """
    _require_write()
    gis = get_gis()
    map_item = gis.content.get(item_id)
    if map_item is None:
        raise ValueError(f"Web Map no encontrado: {item_id}")
    data = _webmap_data(map_item)
    target = None
    for lyr in data.get("operationalLayers", []):
        if lyr.get("title") == layer_title:
            target = lyr
            break
    if target is None:
        available = [l.get("title") for l in data.get("operationalLayers", [])]
        raise ValueError(f"Capa '{layer_title}' no encontrada. Disponibles: {available}")

    if dry_run:
        return {
            "dry_run": True,
            "webmap_id": item_id,
            "would_remove": {"title": layer_title, "url": target.get("url")},
        }

    data["operationalLayers"] = [l for l in data["operationalLayers"] if l.get("title") != layer_title]
    success = map_item.update(item_properties={}, data=json.dumps(data))
    return {"success": success, "webmap_id": item_id, "removed_layer": layer_title}


@mcp.tool()
def webmap_update_layer(
    item_id: str,
    layer_title: str,
    definition_expression: str = "",
    visible: bool | None = None,
    opacity: float = -1.0,
    dry_run: bool = True,
) -> dict:
    """Actualiza propiedades de una capa en un Web Map. OPERACIÓN DE ESCRITURA.

    item_id: ID del Web Map.
    layer_title: título exacto de la capa (obtener con webmap_layers).
    definition_expression: nueva expresión SQL de filtro. Vacío = sin cambio.
        Ejemplo: "MUNICIPIO = 'Bogotá' AND ESTADO = 'Activo'"
    visible: True/False para mostrar/ocultar la capa. None = sin cambio.
    opacity: valor entre 0.0 y 1.0. -1.0 = sin cambio.
    dry_run: True por defecto — simula sin guardar.

    Equivale a modificar la definición de la capa + WebMap.update().
    """
    _require_write()
    gis = get_gis()
    map_item = gis.content.get(item_id)
    if map_item is None:
        raise ValueError(f"Web Map no encontrado: {item_id}")
    data = _webmap_data(map_item)
    target = None
    for lyr in data.get("operationalLayers", []):
        if lyr.get("title") == layer_title:
            target = lyr
            break
    if target is None:
        available = [l.get("title") for l in data.get("operationalLayers", [])]
        raise ValueError(f"Capa '{layer_title}' no encontrada. Disponibles: {available}")

    changes: dict[str, Any] = {}
    if definition_expression:
        changes["definitionExpression"] = definition_expression
    if visible is not None:
        changes["visibility"] = visible
    if 0.0 <= opacity <= 1.0:
        changes["opacity"] = opacity

    if not changes:
        return {"error": "No se proporcionaron cambios", "webmap_id": item_id}

    if dry_run:
        return {
            "dry_run": True,
            "webmap_id": item_id,
            "layer": layer_title,
            "would_apply": changes,
            "current": {"visibility": target.get("visibility"), "opacity": target.get("opacity"), "definitionExpression": target.get("definitionExpression", "")},
        }

    target.update(changes)
    success = map_item.update(item_properties={}, data=json.dumps(data))
    return {"success": success, "webmap_id": item_id, "layer": layer_title, "applied": changes}


@mcp.tool()
def webmap_create(
    title: str,
    tags: str = '["webmap"]',
    basemap: str = "topo-vector",
    folder: str = "",
    dry_run: bool = True,
) -> dict:
    """Crea un nuevo Web Map vacío en el portal. OPERACIÓN DE ESCRITURA.

    title: título del nuevo Web Map.
    tags: JSON array de etiquetas. Ej: '["gis", "operativo"]'
    basemap: basemap inicial. Valores comunes:
        'topo-vector', 'streets-vector', 'satellite', 'hybrid',
        'gray-vector', 'dark-gray-vector', 'oceans', 'osm'.
    folder: carpeta destino en el portal. Vacío = raíz del usuario.
    dry_run: True por defecto — simula sin crear.

    Equivale a gis.map(basemap=basemap).save({...}).
    """
    _require_write()
    gis = get_gis()
    tag_list = json.loads(tags) if tags else ["webmap"]

    if dry_run:
        return {
            "dry_run": True,
            "would_create": {"title": title, "basemap": basemap, "tags": tag_list, "folder": folder or "(raíz)"},
        }

    wm_json = {
        "operationalLayers": [],
        "baseMap": {
            "title": basemap,
            "baseMapLayers": [{"id": "defaultBasemap", "layerType": "ArcGISTiledMapServiceLayer", "title": basemap, "visibility": True, "opacity": 1}],
        },
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "version": "2.30",
    }
    item_props: dict[str, Any] = {
        "title": title,
        "type": "Web Map",
        "tags": ",".join(tag_list),
        "snippet": "Web Map creado via MCP",
        "text": json.dumps(wm_json),
    }
    new_item = gis.content.add(item_props, folder=folder or None)
    return {
        "success": True,
        "item_id": new_item.id,
        "title": new_item.title,
        "url": new_item.homepage,
    }



# =========================================================================== #
#   🖼️  MAP IMAGE LAYER / SERVICIOS DINÁMICOS — arcgis.mapping.MapImageLayer
#       (prefijo mil_)
# =========================================================================== #

@mcp.tool()
def mil_info(url_or_item: str) -> dict:
    """Describe un Map Service dinámico (MapImageLayer): capabilities, SR, capas.

    url_or_item: URL del MapServer o item ID del portal.
        URL: 'https://server/arcgis/rest/services/Catastro/MapServer'
        Item ID: '8abc123...'

    Retorna: nombre, versión del server, capabilities (Query/Map/Data/etc.),
    sistema de referencia espacial, número de capas, extent inicial, y
    si soporta export dinámico.
    Equivale a arcgis.mapping.MapImageLayer(url, gis=gis).properties.
    """
    gis = get_gis()
    url = url_or_item
    if not url_or_item.startswith("http"):
        item = gis.content.get(url_or_item)
        if item is None:
            raise ValueError(f"Item no encontrado: {url_or_item}")
        url = item.url

    mil = MapImageLayer(url, gis=gis)
    props = mil.properties
    return {
        "url": url,
        "service_description": props.get("serviceDescription", ""),
        "map_name": props.get("mapName", ""),
        "current_version": props.get("currentVersion"),
        "capabilities": props.get("capabilities", ""),
        "export_tiles_allowed": props.get("exportTilesAllowed", False),
        "max_record_count": props.get("maxRecordCount"),
        "supported_query_formats": props.get("supportedQueryFormats", ""),
        "spatial_reference": _safe_result(props.get("spatialReference")),
        "initial_extent": _safe_result(props.get("initialExtent")),
        "full_extent": _safe_result(props.get("fullExtent")),
        "layers_count": len(mil.layers),
        "tables_count": len(props.get("tables", [])),
    }


@mcp.tool()
def mil_sublayers(url_or_item: str) -> list:
    """Lista las subcapas de un Map Service dinámico con su configuración.

    url_or_item: URL del MapServer o item ID del portal.

    Retorna por cada subcapa: id, name, type, geometryType, parentLayerId,
    minScale, maxScale, visible por default, y si tiene tiempo habilitado.
    Equivale a arcgis.mapping.MapImageLayer(url).layers.
    """
    gis = get_gis()
    url = url_or_item
    if not url_or_item.startswith("http"):
        item = gis.content.get(url_or_item)
        if item is None:
            raise ValueError(f"Item no encontrado: {url_or_item}")
        url = item.url

    mil = MapImageLayer(url, gis=gis)
    result = []
    for lyr in mil.layers:
        lp = lyr.properties
        result.append({
            "id": lp.get("id"),
            "name": lp.get("name"),
            "type": lp.get("type"),
            "geometryType": lp.get("geometryType"),
            "parentLayerId": lp.get("parentLayerId", -1),
            "subLayerIds": lp.get("subLayerIds"),
            "defaultVisibility": lp.get("defaultVisibility", True),
            "minScale": lp.get("minScale", 0),
            "maxScale": lp.get("maxScale", 0),
            "hasTimeData": lp.get("timeInfo") is not None,
        })
    return result


@mcp.tool()
def mil_query(
    url_or_item: str,
    layer_id: int,
    where: str = "1=1",
    out_fields: str = "*",
    max_records: int = 100,
    out_sr: int = 4326,
) -> dict:
    """Consulta una subcapa de un Map Service dinámico.

    url_or_item: URL del MapServer o item ID del portal.
    layer_id: ID numérico de la subcapa (obtener con mil_sublayers).
    where: cláusula SQL de filtro. '1=1' = todos los registros.
    out_fields: campos a retornar, separados por coma. '*' = todos.
    max_records: máximo de registros. Default 100.
    out_sr: WKID del SR de salida. 4326 = WGS84.

    Retorna: features con atributos y geometría (si la subcapa la tiene).
    Equivale a MapImageLayer(url).layers[id].query(where=..., ...).
    """
    gis = get_gis()
    url = url_or_item
    if not url_or_item.startswith("http"):
        item = gis.content.get(url_or_item)
        if item is None:
            raise ValueError(f"Item no encontrado: {url_or_item}")
        url = item.url

    mil = MapImageLayer(url, gis=gis)
    sublayers = {lyr.properties.get("id"): lyr for lyr in mil.layers}
    if layer_id not in sublayers:
        available = list(sublayers.keys())
        raise ValueError(f"Layer ID {layer_id} no encontrado. Disponibles: {available}")

    fields_list = [f.strip() for f in out_fields.split(",")] if out_fields != "*" else ["*"]
    fset = sublayers[layer_id].query(
        where=where,
        out_fields=fields_list,
        record_count=max_records,
        out_sr=out_sr,
        return_geometry=True,
    )
    features = []
    for f in (fset.features if fset else []):
        features.append({
            "attributes": f.attributes,
            "geometry": _safe_result(f.geometry),
        })
    return {
        "layer_id": layer_id,
        "feature_count": len(features),
        "spatial_reference": {"wkid": out_sr},
        "features": features,
    }



# =========================================================================== #
#   🌐  WEB SCENES — item.get_data()  (prefijo webscene_)
#
#   arcgis 2.4 eliminó WebScene de arcgis.mapping. Se usa item.get_data()
#   para leer el JSON de la escena directamente (mismo patrón que webmap_*).
# =========================================================================== #

@mcp.tool()
def webscene_get(item_id: str) -> dict:
    """Retorna la estructura completa de un Web Scene (mapa 3D).

    item_id: ID del item de tipo 'Web Scene' en el portal.

    Retorna: título, descripción, tipo de escena (global/local), capas operacionales,
    ground (elevación), basemap, cámara inicial y extent.
    Usa item.get_data() para leer el JSON directamente (arcgis 2.4+).
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    data = item.get_data()
    if isinstance(data, str):
        data = json.loads(data)
    data = data or {}
    op_layers = data.get("operationalLayers", [])
    layers = [
        {
            "id": lyr.get("id"),
            "title": lyr.get("title"),
            "url": lyr.get("url"),
            "layerType": lyr.get("layerType"),
            "visibility": lyr.get("visibility", True),
        }
        for lyr in op_layers
    ]
    return {
        "item_id": item_id,
        "title": item.title,
        "description": item.description or "",
        "scene_type": data.get("viewingMode", "global"),
        "version": data.get("version", ""),
        "layers_count": len(layers),
        "layers": layers,
        "basemap": _safe_result(data.get("baseMap", {}).get("title")),
        "initial_camera": _safe_result(data.get("initialState", {}).get("camera")),
    }


@mcp.tool()
def webscene_layers(item_id: str) -> list:
    """Lista las capas operacionales y de ambiente de un Web Scene.

    item_id: ID del item de tipo 'Web Scene'.

    Retorna por cada capa: id, title, url, layerType, visibility,
    opacity, y si es una capa de entorno (ground, basemap).
    Usa item.get_data() para leer el JSON directamente (arcgis 2.4+).
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    data = item.get_data()
    if isinstance(data, str):
        data = json.loads(data)
    data = data or {}
    result = []
    for lyr in data.get("operationalLayers", []):
        result.append({
            "id": lyr.get("id"),
            "title": lyr.get("title"),
            "url": lyr.get("url"),
            "layerType": lyr.get("layerType"),
            "visibility": lyr.get("visibility", True),
            "opacity": lyr.get("opacity", 1.0),
            "itemId": lyr.get("itemId"),
            "elevationInfo": _safe_result(lyr.get("elevationInfo")),
        })
    return result


