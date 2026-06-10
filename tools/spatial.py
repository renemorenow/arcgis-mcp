from __future__ import annotations
import json
from typing import Any

from arcgis.features import FeatureLayerCollection

from _server import mcp
from _auth import (
    get_gis, _require_write, _resolve_layer, _safe_result,
)

# =========================================================================== #
#   🔗  FEATURE LAYER EXTENDED — prefijo fl_  (extensión de sección existente)
# =========================================================================== #

@mcp.tool()
def fl_add_field(
    layer_ref: str,
    field_name: str,
    field_type: str,
    alias: str = "",
    nullable: bool = True,
    default_value: str = "",
    dry_run: bool = True,
) -> dict:
    """Agrega un nuevo campo al esquema de un Feature Layer. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del FeatureServer/layer o item ID.
    field_name: nombre del campo (sin espacios, max 30 chars para geodatabases).
    field_type: tipo del campo. Valores:
        'esriFieldTypeString', 'esriFieldTypeInteger', 'esriFieldTypeSmallInteger',
        'esriFieldTypeDouble', 'esriFieldTypeSingle', 'esriFieldTypeDate',
        'esriFieldTypeGlobalID', 'esriFieldTypeGUID'.
    alias: alias/etiqueta del campo para mostrar. Vacío = usa field_name.
    nullable: True = permite nulos (default).
    default_value: valor por defecto (como string). Vacío = sin valor por defecto.
    dry_run: True por defecto.

    Equivale a FeatureLayerCollection.manager.add_to_definition({"fields": [...]}).
    """
    _require_write()
    gis = get_gis()
    fl = _resolve_layer(layer_ref)
    flc = FeatureLayerCollection(fl.url.rsplit("/", 1)[0], gis=gis)

    field_def: dict[str, Any] = {
        "name": field_name,
        "type": field_type,
        "alias": alias or field_name,
        "nullable": nullable,
        "editable": True,
        "domain": None,
    }
    if default_value:
        field_def["defaultValue"] = default_value

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "would_add_field": field_def,
        }

    result = flc.manager.add_to_definition({"fields": [field_def]})
    return {"success": result.get("success", False), "field": field_name, "layer_url": fl.url}


@mcp.tool()
def fl_delete_fields(
    layer_ref: str,
    field_names: str,
    dry_run: bool = True,
) -> dict:
    """Elimina campos del esquema de un Feature Layer. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del FeatureServer/layer o item ID.
    field_names: JSON array de nombres de campos a eliminar.
        Ej: '["campo1", "campo2"]'
    dry_run: True por defecto.

    ⚠️ No se pueden eliminar campos del sistema: OBJECTID, SHAPE, GlobalID, etc.
    Equivale a FeatureLayerCollection.manager.delete_from_definition({"fields": [...]}).
    """
    _require_write()
    gis = get_gis()
    fl = _resolve_layer(layer_ref)
    flc = FeatureLayerCollection(fl.url.rsplit("/", 1)[0], gis=gis)
    names = json.loads(field_names)
    fields_to_delete = [{"name": n} for n in names]

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "would_delete_fields": names,
        }

    result = flc.manager.delete_from_definition({"fields": fields_to_delete})
    return {"success": result.get("success", False), "deleted_fields": names}


@mcp.tool()
def fl_attachments_list(
    layer_ref: str,
    object_id: int,
) -> list:
    """Lista los adjuntos (attachments) de un feature específico.

    layer_ref: URL del FeatureServer/layer o item ID.
    object_id: OBJECTID del feature cuyos adjuntos se quieren ver.

    Retorna: lista de adjuntos con id, name, contentType, size y url de descarga.
    El layer debe tener habilitado el soporte de adjuntos (hasAttachments=true).
    Equivale a FeatureLayer.attachments.get_list(object_id).
    """
    gis = get_gis()
    fl = _resolve_layer(layer_ref)
    if not getattr(fl.properties, "hasAttachments", False):
        return [{"info": f"Layer {fl.url} no tiene attachments habilitados"}]

    attachments = fl.attachments.get_list(oid=object_id)
    result = []
    for att in (attachments or []):
        result.append({
            "id": att.get("id"),
            "name": att.get("name"),
            "contentType": att.get("contentType"),
            "size": att.get("size"),
            "keywords": att.get("keywords", ""),
            "download_url": f"{fl.url}/{object_id}/attachments/{att.get('id')}",
        })
    return result


@mcp.tool()
def fl_attachment_add(
    layer_ref: str,
    object_id: int,
    file_path: str,
    dry_run: bool = True,
) -> dict:
    """Agrega un adjunto a un feature. OPERACIÓN DE ESCRITURA.

    layer_ref: URL del FeatureServer/layer o item ID.
    object_id: OBJECTID del feature al que agregar el adjunto.
    file_path: ruta local completa del archivo a subir.
        Ej: 'C:/fotos/inspeccion_001.jpg'
    dry_run: True por defecto.

    El layer debe tener hasAttachments=true.
    Equivale a FeatureLayer.attachments.add(oid, file_path).
    """
    _require_write()
    gis = get_gis()
    fl = _resolve_layer(layer_ref)

    if not os.path.exists(file_path):
        raise ValueError(f"Archivo no encontrado: {file_path}")
    if not getattr(fl.properties, "hasAttachments", False):
        raise RuntimeError(f"Layer {fl.url} no tiene attachments habilitados.")

    if dry_run:
        return {
            "dry_run": True,
            "layer_url": fl.url,
            "object_id": object_id,
            "would_upload": file_path,
            "file_size_kb": round(os.path.getsize(file_path) / 1024, 2),
        }

    result = fl.attachments.add(oid=object_id, file_path=file_path)
    return {
        "success": result.get("addAttachmentResult", {}).get("success", False),
        "attachment_id": result.get("addAttachmentResult", {}).get("objectId"),
        "object_id": object_id,
        "file": file_path,
    }


@mcp.tool()
def fl_related_records(
    layer_ref: str,
    object_ids: str,
    relationship_id: int,
    out_fields: str = "*",
    max_records: int = 100,
) -> dict:
    """Consulta registros relacionados de features a través de una relación definida.

    layer_ref: URL del FeatureServer/layer o item ID.
    object_ids: JSON array de OBJECTIDs. Ej: '[1, 2, 3]'
    relationship_id: ID de la relación (obtener de fl_capabilities o flc_describe).
    out_fields: campos a retornar, separados por coma. '*' = todos.
    max_records: máximo de registros relacionados por feature. Default 100.

    Retorna: registros relacionados agrupados por OBJECTID origen.
    Equivale a FeatureLayer.query_related_records(object_ids, ...).
    """
    gis = get_gis()
    fl = _resolve_layer(layer_ref)
    oids = json.loads(object_ids)
    oids_str = ",".join(str(o) for o in oids)

    result = fl.query_related_records(
        object_ids=oids_str,
        relationship_id=relationship_id,
        out_fields=out_fields,
        return_geometry=False,
        max_allowable_offset=None,
    )
    return _safe_result(result)


@mcp.tool()
def fl_append(
    layer_ref: str,
    source_ref: str,
    upsert: bool = False,
    upsert_matching_field: str = "",
    dry_run: bool = True,
) -> dict:
    """Agrega (append) o actualiza (upsert) features desde otro item o servicio. ESCRITURA.

    layer_ref: URL del FeatureServer/layer destino o item ID.
    source_ref: item ID del portal con los datos fuente (Feature Layer, CSV, Shapefile, etc.)
    upsert: False = solo agregar nuevos registros. True = actualizar si existe + insertar nuevos.
    upsert_matching_field: campo para emparejar en upsert. Requerido si upsert=True.
        Ej: 'CODIGO_PREDIO' — debe existir en ambas capas.
    dry_run: True por defecto.

    ⚠️ No hace rollback automático si falla a mitad del proceso.
    Equivale a FeatureLayer.append(item_id=..., upload_format='featureCollection', upsert=...).
    """
    _require_write()
    gis = get_gis()
    fl = _resolve_layer(layer_ref)

    source_item = gis.content.get(source_ref)
    if source_item is None:
        raise ValueError(f"Item fuente no encontrado: {source_ref}")

    if upsert and not upsert_matching_field:
        raise ValueError("'upsert_matching_field' es requerido cuando upsert=True")

    if dry_run:
        return {
            "dry_run": True,
            "target_layer": fl.url,
            "source_item": {"id": source_ref, "title": source_item.title, "type": source_item.type},
            "upsert": upsert,
            "upsert_matching_field": upsert_matching_field or None,
        }

    kwargs: dict[str, Any] = {
        "item_id": source_ref,
        "upload_format": "featureCollection",
        "upsert": upsert,
    }
    if upsert and upsert_matching_field:
        kwargs["upsert_matching_field"] = upsert_matching_field

    result = fl.append(**kwargs)
    return {"success": result, "target_layer": fl.url, "source_item": source_ref}


# =========================================================================== #
#   👁️  LAYER VIEWS — vistas de Feature Layers hosted  (prefijo fl_view_)
# =========================================================================== #

@mcp.tool()
def fl_view_list(item_id: str) -> list:
    """Lista las Layer Views publicadas de un Feature Layer hosted.

    item_id: ID del item del Feature Layer padre (hosted).

    Retorna: lista de Layer Views con su item_id, title, url, tipo de filtro aplicado.
    Las Layer Views son subsets del feature layer padre que exponen
    un subconjunto de features y/o campos con sus propias configuraciones de acceso.
    Equivale a item.related_items("Service2Data", "reverse") filtrando views.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    related = item.related_items("Service2Data", "reverse")
    views = []
    for r in (related or []):
        if "View Service" in (r.typeKeywords or []):
            views.append({
                "item_id": r.id,
                "title": r.title,
                "type": r.type,
                "url": r.url,
                "owner": r.owner,
                "access": r.access,
                "created": str(r.created) if hasattr(r, "created") else None,
            })
    return views


@mcp.tool()
def fl_create_view(
    item_id: str,
    title: str,
    definition_expression: str = "",
    visible_fields: str = "[]",
    dry_run: bool = True,
) -> dict:
    """Crea una Layer View de un Feature Layer hosted. OPERACIÓN DE ESCRITURA.

    item_id: ID del Feature Layer hosted padre.
    title: título de la nueva Layer View.
    definition_expression: expresión SQL para filtrar features. Vacío = todos.
        Ej: "MUNICIPIO = 'Bogotá' AND ESTADO = 'Activo'"
    visible_fields: JSON array de nombres de campos a exponer. '[]' = todos.
        Ej: '["OBJECTID", "NOMBRE", "ESTADO", "Shape"]'
    dry_run: True por defecto.

    La Layer View hereda los datos del padre pero con sus propias definiciones de acceso.
    Equivale a FeatureLayerCollection.fromitem(item).manager.create_view(title, ...).
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    fields_list = json.loads(visible_fields) if visible_fields and visible_fields != "[]" else []

    if dry_run:
        return {
            "dry_run": True,
            "parent_item": {"id": item_id, "title": item.title},
            "view_title": title,
            "definition_expression": definition_expression or "(sin filtro — todos los features)",
            "visible_fields": fields_list or "(todos los campos)",
        }

    flc = FeatureLayerCollection.fromitem(item)
    view_item = flc.manager.create_view(title)

    if definition_expression or fields_list:
        view_fl = view_item.layers[0]
        view_flc = FeatureLayerCollection.fromitem(view_item)
        update_dict: dict[str, Any] = {}
        if definition_expression:
            update_dict["viewDefinitionQuery"] = definition_expression
        if fields_list:
            update_dict["viewLayerDefinition"] = {"fields": [{"name": f} for f in fields_list]}
        if update_dict:
            view_flc.manager.update_definition(update_dict)

    return {
        "success": True,
        "view_item_id": view_item.id,
        "view_title": view_item.title,
        "parent_item_id": item_id,
    }


