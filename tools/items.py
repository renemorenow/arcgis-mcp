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
#   GESTIÓN AVANZADA DE ITEMS (Content Management)
# =========================================================================== #
@mcp.tool()
def item_get(item_id: str) -> dict:
    """Obtiene detalles completos de un item por su ID.
    
    item_id: ID único del item en el portal.
    
    Retorna información completa incluyendo: título, tipo, owner, descripción,
    tags, snippet, thumbnail URL, URL del item, fecha de creación/modificación,
    tamaño, número de vistas, ratings, y propiedades específicas del tipo.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    return {
        "id": item.id,
        "title": item.title,
        "type": item.type,
        "owner": item.owner,
        "description": item.description or "",
        "snippet": item.snippet or "",
        "tags": item.tags or [],
        "url": item.url,
        "thumbnail": item.thumbnail,
        "created": str(item.created) if hasattr(item, 'created') else None,
        "modified": str(item.modified) if hasattr(item, 'modified') else None,
        "size": item.size if hasattr(item, 'size') else None,
        "numViews": item.numViews if hasattr(item, 'numViews') else 0,
        "avgRating": item.avgRating if hasattr(item, 'avgRating') else 0,
        "numRatings": item.numRatings if hasattr(item, 'numRatings') else 0,
        "access": item.access if hasattr(item, 'access') else "private",
        "shared_with": item.shared_with if hasattr(item, 'shared_with') else {},
        "protected": getattr(item, 'protected', False),
        "typeKeywords": item.typeKeywords if hasattr(item, 'typeKeywords') else [],
    }


@mcp.tool()
def item_update(
    item_id: str,
    title: str = "",
    description: str = "",
    tags: str = "[]",
    snippet: str = "",
    dry_run: bool = True,
) -> dict:
    """Actualiza la metadata de un item. OPERACIÓN DE ESCRITURA.
    
    item_id: ID del item a actualizar.
    title: nuevo título (dejar vacío para no cambiar).
    description: nueva descripción (dejar vacío para no cambiar).
    tags: JSON array de tags, ej. '["gis", "mapping"]' (dejar '[]' para no cambiar).
    snippet: nuevo resumen corto (dejar vacío para no cambiar).
    dry_run: True por defecto — simula sin escribir.
    
    Solo actualiza los campos que se proporcionen (no vacíos).
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    # Construir diccionario de propiedades a actualizar
    updates = {}
    if title:
        updates["title"] = title
    if description:
        updates["description"] = description
    if snippet:
        updates["snippet"] = snippet
    if tags and tags != "[]":
        tag_list = json.loads(tags)
        if tag_list:
            updates["tags"] = ",".join(tag_list)
    
    if not updates:
        return {"error": "No se proporcionaron cambios", "item_id": item_id}
    
    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "current_title": item.title,
            "would_update": updates,
        }
    
    success = item.update(item_properties=updates)
    return {
        "success": success,
        "item_id": item_id,
        "updated": updates,
    }


@mcp.tool()
def item_protect(item_id: str, dry_run: bool = True) -> dict:
    """Protege un item contra eliminación accidental. OPERACIÓN DE ESCRITURA.
    
    item_id: ID del item a proteger.
    dry_run: True por defecto — simula sin escribir.
    
    Los items protegidos no pueden ser eliminados hasta que se remueva la protección.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "currently_protected": getattr(item, 'protected', False),
            "action": "would protect",
        }
    
    success = item.protect(enable=True)
    return {
        "success": success,
        "item_id": item_id,
        "protected": True,
    }


@mcp.tool()
def item_unprotect(item_id: str, dry_run: bool = True) -> dict:
    """Remueve la protección contra eliminación de un item. OPERACIÓN DE ESCRITURA.
    
    item_id: ID del item a desproteger.
    dry_run: True por defecto — simula sin escribir.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "currently_protected": getattr(item, 'protected', False),
            "action": "would unprotect",
        }
    
    success = item.protect(enable=False)
    return {
        "success": success,
        "item_id": item_id,
        "protected": False,
    }


@mcp.tool()
def item_metadata(item_id: str, metadata_format: str = "json") -> dict:
    """Obtiene la metadata completa de un item en formato JSON o XML.
    
    item_id: ID del item.
    metadata_format: 'json' o 'xml'.
    
    Retorna la metadata completa del item tal como está almacenada en el portal,
    incluyendo todos los campos estándar y personalizados.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    if metadata_format.lower() == "xml":
        # Obtener metadata XML si existe
        metadata = item.metadata
        return {
            "item_id": item_id,
            "format": "xml",
            "metadata": metadata if metadata else "No metadata XML available",
        }
    else:
        # Retornar propiedades completas como JSON
        return {
            "item_id": item_id,
            "format": "json",
            "metadata": _safe_result(item),
        }


@mcp.tool()
def item_download(item_id: str, save_path: str = "") -> dict:
    """Descarga los datos de un item al sistema de archivos local.
    
    item_id: ID del item a descargar.
    save_path: ruta donde guardar (opcional). Si vacío, usa el directorio actual.
    
    Funciona con: Feature Services, File Geodatabases, Shapefiles, CSVs, etc.
    Retorna información sobre el archivo descargado.
    
    NOTA: Esta operación descarga archivos localmente donde corre el MCP.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    
    try:
        # Intentar descargar el item
        download_path = item.download(save_path=save_path or None)
        
        # Obtener información del archivo descargado
        if download_path and os.path.exists(download_path):
            file_size = os.path.getsize(download_path)
            return {
                "success": True,
                "item_id": item_id,
                "item_title": item.title,
                "downloaded_to": download_path,
                "file_size_bytes": file_size,
            }
        else:
            return {
                "success": False,
                "item_id": item_id,
                "error": "Download completed but file not found",
            }
    except Exception as e:
        return {
            "success": False,
            "item_id": item_id,
            "error": str(e),
            "note": "Some item types cannot be downloaded directly",
        }



# =========================================================================== #
#   GESTIÓN DE ITEMS — prefijo item_
# =========================================================================== #

@mcp.tool()
def item_delete(item_id: str, dry_run: bool = True) -> dict:
    """Elimina un item del portal. OPERACIÓN DESTRUCTIVA.

    item_id: ID del item a eliminar.
    dry_run: True por defecto — simula sin eliminar.

    CUIDADO: eliminar un Feature Service hosted también borra el servicio y sus
    datos. Acción irreversible.
    Tip: verificar item_dependent_to() antes de eliminar.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    is_protected = getattr(item, "protected", False)

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "type": item.type,
            "owner": item.owner,
            "is_protected": is_protected,
            "warning": "Al eliminar un servicio hosted se borran también sus datos.",
        }

    if is_protected:
        raise PermissionError(
            f"El item '{item.title}' tiene protección activa. "
            "Usar unprotect_item() antes de eliminar."
        )

    success = item.delete()
    return {"success": success, "item_id": item_id, "deleted": True}


@mcp.tool()
def item_move(
    item_id: str,
    folder: str,
    owner: str = "",
    dry_run: bool = True,
) -> dict:
    """Mueve un item a una carpeta del portal. OPERACIÓN DE ESCRITURA.

    item_id: ID del item.
    folder: nombre de la carpeta destino (debe existir). Usar '/' para raíz.
    owner: nombre de usuario propietario (vacío = propietario actual).
    dry_run: True por defecto — simula sin mover.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "current_owner": item.owner,
            "would_move_to_folder": folder,
        }

    target_owner = owner or item.owner
    result = item.move(folder=folder, owner=target_owner)
    success = result.get("success", False) if isinstance(result, dict) else bool(result)
    return {"success": success, "item_id": item_id, "moved_to": folder}


@mcp.tool()
def item_clone(
    item_id: str,
    folder: str = "",
    copy_data: bool = True,
    dry_run: bool = True,
) -> dict:
    """Clona un item dentro del mismo portal. OPERACIÓN DE ESCRITURA.

    item_id: ID del item a clonar.
    folder: carpeta destino (vacío = raíz del usuario actual).
    copy_data: True para copiar datos del servicio hosted.
    dry_run: True por defecto — simula sin clonar.

    Útil para: backup, crear versiones de prueba, migración entre usuarios.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "type": item.type,
            "copy_data": copy_data,
            "target_folder": folder or "root",
        }

    cloned_items = gis.content.clone_items(
        items=[item],
        folder=folder or None,
        copy_data=copy_data,
    )

    if cloned_items:
        cloned = cloned_items[0]
        return {
            "success": True,
            "original_id": item_id,
            "cloned_id": cloned.id,
            "cloned_title": cloned.title,
        }
    return {"success": False, "item_id": item_id, "error": "clone_items retornó vacío"}


@mcp.tool()
def item_publish(
    item_id: str,
    publish_params_json: str = "{}",
    file_type: str = "",
    dry_run: bool = True,
) -> dict:
    """Publica un item como Feature Layer hosted. OPERACIÓN DE ESCRITURA.

    item_id: ID del item fuente (CSV, Shapefile, GeoJSON, FGDB, etc.).
    publish_params_json: JSON con parámetros opcionales.
                         Ejemplo: {"name": "mi_capa", "maxRecordCount": 2000}
    file_type: tipo del archivo fuente. Vacío = detección automática.
               Valores: 'csv', 'shapefile', 'geojson', 'fileGeodatabase'.
    dry_run: True por defecto — simula sin publicar.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    pub_params = json.loads(publish_params_json) if publish_params_json else {}

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "type": item.type,
            "publish_params": pub_params,
            "file_type": file_type or "auto-detect",
        }

    kwargs: dict[str, Any] = {}
    if file_type:
        kwargs["file_type"] = file_type
    if pub_params:
        kwargs["publish_parameters"] = pub_params

    published = item.publish(**kwargs)
    return {
        "success": True,
        "source_item_id": item_id,
        "published_item_id": published.id,
        "published_title": published.title,
        "published_type": published.type,
        "url": published.url,
    }


@mcp.tool()
def item_export(
    item_id: str,
    export_title: str,
    export_format: str,
    layers_json: str = "[]",
    dry_run: bool = True,
) -> dict:
    """Exporta un servicio a un formato de archivo descargable. OPERACIÓN DE ESCRITURA.

    item_id: ID del item a exportar (Feature Service, Map Service, etc.).
    export_title: título del item exportado resultante en el portal.
    export_format: formato de salida. Valores válidos:
        'Shapefile', 'CSV', 'File Geodatabase', 'Feature Collection',
        'GeoJson', 'Scene Package', 'KML', 'Excel'.
    layers_json: JSON array de índices de capas a exportar (vacío = todas).
                 Ejemplo: '[0, 1]'
    dry_run: True por defecto — simula sin exportar.

    El resultado es un item descargable en el portal. Usar download_item_data()
    para bajarlo al disco local.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    valid_formats = [
        "Shapefile", "CSV", "File Geodatabase", "Feature Collection",
        "GeoJson", "Scene Package", "KML", "Excel",
    ]
    if export_format not in valid_formats:
        raise ValueError(f"Formato inválido: '{export_format}'. Válidos: {valid_formats}")

    layers = json.loads(layers_json) if layers_json and layers_json != "[]" else None

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "source_title": item.title,
            "export_title": export_title,
            "export_format": export_format,
            "layers": layers or "all",
        }

    export_params: dict[str, Any] = {}
    if layers:
        export_params["layers"] = [{"id": i} for i in layers]

    exported = item.export(
        title=export_title,
        export_format=export_format,
        parameters=export_params if export_params else None,
    )
    return {
        "success": True,
        "source_item_id": item_id,
        "exported_item_id": exported.id,
        "exported_title": exported.title,
        "export_format": export_format,
    }


@mcp.tool()
def item_share(
    item_id: str,
    everyone: bool = False,
    org: bool = False,
    groups: str = "[]",
    dry_run: bool = True,
) -> dict:
    """Comparte un item con la organización, todos, o grupos específicos.

    item_id: ID del item a compartir.
    everyone: True para compartir públicamente (acceso anónimo en internet).
    org: True para compartir con toda la organización.
    groups: JSON array de IDs de grupos. Ejemplo: '["abc123", "def456"]'.
    dry_run: True por defecto — simula sin modificar.

    CUIDADO: everyone=True expone el item públicamente sin autenticación.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    group_list = json.loads(groups) if groups and groups != "[]" else []

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "current_access": getattr(item, "access", "private"),
            "would_share": {"everyone": everyone, "org": org, "groups": group_list},
        }

    result = item.share(everyone=everyone, org=org, groups=group_list)
    return {"success": True, "item_id": item_id, "shared": _safe_result(result)}


@mcp.tool()
def item_layers(item_id: str) -> dict:
    """Lista todas las capas y tablas de un item de servicio.

    item_id: ID del item (Feature Layer Collection, Map Service, etc.).

    Retorna por cada capa: índice, nombre, tipo de geometría, conteo de
    features y URL. Incluye capas y tablas en secciones separadas.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    layers_info = []
    for i, lyr in enumerate(item.layers or []):
        info: dict[str, Any] = {
            "index": i,
            "name": lyr.properties.get("name"),
            "type": "layer",
            "geometry_type": lyr.properties.get("geometryType"),
            "url": lyr.url,
        }
        try:
            info["feature_count"] = lyr.query(return_count_only=True)
        except Exception:
            info["feature_count"] = None
        layers_info.append(info)

    tables_info = []
    for i, tbl in enumerate(item.tables or []):
        info = {
            "index": i,
            "name": tbl.properties.get("name"),
            "type": "table",
            "url": tbl.url,
        }
        try:
            info["record_count"] = tbl.query(return_count_only=True)
        except Exception:
            info["record_count"] = None
        tables_info.append(info)

    return {
        "item_id": item_id,
        "title": item.title,
        "item_type": item.type,
        "url": item.url,
        "layers": layers_info,
        "tables": tables_info,
    }


@mcp.tool()
def item_dependent_upon(item_id: str) -> dict:
    """Lista los items de los que depende este item (dependencias hacia adelante).

    item_id: ID del item a analizar.

    Un Web Map depende de sus capas; un Feature Service puede depender de
    su fuente de datos. Útil para entender el impacto antes de modificar un item.
    Cuando la dependencia es por ID, enriquece el resultado con título y tipo.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    deps = item.dependent_upon()
    enriched = []
    for dep in deps.get("list") or []:
        entry: dict[str, Any] = dict(dep)
        if dep.get("dependencyType") == "id" and dep.get("id"):
            dep_item = gis.content.get(dep["id"])
            if dep_item:
                entry["title"] = dep_item.title
                entry["type"] = dep_item.type
        enriched.append(entry)

    return {
        "item_id": item_id,
        "title": item.title,
        "total": deps.get("total", len(enriched)),
        "dependencies": enriched,
    }


@mcp.tool()
def item_dependent_to(item_id: str) -> dict:
    """Lista los items que dependen de este item (dependencias inversas).

    item_id: ID del item a analizar.

    Permite saber qué Web Maps, apps u otros items consumen este servicio.
    CRÍTICO antes de eliminar un servicio: si hay dependientes activos,
    eliminarlos primero o actualizar sus referencias.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    deps = item.dependent_to()
    enriched = []
    for dep in deps.get("list") or []:
        entry: dict[str, Any] = dict(dep)
        if dep.get("dependencyType") == "id" and dep.get("id"):
            dep_item = gis.content.get(dep["id"])
            if dep_item:
                entry["title"] = dep_item.title
                entry["type"] = dep_item.type
        enriched.append(entry)

    return {
        "item_id": item_id,
        "title": item.title,
        "total": deps.get("total", len(enriched)),
        "dependents": enriched,
    }


@mcp.tool()
def item_related_items(
    item_id: str,
    relationship_type: str,
    direction: str = "forward",
) -> list:
    """Lista items relacionados por tipo de relación.

    item_id: ID del item.
    relationship_type: tipo de relación. Valores comunes:
        'Map2Service'    — Web Map → Feature/Map Service
        'Service2Data'   — Service → datos fuente (CSV, FGDB)
        'WMA2Code'       — Web Mapping App → código fuente
        'Survey2Service' — Survey → Feature Service
        'Item2StoryMap'  — Item → Story Map
    direction: 'forward' (este → relacionado) o 'reverse'.

    Referencia completa: https://developers.arcgis.com/rest/users-groups-and-items/relationship-types/
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    related = item.related_items(rel_type=relationship_type, direction=direction)
    return [
        {"id": r.id, "title": r.title, "type": r.type, "owner": r.owner, "url": r.url}
        for r in related
    ]


@mcp.tool()
def item_reassign(
    item_id: str,
    new_owner: str,
    target_folder: str = "/",
    dry_run: bool = True,
) -> dict:
    """Reasigna la propiedad de un item a otro usuario. OPERACIÓN DE ESCRITURA.

    item_id: ID del item a reasignar.
    new_owner: nombre de usuario del nuevo propietario (debe existir).
    target_folder: carpeta destino en el perfil del nuevo propietario.
                   Usar '/' para la raíz. Default '/'.
    dry_run: True por defecto — simula sin reasignar.

    Requiere privilegios de administrador.
    CUIDADO: el item desaparece del contenido del propietario original.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    new_owner_obj = gis.users.get(new_owner)
    if new_owner_obj is None:
        raise ValueError(f"Usuario no encontrado: {new_owner}")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "current_owner": item.owner,
            "new_owner": new_owner,
            "target_folder": target_folder,
        }

    result = item.reassign_to(target_owner=new_owner, target_folder=target_folder)
    return {
        "success": bool(result),
        "item_id": item_id,
        "new_owner": new_owner,
        "folder": target_folder,
    }


@mcp.tool()
def item_get_data(item_id: str) -> Any:
    """Obtiene los datos asociados a un item directamente en memoria.

    item_id: ID del item.

    Comportamiento por tipo de item:
    - JSON / Web Map / Feature Collection → retorna dict Python.
    - CSV / texto → retorna ruta al archivo descargado en temp.
    - Binario → retorna ruta al archivo descargado en temp.

    Diferencia con download_item_data: este método usa Item.get_data()
    que para JSON retorna el contenido sin escribir en disco.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    data = item.get_data()
    return _safe_result(data)


@mcp.tool()
def item_thumbnail(item_id: str, save_folder: str = "") -> dict:
    """Descarga la miniatura (thumbnail) de un item al sistema local.

    item_id: ID del item.
    save_folder: carpeta donde guardar la imagen. Vacío = directorio actual.

    Retorna la ruta al archivo PNG/JPG descargado.
    Útil para verificar visualmente items en scripts de administración masiva.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    if not item.thumbnail:
        return {"item_id": item_id, "title": item.title, "has_thumbnail": False}

    path = item.download_thumbnail(save_folder=save_folder or None)
    return {"item_id": item_id, "title": item.title, "has_thumbnail": True, "saved_to": path}


@mcp.tool()
def item_add_comment(item_id: str, comment: str) -> dict:
    """Agrega un comentario a un item. OPERACIÓN DE ESCRITURA.

    item_id: ID del item.
    comment: texto del comentario.

    Los comentarios son visibles para todos los usuarios que pueden ver el item.
    Útil para documentar problemas, actualizaciones o notas de revisión colaborativa.
    Requiere ARCGIS_WRITE_ENABLED=true.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    result = item.add_comment(comment=comment)
    return {
        "success": True,
        "item_id": item_id,
        "comment_id": getattr(result, "id", None),
        "comment": comment,
    }


@mcp.tool()
def item_resources(item_id: str) -> list:
    """Lista los recursos (archivos adjuntos) de un item del portal.

    item_id: ID del item.

    Los item resources son archivos adicionales adjuntos al item: imágenes,
    PDFs, templates, archivos de configuración, etc.
    Retorna nombre, tamaño y URL de acceso de cada recurso.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    resources = item.resources.list()
    result = []
    for r in resources:
        if isinstance(r, dict):
            result.append(r)
        else:
            result.append({
                "resource": getattr(r, "resource", str(r)),
                "size": getattr(r, "size", None),
            })
    return result


def _resolve_table(item_id: str, table_index: int = 0):
    """Resuelve item ID a un Table (non-spatial) por índice."""
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    tables = item.tables
    if not tables:
        raise ValueError(f"El item {item_id} no tiene tablas.")
    if table_index >= len(tables):
        raise ValueError(f"table_index={table_index} fuera de rango (tiene {len(tables)} tablas).")
    return tables[table_index]


