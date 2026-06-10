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
#   GESTIÓN AVANZADA DE USUARIOS (User Management)
# =========================================================================== #
@mcp.tool()
def user_get(username: str) -> dict:
    """Obtiene información detallada de un usuario por su nombre de usuario.
    
    username: nombre de usuario en el portal.
    
    Retorna información completa incluyendo: nombre completo, email, rol,
    descripción, fecha de creación, última conexión, privilegios, y más.
    """
    gis = get_gis()
    try:
        user = gis.users.get(username)
        if user is None:
            raise ValueError(f"Usuario no encontrado: {username}")
        
        return {
            "username": user.username,
            "fullName": user.fullName if hasattr(user, 'fullName') else "",
            "email": user.email if hasattr(user, 'email') else "",
            "role": getattr(user, "role", None),
            "description": user.description if hasattr(user, 'description') else "",
            "created": str(user.created) if hasattr(user, 'created') else None,
            "modified": str(user.modified) if hasattr(user, 'modified') else None,
            "lastLogin": str(user.lastLogin) if hasattr(user, 'lastLogin') else None,
            "privileges": list(user.privileges) if hasattr(user, 'privileges') else [],
            "userLicenseType": user.userLicenseType if hasattr(user, 'userLicenseType') else "",
            "disabled": getattr(user, 'disabled', False),
            "thumbnail": user.thumbnail if hasattr(user, 'thumbnail') else None,
            "tags": user.tags if hasattr(user, 'tags') else [],
            "culture": user.culture if hasattr(user, 'culture') else "",
            "region": user.region if hasattr(user, 'region') else "",
            "units": user.units if hasattr(user, 'units') else "",
        }
    except Exception as e:
        raise ValueError(f"Error obteniendo usuario {username}: {e}")


@mcp.tool()
def user_update(
    username: str,
    full_name: str = "",
    email: str = "",
    description: str = "",
    tags: str = "[]",
    dry_run: bool = True,
) -> dict:
    """Actualiza la información de un usuario. OPERACIÓN DE ESCRITURA.
    
    username: nombre del usuario a actualizar.
    full_name: nuevo nombre completo (dejar vacío para no cambiar).
    email: nuevo email (dejar vacío para no cambiar).
    description: nueva descripción (dejar vacío para no cambiar).
    tags: JSON array de tags, ej. '["admin", "gis"]' (dejar '[]' para no cambiar).
    dry_run: True por defecto — simula sin escribir.
    
    Solo actualiza los campos que se proporcionen (no vacíos).
    Requiere privilegios de administrador.
    """
    _require_write()
    gis = get_gis()
    
    user = gis.users.get(username)
    if user is None:
        raise ValueError(f"Usuario no encontrado: {username}")
    
    # Construir diccionario de propiedades a actualizar
    updates = {}
    if full_name:
        updates["fullName"] = full_name
    if email:
        updates["email"] = email
    if description:
        updates["description"] = description
    if tags and tags != "[]":
        tag_list = json.loads(tags)
        if tag_list:
            updates["tags"] = tag_list
    
    if not updates:
        return {"error": "No se proporcionaron cambios", "username": username}
    
    if dry_run:
        return {
            "dry_run": True,
            "username": username,
            "current_fullName": user.fullName if hasattr(user, 'fullName') else "",
            "would_update": updates,
        }
    
    success = user.update(**updates)
    return {
        "success": success,
        "username": username,
        "updated": updates,
    }


@mcp.tool()
def user_disable(username: str, dry_run: bool = True) -> dict:
    """Desactiva la cuenta de un usuario. OPERACIÓN DE ESCRITURA.
    
    username: nombre del usuario a desactivar.
    dry_run: True por defecto — simula sin escribir.
    
    Los usuarios desactivados no pueden iniciar sesión pero mantienen su contenido.
    Requiere privilegios de administrador.
    """
    _require_write()
    gis = get_gis()
    
    user = gis.users.get(username)
    if user is None:
        raise ValueError(f"Usuario no encontrado: {username}")
    
    if dry_run:
        return {
            "dry_run": True,
            "username": username,
            "currently_disabled": getattr(user, 'disabled', False),
            "action": "would disable",
        }
    
    success = user.disable()
    return {
        "success": success,
        "username": username,
        "disabled": True,
    }


@mcp.tool()
def user_enable(username: str, dry_run: bool = True) -> dict:
    """Activa la cuenta de un usuario previamente desactivado. OPERACIÓN DE ESCRITURA.
    
    username: nombre del usuario a activar.
    dry_run: True por defecto — simula sin escribir.
    
    Requiere privilegios de administrador.
    """
    _require_write()
    gis = get_gis()
    
    user = gis.users.get(username)
    if user is None:
        raise ValueError(f"Usuario no encontrado: {username}")
    
    if dry_run:
        return {
            "dry_run": True,
            "username": username,
            "currently_disabled": getattr(user, 'disabled', False),
            "action": "would enable",
        }
    
    success = user.enable()
    return {
        "success": success,
        "username": username,
        "disabled": False,
    }


@mcp.tool()
def user_set_role(
    username: str,
    role: str,
    dry_run: bool = True,
) -> dict:
    """Cambia el rol de un usuario. OPERACIÓN DE ESCRITURA.
    
    username: nombre del usuario.
    role: nuevo rol. Valores válidos:
          - 'org_admin' (Administrador de la organización)
          - 'org_publisher' (Editor/Publisher)
          - 'org_user' (Usuario/Viewer)
          - O un rol personalizado existente en el portal
    dry_run: True por defecto — simula sin escribir.
    
    Requiere privilegios de administrador.
    CUIDADO: Cambiar roles afecta permisos y acceso a recursos.
    """
    _require_write()
    gis = get_gis()
    
    user = gis.users.get(username)
    if user is None:
        raise ValueError(f"Usuario no encontrado: {username}")
    
    # Validar roles estándar
    valid_roles = ['org_admin', 'org_publisher', 'org_user']
    if role not in valid_roles:
        # Podría ser un rol personalizado - advertir pero permitir
        print(f"[WARN] Rol '{role}' no es estándar. Roles estándar: {valid_roles}", file=sys.stderr)
    
    if dry_run:
        return {
            "dry_run": True,
            "username": username,
            "current_role": getattr(user, "role", None),
            "would_change_to": role,
        }
    
    success = user.update_role(role)
    return {
        "success": success,
        "username": username,
        "previous_role": getattr(user, "role", None),
        "new_role": role,
    }


@mcp.tool()
def user_content(
    username: str,
    folder: str = "",
    max_items: int = 100,
) -> list:
    """Lista todo el contenido de un usuario.
    
    username: nombre del usuario.
    folder: nombre de carpeta específica (opcional). Vacío = raíz + todas las carpetas.
    max_items: máximo de items a retornar por carpeta.
    
    Retorna lista de items con información básica.
    """
    gis = get_gis()
    
    user = gis.users.get(username)
    if user is None:
        raise ValueError(f"Usuario no encontrado: {username}")
    
    try:
        # Obtener items del usuario
        items = user.items(folder=folder or None, max_items=max_items)
        
        result = []
        for item in items:
            result.append({
                "id": item.id,
                "title": item.title,
                "type": item.type,
                "owner": item.owner,
                "folder": folder or "root",
                "created": str(item.created) if hasattr(item, 'created') else None,
                "modified": str(item.modified) if hasattr(item, 'modified') else None,
                "size": item.size if hasattr(item, 'size') else None,
                "numViews": item.numViews if hasattr(item, 'numViews') else 0,
            })
        
        return result
    except Exception as e:
        raise ValueError(f"Error obteniendo contenido de {username}: {e}")


# =========================================================================== #
#   GESTIÓN AVANZADA DE GRUPOS (Group Management)
# =========================================================================== #
@mcp.tool()
def group_get(group_id: str) -> dict:
    """Obtiene información detallada de un grupo por su ID.
    
    group_id: ID único del grupo en el portal.
    
    Retorna información completa incluyendo: título, descripción, tags,
    owner, fecha de creación, acceso, número de usuarios, y más.
    """
    gis = get_gis()
    try:
        group = gis.groups.get(group_id)
        if group is None:
            raise ValueError(f"Grupo no encontrado: {group_id}")
        
        return {
            "id": group.id,
            "title": group.title,
            "description": group.description if hasattr(group, 'description') else "",
            "snippet": group.snippet if hasattr(group, 'snippet') else "",
            "tags": group.tags if hasattr(group, 'tags') else [],
            "owner": group.owner,
            "created": str(group.created) if hasattr(group, 'created') else None,
            "modified": str(group.modified) if hasattr(group, 'modified') else None,
            "access": group.access if hasattr(group, 'access') else "private",
            "isInvitationOnly": group.isInvitationOnly if hasattr(group, 'isInvitationOnly') else False,
            "thumbnail": group.thumbnail if hasattr(group, 'thumbnail') else None,
            "phone": group.phone if hasattr(group, 'phone') else "",
            "sortField": group.sortField if hasattr(group, 'sortField') else "",
            "sortOrder": group.sortOrder if hasattr(group, 'sortOrder') else "",
            "memberCount": len(group.get_members()['users']) if hasattr(group, 'get_members') else 0,
        }
    except Exception as e:
        raise ValueError(f"Error obteniendo grupo {group_id}: {e}")


@mcp.tool()
def group_update(
    group_id: str,
    title: str = "",
    description: str = "",
    tags: str = "[]",
    snippet: str = "",
    dry_run: bool = True,
) -> dict:
    """Actualiza la información de un grupo. OPERACIÓN DE ESCRITURA.
    
    group_id: ID del grupo a actualizar.
    title: nuevo título (dejar vacío para no cambiar).
    description: nueva descripción (dejar vacío para no cambiar).
    tags: JSON array de tags, ej. '["gis", "collaboration"]' (dejar '[]' para no cambiar).
    snippet: nuevo resumen corto (dejar vacío para no cambiar).
    dry_run: True por defecto — simula sin escribir.
    
    Solo actualiza los campos que se proporcionen (no vacíos).
    Requiere ser owner del grupo o administrador.
    """
    _require_write()
    gis = get_gis()
    
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")
    
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
        return {"error": "No se proporcionaron cambios", "group_id": group_id}
    
    if dry_run:
        return {
            "dry_run": True,
            "group_id": group_id,
            "current_title": group.title,
            "would_update": updates,
        }
    
    success = group.update(**updates)
    return {
        "success": success,
        "group_id": group_id,
        "updated": updates,
    }


@mcp.tool()
def group_add_users(
    group_id: str,
    usernames: str,
    dry_run: bool = True,
) -> dict:
    """Agrega usuarios a un grupo. OPERACIÓN DE ESCRITURA.
    
    group_id: ID del grupo.
    usernames: JSON array de nombres de usuario, ej. '["user1", "user2"]'.
    dry_run: True por defecto — simula sin escribir.
    
    Requiere ser owner del grupo o administrador.
    """
    _require_write()
    gis = get_gis()
    
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")
    
    user_list = json.loads(usernames)
    if not user_list:
        return {"error": "No se proporcionaron usuarios", "group_id": group_id}
    
    if dry_run:
        return {
            "dry_run": True,
            "group_id": group_id,
            "group_title": group.title,
            "would_add_users": user_list,
        }
    
    # Agregar usuarios al grupo
    results = group.add_users(user_list)
    return {
        "group_id": group_id,
        "requested": user_list,
        "results": _safe_result(results),
    }


@mcp.tool()
def group_remove_users(
    group_id: str,
    usernames: str,
    dry_run: bool = True,
) -> dict:
    """Remueve usuarios de un grupo. OPERACIÓN DE ESCRITURA.
    
    group_id: ID del grupo.
    usernames: JSON array de nombres de usuario, ej. '["user1", "user2"]'.
    dry_run: True por defecto — simula sin escribir.
    
    Requiere ser owner del grupo o administrador.
    """
    _require_write()
    gis = get_gis()
    
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")
    
    user_list = json.loads(usernames)
    if not user_list:
        return {"error": "No se proporcionaron usuarios", "group_id": group_id}
    
    if dry_run:
        return {
            "dry_run": True,
            "group_id": group_id,
            "group_title": group.title,
            "would_remove_users": user_list,
        }
    
    # Remover usuarios del grupo
    results = group.remove_users(user_list)
    return {
        "group_id": group_id,
        "requested": user_list,
        "results": _safe_result(results),
    }


@mcp.tool()
def group_content(
    group_id: str,
    max_items: int = 100,
) -> list:
    """Lista todos los items compartidos en un grupo.
    
    group_id: ID del grupo.
    max_items: máximo de items a retornar.
    
    Retorna lista de items compartidos con el grupo.
    """
    gis = get_gis()
    
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")
    
    try:
        # Buscar contenido compartido con el grupo
        items = gis.content.search(f"group:{group_id}", max_items=max_items)
        
        result = []
        for item in items:
            result.append({
                "id": item.id,
                "title": item.title,
                "type": item.type,
                "owner": item.owner,
                "created": str(item.created) if hasattr(item, 'created') else None,
                "modified": str(item.modified) if hasattr(item, 'modified') else None,
                "numViews": item.numViews if hasattr(item, 'numViews') else 0,
            })
        
        return result
    except Exception as e:
        raise ValueError(f"Error obteniendo contenido del grupo {group_id}: {e}")


@mcp.tool()
def group_members(group_id: str) -> dict:
    """Lista los miembros de un grupo por su ID.

    group_id: ID del grupo.
    Equivalente a arcgis.gis.Group.get_members().
    Retorna: {'users': [...], 'admins': [...], 'owner': '...'}
    """
    gis = get_gis()
    grupo = gis.groups.get(group_id)
    if grupo is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")
    return grupo.get_members()


@mcp.tool()
def group_create(title: str, description: str = "", tags: list = None) -> dict:
    """Crea un grupo nuevo en el portal. OPERACIÓN DE ESCRITURA.

    title: nombre del grupo.
    description: descripción opcional.
    tags: lista de etiquetas.
    Equivalente a arcgis.gis.GroupManager.create().
    """
    _require_write()
    gis = get_gis()
    grupo = gis.groups.create(title=title, description=description, tags=tags or [])
    return _safe_result(grupo)


# =========================================================================== #
#   SHARING — SharingManager y SharingGroupManager  (prefijo share_)
#
#   Patrón nuevo de la API (v2.x):
#     item.sharing              → SharingManager
#     item.sharing.access       → 'private' | 'org' | 'public'
#     item.sharing.groups       → SharingGroupManager
#     item.sharing.groups.add() / .remove() / .list()
# =========================================================================== #

@mcp.tool()
def share_get_access(item_id: str) -> dict:
    """Obtiene el nivel de acceso actual de un item via SharingManager.

    item_id: ID del item.

    Retorna: access ('private' | 'org' | 'public'), título y propietario.
    Útil para auditorías masivas de contenido expuesto involuntariamente.
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    sharing = item.sharing
    access = getattr(sharing, "access", None) or getattr(item, "access", "private")

    return {
        "item_id": item_id,
        "title": item.title,
        "type": item.type,
        "owner": item.owner,
        "access": access,
    }


@mcp.tool()
def share_set_access(
    item_id: str,
    access: str,
    dry_run: bool = True,
) -> dict:
    """Cambia el nivel de acceso de un item via SharingManager. OPERACIÓN DE ESCRITURA.

    item_id: ID del item.
    access: nuevo nivel de acceso:
        'private' — solo el propietario.
        'org'     — todos los usuarios autenticados de la organización.
        'public'  — acceso anónimo en internet (CUIDADO).
    dry_run: True por defecto — simula sin escribir.

    CUIDADO: 'public' expone el item sin autenticación.
    Para compartir con grupos específicos usar share_group_add().
    """
    _require_write()
    valid = ("private", "org", "public")
    if access not in valid:
        raise ValueError(f"access debe ser uno de {valid}. Recibido: '{access}'")

    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    current_access = getattr(item.sharing, "access", None) or getattr(item, "access", "private")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "current_access": current_access,
            "would_set_to": access,
        }

    item.sharing.access = access
    return {
        "success": True,
        "item_id": item_id,
        "previous_access": current_access,
        "new_access": access,
    }


@mcp.tool()
def share_status(item_id: str) -> dict:
    """Muestra el estado completo de compartición de un item.

    item_id: ID del item.

    Retorna: nivel de acceso, grupos con los que está compartido (IDs y títulos),
    si está disponible para toda la org o para todos.
    Combina SharingManager.access + SharingGroupManager.list().
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    sharing = item.sharing
    access = getattr(sharing, "access", None) or getattr(item, "access", "private")

    groups_info = []
    try:
        for g in sharing.groups.list():
            groups_info.append({
                "id": g.id if hasattr(g, "id") else getattr(g, "groupid", str(g)),
                "title": getattr(g, "title", str(g)),
                "owner": getattr(g, "owner", ""),
            })
    except Exception:
        # fallback via shared_with
        sw = getattr(item, "shared_with", {}) or {}
        for g in sw.get("groups", []):
            groups_info.append({"id": getattr(g, "id", str(g)), "title": getattr(g, "title", "")})

    return {
        "item_id": item_id,
        "title": item.title,
        "type": item.type,
        "owner": item.owner,
        "access": access,
        "shared_with_org": access in ("org", "public"),
        "shared_with_everyone": access == "public",
        "groups": groups_info,
        "group_count": len(groups_info),
    }


@mcp.tool()
def share_bulk_set_access(
    item_ids_json: str,
    access: str,
    dry_run: bool = True,
) -> list:
    """Cambia el nivel de acceso de múltiples items a la vez. OPERACIÓN DE ESCRITURA.

    item_ids_json: JSON array de IDs de items.
                   Ejemplo: '["abc123", "def456", "ghi789"]'
    access: 'private' | 'org' | 'public'
    dry_run: True por defecto — simula sin escribir.

    Útil para: retirar acceso público a una colección entera, o sincronizar
    niveles de acceso antes de una publicación oficial.
    """
    _require_write()
    valid = ("private", "org", "public")
    if access not in valid:
        raise ValueError(f"access debe ser uno de {valid}")

    item_ids: list[str] = json.loads(item_ids_json)
    if not item_ids:
        return []

    gis = get_gis()
    results = []
    for item_id in item_ids:
        try:
            item = gis.content.get(item_id)
            if item is None:
                results.append({"item_id": item_id, "success": False, "error": "Item no encontrado"})
                continue
            current = getattr(item.sharing, "access", None) or getattr(item, "access", "private")
            if dry_run:
                results.append({
                    "item_id": item_id,
                    "title": item.title,
                    "dry_run": True,
                    "current_access": current,
                    "would_set_to": access,
                })
            else:
                item.sharing.access = access
                results.append({
                    "item_id": item_id,
                    "title": item.title,
                    "success": True,
                    "previous_access": current,
                    "new_access": access,
                })
        except Exception as e:
            results.append({"item_id": item_id, "success": False, "error": str(e)})

    return results


@mcp.tool()
def share_audit_public(max_items: int = 200) -> list:
    """Lista todos los items públicos del portal (access='public') para auditoría.

    max_items: máximo de items a inspeccionar (default 200).

    Retorna lista con: id, título, tipo, propietario y acceso de cada item público.
    Herramienta clave para administradores que necesitan revisar exposición de datos.
    """
    gis = get_gis()
    items = gis.content.search(query="access:public", max_items=max_items)
    result = []
    for item in items:
        access = getattr(item.sharing, "access", None) or getattr(item, "access", "public")
        result.append({
            "item_id": item.id,
            "title": item.title,
            "type": item.type,
            "owner": item.owner,
            "access": access,
            "url": item.url,
        })
    return result


@mcp.tool()
def share_audit_by_owner(username: str, max_items: int = 200) -> dict:
    """Audita el estado de compartición de todos los items de un usuario.

    username: nombre del usuario a auditar.
    max_items: máximo de items a inspeccionar.

    Retorna resumen (total por nivel de acceso) y detalle de cada item.
    Útil para: offboarding de empleados, revisión de contenido sensible,
    identificar items privados que deberían estar compartidos y viceversa.
    """
    gis = get_gis()
    items = gis.content.search(query=f"owner:{username}", max_items=max_items)

    summary = {"private": 0, "org": 0, "public": 0, "unknown": 0}
    detail = []
    for item in items:
        access = getattr(item.sharing, "access", None) or getattr(item, "access", "private") or "unknown"
        summary[access if access in summary else "unknown"] += 1
        detail.append({
            "item_id": item.id,
            "title": item.title,
            "type": item.type,
            "access": access,
        })

    return {
        "username": username,
        "total_items": len(items),
        "summary": summary,
        "items": detail,
    }


# ---------------------------------------------------------------------------
# SharingGroupManager — item.sharing.groups
# ---------------------------------------------------------------------------

@mcp.tool()
def share_group_add(
    item_id: str,
    group_id: str,
    dry_run: bool = True,
) -> dict:
    """Agrega un item a un grupo via SharingGroupManager. OPERACIÓN DE ESCRITURA.

    item_id: ID del item a compartir.
    group_id: ID del grupo destino.
    dry_run: True por defecto — simula sin escribir.

    Usa item.sharing.groups.add() — API nueva (v2.x).
    El propietario del item debe tener acceso al grupo o ser admin.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "item_title": item.title,
            "group_id": group_id,
            "group_title": group.title,
            "action": "would add item to group",
        }

    success = item.sharing.groups.add(group=group)
    return {
        "success": bool(success),
        "item_id": item_id,
        "group_id": group_id,
        "group_title": group.title,
    }


@mcp.tool()
def share_group_remove(
    item_id: str,
    group_id: str,
    dry_run: bool = True,
) -> dict:
    """Quita un item de un grupo via SharingGroupManager. OPERACIÓN DE ESCRITURA.

    item_id: ID del item.
    group_id: ID del grupo del que se retira el item.
    dry_run: True por defecto — simula sin escribir.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "item_title": item.title,
            "group_id": group_id,
            "group_title": group.title,
            "action": "would remove item from group",
        }

    success = item.sharing.groups.remove(group=group)
    return {
        "success": bool(success),
        "item_id": item_id,
        "group_id": group_id,
        "group_title": group.title,
    }


@mcp.tool()
def share_group_list(item_id: str) -> list:
    """Lista todos los grupos con los que está compartido un item via SharingGroupManager.

    item_id: ID del item.

    Retorna id, título y propietario de cada grupo.
    Equivalente a item.sharing.groups.list().
    """
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    groups = item.sharing.groups.list()
    return [
        {
            "id": g.id if hasattr(g, "id") else getattr(g, "groupid", str(g)),
            "title": getattr(g, "title", ""),
            "owner": getattr(g, "owner", ""),
            "access": getattr(g, "access", ""),
        }
        for g in groups
    ]


@mcp.tool()
def share_group_replace(
    item_id: str,
    new_group_ids_json: str,
    dry_run: bool = True,
) -> dict:
    """Reemplaza todos los grupos de compartición de un item con un nuevo set.

    item_id: ID del item.
    new_group_ids_json: JSON array de IDs de grupos que DEBEN tener el item.
                        Ejemplo: '["abc123", "def456"]'
                        Usar '[]' para dejar el item sin grupos.
    dry_run: True por defecto — simula sin escribir.

    Calcula la diferencia (a agregar y a quitar) y aplica solo los cambios
    necesarios para que el estado final coincida exactamente con new_group_ids.
    """
    _require_write()
    gis = get_gis()
    item = gis.content.get(item_id)
    if item is None:
        raise ValueError(f"Item no encontrado: {item_id}")

    new_ids: set[str] = set(json.loads(new_group_ids_json))
    current_groups = item.sharing.groups.list()
    current_ids = {
        g.id if hasattr(g, "id") else getattr(g, "groupid", "")
        for g in current_groups
    }

    to_add = new_ids - current_ids
    to_remove = current_ids - new_ids

    if dry_run:
        return {
            "dry_run": True,
            "item_id": item_id,
            "title": item.title,
            "current_groups": list(current_ids),
            "would_add": list(to_add),
            "would_remove": list(to_remove),
        }

    added, removed, errors = [], [], []
    for gid in to_add:
        try:
            g = gis.groups.get(gid)
            if g:
                item.sharing.groups.add(group=g)
                added.append(gid)
            else:
                errors.append({"group_id": gid, "error": "Grupo no encontrado"})
        except Exception as e:
            errors.append({"group_id": gid, "error": str(e)})

    for gid in to_remove:
        try:
            g = gis.groups.get(gid)
            if g:
                item.sharing.groups.remove(group=g)
                removed.append(gid)
        except Exception as e:
            errors.append({"group_id": gid, "error": str(e)})

    return {
        "item_id": item_id,
        "added": added,
        "removed": removed,
        "final_groups": list((current_ids - set(removed)) | set(added)),
        "errors": errors,
    }


@mcp.tool()
def share_group_copy(
    source_item_id: str,
    target_item_id: str,
    dry_run: bool = True,
) -> dict:
    """Copia la configuración de grupos de compartición de un item a otro.

    source_item_id: ID del item cuyos grupos se copian.
    target_item_id: ID del item que recibirá esa misma configuración de grupos.
    dry_run: True por defecto — simula sin escribir.

    Útil al publicar una nueva versión de un servicio: el nuevo item hereda
    exactamente los mismos grupos que el original, sin tener que configurar
    uno por uno.
    """
    _require_write()
    gis = get_gis()
    source = gis.content.get(source_item_id)
    if source is None:
        raise ValueError(f"Item fuente no encontrado: {source_item_id}")
    target = gis.content.get(target_item_id)
    if target is None:
        raise ValueError(f"Item destino no encontrado: {target_item_id}")

    source_groups = source.sharing.groups.list()
    source_group_ids = [
        g.id if hasattr(g, "id") else getattr(g, "groupid", "")
        for g in source_groups
    ]

    if dry_run:
        return {
            "dry_run": True,
            "source_item_id": source_item_id,
            "source_title": source.title,
            "target_item_id": target_item_id,
            "target_title": target.title,
            "would_copy_groups": source_group_ids,
        }

    added, errors = [], []
    for g in source_groups:
        try:
            target.sharing.groups.add(group=g)
            added.append(g.id if hasattr(g, "id") else getattr(g, "groupid", str(g)))
        except Exception as e:
            errors.append({"group": str(g), "error": str(e)})

    return {
        "source_item_id": source_item_id,
        "target_item_id": target_item_id,
        "groups_added": added,
        "errors": errors,
    }


@mcp.tool()
def share_group_audit(group_id: str, max_items: int = 200) -> dict:
    """Audita todos los items compartidos con un grupo y sus niveles de acceso.

    group_id: ID del grupo a auditar.
    max_items: máximo de items a analizar.

    Retorna: resumen por tipo de item, lista detallada con acceso individual.
    Útil para: revisar que un grupo de distribución no comparte datos sensibles,
    planificar la migración de grupos, y generar reportes de gobernanza.
    """
    gis = get_gis()
    group = gis.groups.get(group_id)
    if group is None:
        raise ValueError(f"Grupo no encontrado: {group_id}")

    items = group.content()[:max_items]
    summary_by_type: dict[str, int] = {}
    detail = []

    for item in items:
        item_type = item.type or "Unknown"
        summary_by_type[item_type] = summary_by_type.get(item_type, 0) + 1
        access = getattr(item.sharing, "access", None) or getattr(item, "access", "private")
        detail.append({
            "item_id": item.id,
            "title": item.title,
            "type": item_type,
            "owner": item.owner,
            "access": access,
        })

    return {
        "group_id": group_id,
        "group_title": group.title,
        "group_owner": group.owner,
        "total_items": len(items),
        "summary_by_type": summary_by_type,
        "items": detail,
    }


