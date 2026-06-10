from __future__ import annotations
import json
from typing import Any

from arcgis.features import FeatureLayerCollection

from _server import mcp
from _auth import (
    get_gis, _require_write, _resolve_layer, _safe_result,
)

from tools.items import _resolve_table  # helper para table_*

# =========================================================================== #
#   Feature — objeto individual
# =========================================================================== #

@mcp.tool()
def feature_get(
    layer_ref: str,
    object_id: int,
    out_sr: int = 4326,
    layer_index: int = 0,
) -> dict:
    """Obtiene un Feature individual por su ObjectID.

    layer_ref: URL del servicio o item ID.
    object_id: valor del campo ObjectID del feature a recuperar.
    out_sr: WKID del sistema de referencia de salida (default 4326 WGS84).
    layer_index: índice de capa si se usa item ID.

    Retorna geometry y attributes del Feature.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    oid_field = fl.properties.get("objectIdField", "OBJECTID")
    fset = fl.query(
        where=f"{oid_field} = {object_id}",
        out_sr=str(out_sr),
        result_record_count=1,
    )
    if not fset.features:
        raise ValueError(f"Feature con {oid_field}={object_id} no encontrado.")
    f = fset.features[0]
    return {
        "object_id": object_id,
        "attributes": f.attributes,
        "geometry": f.geometry,
    }


@mcp.tool()
def feature_get_value(
    layer_ref: str,
    object_id: int,
    field_name: str,
    layer_index: int = 0,
) -> Any:
    """Obtiene el valor de un campo específico de un Feature por ObjectID.

    layer_ref: URL del servicio o item ID.
    object_id: ObjectID del feature.
    field_name: nombre exacto del campo a leer.
    layer_index: índice de capa si se usa item ID.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    oid_field = fl.properties.get("objectIdField", "OBJECTID")
    fset = fl.query(
        where=f"{oid_field} = {object_id}",
        out_fields=f"{oid_field},{field_name}",
        return_geometry=False,
        result_record_count=1,
    )
    if not fset.features:
        raise ValueError(f"Feature con {oid_field}={object_id} no encontrado.")
    return fset.features[0].attributes.get(field_name)


@mcp.tool()
def feature_update(
    layer_ref: str,
    object_id: int,
    attributes_json: str,
    layer_index: int = 0,
    dry_run: bool = True,
) -> dict:
    """Actualiza los atributos de un Feature individual. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del servicio o item ID.
    object_id: ObjectID del feature a modificar.
    attributes_json: JSON dict con los campos y nuevos valores.
                     Ejemplo: '{"STATUS": "Activo", "NOTES": "Revisado"}'
                     No incluir el ObjectID — se agrega automáticamente.
    layer_index: índice de capa si se usa item ID.
    dry_run: True por defecto — simula sin escribir.
    """
    _require_write()
    fl = _resolve_layer(layer_ref, layer_index)
    oid_field = fl.properties.get("objectIdField", "OBJECTID")
    new_attrs = json.loads(attributes_json)
    new_attrs[oid_field] = object_id

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "object_id": object_id,
            "would_update": new_attrs,
        }

    result = fl.edit_features(updates=[{"attributes": new_attrs}])
    return _safe_result(result)


# =========================================================================== #
#   FeatureLayer — operaciones avanzadas (fl_*)
# =========================================================================== #

@mcp.tool()
def fl_fields(layer_ref: str, layer_index: int = 0) -> list:
    """Lista todos los campos de un FeatureLayer con nombre, tipo y alias.

    layer_ref: URL del servicio o item ID.
    layer_index: índice de capa.

    Retorna: nombre, alias, type y longitud de cada campo.
    Imprescindible antes de escribir consultas SQL o editar features.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    return [
        {
            "name": f["name"],
            "alias": f.get("alias", ""),
            "type": f.get("type", ""),
            "length": f.get("length"),
            "domain": f.get("domain"),
            "nullable": f.get("nullable", True),
        }
        for f in fl.properties.get("fields", [])
    ]


@mcp.tool()
def fl_query_advanced(
    layer_ref: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    return_geometry: bool = True,
    return_count_only: bool = False,
    order_by: str = "",
    max_features: int = 1000,
    layer_index: int = 0,
) -> dict:
    """Consulta avanzada de un FeatureLayer con control completo de parámetros.

    layer_ref: URL del servicio o item ID.
    where: cláusula SQL. Ejemplo: "POPULATION > 500000 AND STATUS = 'Active'"
    out_fields: campos separados por coma o '*'.
    out_sr: WKID de salida (4326 = WGS84, 102100 = Web Mercator).
    return_geometry: incluir geometría en la respuesta.
    return_count_only: si True, solo retorna el conteo (muy rápido).
    order_by: campo y dirección. Ejemplo: "POPULATION DESC".
    max_features: máximo de features a retornar.
    layer_index: índice de capa si se usa item ID.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    kwargs: dict[str, Any] = dict(
        where=where,
        out_fields=out_fields,
        return_geometry=return_geometry,
        result_record_count=max_features,
        out_sr=str(out_sr),
        return_count_only=return_count_only,
    )
    if order_by:
        kwargs["order_by_fields"] = order_by

    fset = fl.query(**kwargs)

    if return_count_only:
        return {"count": fset}

    features = [
        {
            "attributes": f.attributes,
            **({"geometry": f.geometry} if return_geometry and f.geometry else {}),
        }
        for f in fset.features
    ]
    return {
        "count": len(features),
        "spatial_reference": fset.spatial_reference,
        "fields": [fld["name"] for fld in (fset.fields or [])],
        "features": features,
    }


@mcp.tool()
def fl_edit(
    layer_ref: str,
    adds_json: str = "[]",
    updates_json: str = "[]",
    deletes: str = "",
    layer_index: int = 0,
    dry_run: bool = True,
) -> dict:
    """Agrega, actualiza o elimina features en un FeatureLayer. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del servicio o item ID.
    adds_json: JSON array de features a agregar.
               Ejemplo: '[{"attributes":{"NAME":"Test"},"geometry":{"x":-77,"y":4}}]'
    updates_json: JSON array de features a actualizar (deben incluir ObjectID).
               Ejemplo: '[{"attributes":{"OBJECTID":5,"STATUS":"Inactivo"}}]'
    deletes: string con ObjectIDs separados por coma a eliminar.
             Ejemplo: '1,2,5'
    dry_run: True por defecto — simula sin escribir.

    Equivalente a FeatureLayer.edit_features(adds, updates, deletes).
    """
    _require_write()
    fl = _resolve_layer(layer_ref, layer_index)
    adds = json.loads(adds_json)
    updates = json.loads(updates_json)

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "would_add": len(adds),
            "would_update": len(updates),
            "would_delete": deletes or "(ninguno)",
        }

    kwargs: dict[str, Any] = {}
    if adds:
        kwargs["adds"] = adds
    if updates:
        kwargs["updates"] = updates
    if deletes:
        kwargs["deletes"] = deletes

    result = fl.edit_features(**kwargs)
    return _safe_result(result)


@mcp.tool()
def fl_delete_by_query(
    layer_ref: str,
    where: str,
    layer_index: int = 0,
    dry_run: bool = True,
) -> dict:
    """Elimina features que cumplan una condición SQL. OPERACIÓN DESTRUCTIVA.

    layer_ref: URL del servicio o item ID.
    where: cláusula WHERE. Ejemplo: "STATUS = 'Obsoleto'" o "CREATED_DATE < '2020-01-01'"
           CUIDADO: '1=1' elimina TODOS los features.
    layer_index: índice de capa.
    dry_run: True por defecto — muestra cuántos features se eliminarían.

    Usa FeatureLayer.delete_features(where=...) en modo real.
    """
    _require_write()
    fl = _resolve_layer(layer_ref, layer_index)
    count = fl.query(where=where, return_count_only=True)

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "where": where,
            "features_that_would_be_deleted": count,
        }

    result = fl.delete_features(where=where)
    return _safe_result(result)


@mcp.tool()
def fl_calculate(
    layer_ref: str,
    where: str,
    calc_expression_json: str,
    layer_index: int = 0,
    dry_run: bool = True,
) -> dict:
    """Calcula y actualiza valores de campo en un FeatureLayer. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del servicio o item ID.
    where: cláusula SQL que filtra qué features se actualizan.
    calc_expression_json: JSON array de cálculos a aplicar.
        Ejemplo para actualizar un campo: '[{"field":"STATUS","value":"Activo"}]'
        Ejemplo con expresión SQL: '[{"field":"AREA","sqlExpression":"Shape__Area * 0.0001"}]'
    layer_index: índice de capa.
    dry_run: True por defecto — muestra cuántos features se afectarían.

    Equivalente a FeatureLayer.calculate(where=..., calc_expression=...).
    """
    _require_write()
    fl = _resolve_layer(layer_ref, layer_index)
    calc_expr = json.loads(calc_expression_json)
    count = fl.query(where=where, return_count_only=True)

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "where": where,
            "features_affected": count,
            "would_calculate": calc_expr,
        }

    result = fl.calculate(where=where, calc_expression=calc_expr)
    return _safe_result(result)


@mcp.tool()
def fl_capabilities(layer_ref: str, layer_index: int = 0) -> dict:
    """Inspecciona las capacidades y propiedades clave de un FeatureLayer.

    layer_ref: URL del servicio o item ID.
    layer_index: índice de capa.

    Retorna: nombre, tipo de geometría, capabilities habilitadas (Query/Create/Update/
    Delete/Editing/Sync/Extract), extent, maxRecordCount y sistema de referencia.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    p = fl.properties
    return {
        "url": fl.url,
        "name": p.get("name"),
        "type": p.get("type"),
        "geometry_type": p.get("geometryType"),
        "capabilities": p.get("capabilities"),
        "max_record_count": p.get("maxRecordCount"),
        "object_id_field": p.get("objectIdField"),
        "display_field": p.get("displayField"),
        "spatial_reference": p.get("extent", {}).get("spatialReference"),
        "extent": p.get("extent"),
        "supports_statistics": p.get("supportsStatistics", False),
        "supports_advanced_queries": p.get("supportsAdvancedQueries", False),
        "supports_calculate": p.get("supportsCalculate", False),
        "has_attachments": p.get("hasAttachments", False),
    }


# =========================================================================== #
#   Table — tabla no espacial (table_*)
# =========================================================================== #

@mcp.tool()
def table_query(
    item_id: str,
    table_index: int = 0,
    where: str = "1=1",
    out_fields: str = "*",
    return_count_only: bool = False,
    max_records: int = 1000,
) -> dict:
    """Consulta una tabla no espacial de un Feature Service.

    item_id: ID del item en el portal.
    table_index: índice de la tabla dentro del servicio (default 0).
    where: cláusula SQL. Ejemplo: "STATUS = 'Pendiente'"
    out_fields: campos a retornar separados por coma, o '*'.
    return_count_only: True = solo cuenta registros (muy rápido).
    max_records: máximo de registros a retornar.

    Equivalente a Table.query(). No retorna geometría (es una tabla).
    """
    tbl = _resolve_table(item_id, table_index)
    fset = tbl.query(
        where=where,
        out_fields=out_fields,
        return_geometry=False,
        result_record_count=max_records,
        return_count_only=return_count_only,
    )
    if return_count_only:
        return {"count": fset}

    records = [f.attributes for f in fset.features]
    return {
        "count": len(records),
        "fields": [fld["name"] for fld in (fset.fields or [])],
        "records": records,
    }


@mcp.tool()
def table_edit(
    item_id: str,
    table_index: int = 0,
    adds_json: str = "[]",
    updates_json: str = "[]",
    deletes: str = "",
    dry_run: bool = True,
) -> dict:
    """Agrega, actualiza o elimina registros en una tabla no espacial. ESCRITURA.

    item_id: ID del item en el portal.
    table_index: índice de la tabla (default 0).
    adds_json: JSON array de registros a agregar (solo 'attributes', sin 'geometry').
    updates_json: JSON array de registros a actualizar (incluir ObjectID).
    deletes: ObjectIDs separados por coma a eliminar.
    dry_run: True por defecto — simula sin escribir.
    """
    _require_write()
    tbl = _resolve_table(item_id, table_index)
    adds = json.loads(adds_json)
    updates = json.loads(updates_json)

    if dry_run:
        return {
            "dry_run": True,
            "table_url": tbl.url,
            "would_add": len(adds),
            "would_update": len(updates),
            "would_delete": deletes or "(ninguno)",
        }

    kwargs: dict[str, Any] = {}
    if adds:
        kwargs["adds"] = [{"attributes": r} if "attributes" not in r else r for r in adds]
    if updates:
        kwargs["updates"] = [{"attributes": r} if "attributes" not in r else r for r in updates]
    if deletes:
        kwargs["deletes"] = deletes

    result = tbl.edit_features(**kwargs)
    return _safe_result(result)


@mcp.tool()
def table_fields(item_id: str, table_index: int = 0) -> list:
    """Lista los campos de una tabla no espacial.

    item_id: ID del item en el portal.
    table_index: índice de la tabla (default 0).

    Retorna nombre, alias, tipo y propiedades de cada campo.
    """
    tbl = _resolve_table(item_id, table_index)
    return [
        {
            "name": f["name"],
            "alias": f.get("alias", ""),
            "type": f.get("type", ""),
            "length": f.get("length"),
            "nullable": f.get("nullable", True),
        }
        for f in tbl.properties.get("fields", [])
    ]


# =========================================================================== #
#   FeatureLayerCollection — servicio completo (flc_*)
# =========================================================================== #

@mcp.tool()
def flc_describe(item_id: str) -> dict:
    """Describe un Feature Service completo: capas, tablas y propiedades del servicio.

    item_id: ID del item Feature Layer Collection en el portal.

    Retorna: versión, capabilities, sincronización, extent, lista de capas y tablas
    con su nombre, tipo de geometría y maxRecordCount.
    Equivalente a inspeccionar FeatureLayerCollection.properties + .layers + .tables.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    flc = FeatureLayerCollection.fromitem(item)
    p = flc.properties

    layers_info = [
        {
            "index": i,
            "name": lyr.properties.get("name"),
            "type": "layer",
            "geometry_type": lyr.properties.get("geometryType"),
            "max_record_count": lyr.properties.get("maxRecordCount"),
            "capabilities": lyr.properties.get("capabilities"),
            "url": lyr.url,
        }
        for i, lyr in enumerate(flc.layers)
    ]
    tables_info = [
        {
            "index": i,
            "name": tbl.properties.get("name"),
            "type": "table",
            "url": tbl.url,
        }
        for i, tbl in enumerate(flc.tables)
    ]

    return {
        "item_id": item_id,
        "service_url": item.url,
        "current_version": p.get("currentVersion"),
        "capabilities": p.get("capabilities"),
        "description": p.get("serviceDescription") or p.get("description"),
        "copyright": p.get("copyrightText"),
        "max_record_count": p.get("maxRecordCount"),
        "sync_enabled": p.get("syncEnabled", False),
        "supports_append": p.get("supportsAppend", False),
        "layers": layers_info,
        "tables": tables_info,
    }


@mcp.tool()
def flc_update_definition(
    item_id: str,
    definition_json: str,
    dry_run: bool = True,
) -> dict:
    """Actualiza la definición del Feature Service. OPERACIÓN DE ESCRITURA.

    item_id: ID del item Feature Layer Collection.
    definition_json: JSON dict con las propiedades a modificar.
        Ejemplos comunes:
        '{"description": "Capa de infraestructura 2024"}'
        '{"copyrightText": "© Organización 2024"}'
        '{"capabilities": "Query", "syncEnabled": false}'
    dry_run: True por defecto — simula sin escribir.

    Requiere ser propietario del item o administrador.
    Usa FeatureLayerCollection.manager.update_definition().
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    flc = FeatureLayerCollection.fromitem(item)
    update_dict = json.loads(definition_json)

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "service_url": item.url,
            "current_capabilities": flc.properties.get("capabilities"),
            "would_update": update_dict,
        }

    result = flc.manager.update_definition(update_dict)
    return _safe_result(result)


@mcp.tool()
def flc_truncate(
    item_id: str,
    layer_index: int = 0,
    attachment_only: bool = False,
    dry_run: bool = True,
) -> dict:
    """Vacía todos los features de una capa (truncate). OPERACIÓN DESTRUCTIVA.

    item_id: ID del item Feature Layer Collection.
    layer_index: índice de la capa a vaciar (default 0).
    attachment_only: True = solo elimina attachments, mantiene features.
    dry_run: True por defecto — muestra cuántos features se eliminarían.

    IRREVERSIBLE sin backup previo. Verificar item_dependent_to() antes.
    Usa FeatureLayerCollection.manager.truncate().
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    flc = FeatureLayerCollection.fromitem(item)
    if layer_index >= len(flc.layers):
        raise ValueError(f"layer_index={layer_index} fuera de rango.")

    layer = flc.layers[layer_index]
    count = layer.query(where="1=1", return_count_only=True)

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "layer_name": layer.properties.get("name"),
            "layer_url": layer.url,
            "features_that_would_be_deleted": count,
            "attachment_only": attachment_only,
            "warning": "IRREVERSIBLE — asegurarse de tener backup antes.",
        }

    result = flc.manager.truncate(
        layer=layer_index,
        attachment_only=attachment_only,
    )
    return _safe_result(result)


# =========================================================================== #
#   FeatureSet — operaciones sobre conjuntos de resultados (fset_*)
# =========================================================================== #

@mcp.tool()
def fset_from_query(
    layer_ref: str,
    where: str = "1=1",
    out_fields: str = "*",
    out_sr: int = 4326,
    max_features: int = 500,
    layer_index: int = 0,
) -> dict:
    """Ejecuta una query y retorna el FeatureSet completo como JSON estructurado.

    layer_ref: URL del servicio o item ID.
    where: cláusula SQL.
    out_fields: campos a retornar.
    out_sr: WKID de salida (4326 = WGS84).
    max_features: límite de features.
    layer_index: índice de capa si se usa item ID.

    Retorna el contenido del FeatureSet: features (atributos + geometría),
    campos, referencia espacial y tipo de geometría.
    Ideal para análisis o exportación por parte del LLM.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    fset = fl.query(
        where=where,
        out_fields=out_fields,
        out_sr=str(out_sr),
        result_record_count=max_features,
    )
    return {
        "feature_count": len(fset.features),
        "geometry_type": fset.geometry_type,
        "spatial_reference": fset.spatial_reference,
        "fields": [
            {"name": f["name"], "type": f.get("type", ""), "alias": f.get("alias", "")}
            for f in (fset.fields or [])
        ],
        "features": [
            {"attributes": f.attributes, "geometry": f.geometry}
            for f in fset.features
        ],
    }


@mcp.tool()
def fset_statistics(
    layer_ref: str,
    out_statistics_json: str,
    where: str = "1=1",
    group_by_fields: str = "",
    layer_index: int = 0,
) -> list:
    """Calcula estadísticas (sum, avg, count, min, max) en el servidor. SOLO LECTURA.

    layer_ref: URL del servicio o item ID.
    out_statistics_json: JSON array con definición de estadísticas.
        Ejemplo:
        '[{"statisticType":"count","onStatisticField":"OBJECTID","outStatisticFieldName":"total"},
          {"statisticType":"sum","onStatisticField":"POPULATION","outStatisticFieldName":"pop_total"},
          {"statisticType":"avg","onStatisticField":"POPULATION","outStatisticFieldName":"pop_avg"}]'
    where: filtro SQL aplicado antes del cálculo.
    group_by_fields: campo(s) para agrupar (como GROUP BY en SQL).
                     Ejemplo: "STATE_NAME" o "STATE_NAME,COUNTY"
    layer_index: índice de capa.

    El cálculo ocurre en el servidor — no se transfieren todos los datos.
    Requiere que el layer tenga supportsStatistics=true.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    out_stats = json.loads(out_statistics_json)
    kwargs: dict[str, Any] = dict(
        where=where,
        out_statistics=out_stats,
        return_geometry=False,
    )
    if group_by_fields:
        kwargs["group_by_fields_for_statistics"] = group_by_fields

    fset = fl.query(**kwargs)
    return [f.attributes for f in fset.features]


@mcp.tool()
def fset_to_geojson(
    layer_ref: str,
    where: str = "1=1",
    out_fields: str = "*",
    max_features: int = 1000,
    layer_index: int = 0,
) -> dict:
    """Retorna los features de una capa como GeoJSON FeatureCollection.

    layer_ref: URL del servicio o item ID.
    where: cláusula SQL.
    out_fields: campos a retornar.
    max_features: límite de features.
    layer_index: índice de capa.

    El GeoJSON está en WGS84 (EPSG:4326) — estándar interoperable.
    Útil para visualización, integración con otras herramientas o exportación.
    """
    fl = _resolve_layer(layer_ref, layer_index)
    fset = fl.query(
        where=where,
        out_fields=out_fields,
        out_sr="4326",
        result_record_count=max_features,
    )

    geojson_features = []
    for f in fset.features:
        geom = f.geometry
        attrs = f.attributes

        # Convertir geometría a formato GeoJSON
        geojson_geom: dict | None = None
        if geom:
            if "x" in geom and "y" in geom:
                geojson_geom = {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
            elif "rings" in geom:
                geojson_geom = {"type": "Polygon", "coordinates": geom["rings"]}
            elif "paths" in geom:
                geojson_geom = {
                    "type": "MultiLineString" if len(geom["paths"]) > 1 else "LineString",
                    "coordinates": geom["paths"] if len(geom["paths"]) > 1 else geom["paths"][0],
                }

        geojson_features.append({
            "type": "Feature",
            "geometry": geojson_geom,
            "properties": attrs,
        })

    return {
        "type": "FeatureCollection",
        "features": geojson_features,
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
    }


# =========================================================================== #
#   FeatureCollection — colección en memoria / item tipo Feature Collection (fc_*)
# =========================================================================== #

@mcp.tool()
def fc_describe(item_id: str) -> dict:
    """Describe un item de tipo Feature Collection del portal.

    item_id: ID del item tipo Feature Collection.

    Retorna: número de capas, nombre y tipo de geometría de cada capa.
    A diferencia de un Feature Service, una Feature Collection almacena los
    datos como JSON dentro del item (no hay servicio REST detrás).
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    if item.type != "Feature Collection":
        raise ValueError(f"El item '{item.title}' no es de tipo Feature Collection (es {item.type}).")

    fc_layers = item.layers  # lista de FeatureCollection objects
    layers_info = []
    for i, fc in enumerate(fc_layers):
        layer_def = fc.properties.get("layerDefinition", {}) if hasattr(fc, "properties") else {}
        layers_info.append({
            "index": i,
            "name": layer_def.get("name", f"Layer {i}"),
            "geometry_type": layer_def.get("geometryType"),
            "field_count": len(layer_def.get("fields", [])),
        })

    return {
        "item_id": item_id,
        "title": item.title,
        "description": item.description,
        "layer_count": len(fc_layers),
        "layers": layers_info,
        "size_bytes": item.size,
    }


@mcp.tool()
def fc_query(
    item_id: str,
    layer_index: int = 0,
    where: str = "1=1",
    out_fields: str = "*",
) -> dict:
    """Consulta los features de una capa de un Feature Collection item.

    item_id: ID del item tipo Feature Collection.
    layer_index: índice de la capa dentro del Feature Collection.
    where: cláusula SQL de filtro (no todos los FC soportan filtros complejos).
    out_fields: '*' o campos separados por coma.

    Los datos están almacenados en el portal como JSON, no en un servicio.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    fc_layers = item.layers
    if not fc_layers or layer_index >= len(fc_layers):
        raise ValueError(f"layer_index={layer_index} fuera de rango (tiene {len(fc_layers or [])} capas).")

    fc = fc_layers[layer_index]
    fset = fc.query(where=where)

    features = [
        {"attributes": f.attributes, "geometry": f.geometry}
        for f in fset.features
    ]
    return {
        "count": len(features),
        "fields": [fld["name"] for fld in (fset.fields or [])],
        "features": features,
    }


@mcp.tool()
def fc_to_feature_layer(
    item_id: str,
    title: str,
    folder: str = "",
    layer_index: int = 0,
    dry_run: bool = True,
) -> dict:
    """Publica un Feature Collection como Feature Layer hosted. OPERACIÓN DE ESCRITURA.

    item_id: ID del item Feature Collection.
    title: título del nuevo Feature Layer hosted.
    folder: carpeta destino (vacío = raíz).
    layer_index: índice de la capa a publicar.
    dry_run: True por defecto — simula sin publicar.

    Útil para promover datos estáticos de un FC a un servicio editable y
    queryable con capacidades avanzadas (sync, edición, filtros SQL completos).
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    if item.type != "Feature Collection":
        raise ValueError(f"El item no es de tipo Feature Collection (es {item.type}).")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "source_title": item.title,
            "would_publish_as": title,
            "target_folder": folder or "root",
        }

    published = item.publish(
        publish_parameters={"name": title, "layerIndex": layer_index},
    )
    return {
        "success": True,
        "source_item_id": item_id,
        "published_item_id": published.id,
        "published_title": published.title,
        "published_url": published.url,
    }


