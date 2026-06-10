from __future__ import annotations
import json
from typing import Any

from _server import mcp
from _auth import (
    get_gis, detect_platform, WRITE_ENABLED,
    _safe_result,
    connect_with_method, save_session_as_profile,
)

# =========================================================================== #
#   INTROSPECCIÓN
# =========================================================================== #
@mcp.tool()
def whoami() -> dict:
    """Identidad, plataforma, versión y privilegios de la sesión.

    Llamar SIEMPRE antes de actuar para saber qué está permitido.
    """
    gis = get_gis()
    info: dict[str, Any] = {
        "platform": detect_platform(gis).value,
        "version": gis.properties.get("currentVersion"),
        "org": gis.properties.get("name"),
        "write_enabled": WRITE_ENABLED,
    }
    me = gis.users.me
    if me is not None:
        info.update(
            username=me.username,
            role=me.role,
            privileges=list(me.privileges or []),
        )
    else:
        info["username"] = None
        info["note"] = (
            "Sesión por API key/app: sin usuario nombrado. "
            "Privilegios del token vía /self del portal."
        )
    return info


@mcp.tool()
def gis_properties() -> dict:
    """Retorna propiedades generales del portal (GIS).

    Equivalente a arcgis.gis.GIS.properties.
    """
    gis = get_gis()
    props: Any = gis.properties

    if hasattr(props, "to_dict") and callable(getattr(props, "to_dict")):
        try:
            props = props.to_dict()
        except Exception:
            pass

    if isinstance(props, str):
        text = props.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                props = json.loads(text)
            except Exception:
                pass

    if not isinstance(props, (dict, list, str, int, float, bool, type(None))):
        try:
            props = dict(props)
        except Exception:
            pass

    return _safe_result(props)


@mcp.tool()
def gis_version() -> str:
    """Retorna la versión del portal ArcGIS (Online o Enterprise).

    Equivalente a arcgis.gis.GIS.version.
    """
    gis = get_gis()
    return str(gis.version)


# =========================================================================== #
#   DESCUBRIMIENTO DE CONTENIDO
# =========================================================================== #
@mcp.tool()
def content_search(
    query: str,
    item_type: str = "",
    max_items: int = 25,
) -> list:
    """Busca items en el portal.

    item_type: filtro opcional (ej. 'Feature Layer', 'Geoprocessing Service',
               'Web Map', 'Map Service'). Dejar vacío para todos.
    """
    gis = get_gis()
    items = gis.content.search(
        query=query,
        item_type=item_type or None,
        max_items=max_items,
    )
    return [
        {
            "id": i.id,
            "title": i.title,
            "type": i.type,
            "owner": i.owner,
            "url": i.url,
        }
        for i in items
    ]


@mcp.tool()
def content_find_large(min_mb: int = 500) -> list:
    """Busca items que consumen más de min_mb MB de espacio.

    min_mb: umbral mínimo en megabytes (default 500).
    Equivalente a buscar en arcgis.gis.ContentManager con filtro por tamaño.
    """
    gis = get_gis()
    items = gis.content.search('', max_items=1000)
    return [
        {"title": i.title, "size_mb": i.size/1024/1024}
        for i in items
        if hasattr(i, 'size') and i.size and i.size/1024/1024 > min_mb
    ]


# =========================================================================== #
#   AUTENTICACIÓN
# =========================================================================== #

@mcp.tool()
def arcgis_auth_status() -> dict:
    """Muestra el estado de la conexión GIS activa.

    Si no hay sesión activa, devuelve los métodos disponibles para que
    el usuario elija cómo conectarse. El modelo debe presentar esas opciones
    y llamar a arcgis_auth_connect() con el método elegido.
    """
    from _auth import _gis as current_gis
    if current_gis is None:
        return {
            "status": "not_connected",
            "action_required": "select_auth_method",
            "message": "No hay sesión activa. ¿Con qué método querés conectarte?",
            "available_methods": [
                {
                    "method": "pro",
                    "label": "ArcGIS Pro (sesión activa)",
                    "description": "Usa la sesión ya autenticada en ArcGIS Pro. No requiere parámetros.",
                    "requires": [],
                },
                {
                    "method": "oauth",
                    "label": "OAuth2 (navegador)",
                    "description": "Abre el navegador para autenticarte. Recomendado para AGOL y Enterprise.",
                    "requires": ["url (Enterprise)", "client_id (opcional si está en .env)"],
                },
                {
                    "method": "apikey",
                    "label": "API Key",
                    "description": "Lee ARCGIS_API_KEY del .env. Para Enterprise 11.4+ o AGOL.",
                    "requires": ["url", "ARCGIS_API_KEY en .env"],
                },
                {
                    "method": "profile",
                    "label": "Perfil nombrado (keyring)",
                    "description": "Usa credenciales guardadas en Windows Credential Manager.",
                    "requires": ["profile_name (o ARCGIS_PROFILE en .env)"],
                },
                {
                    "method": "token",
                    "label": "Token externo",
                    "description": "Lee ARCGIS_TOKEN del .env.",
                    "requires": ["url", "ARCGIS_TOKEN en .env"],
                },
                {
                    "method": "userpass",
                    "label": "Usuario / Contraseña",
                    "description": "Lee ARCGIS_USER y ARCGIS_PASS del .env. Solo para desarrollo local.",
                    "requires": ["url", "ARCGIS_USER y ARCGIS_PASS en .env"],
                },
            ],
            "hint": (
                "Pedile al usuario que elija un método y llamá a "
                "arcgis_auth_connect(method='...') con su elección."
            ),
        }
    try:
        me = current_gis.users.me
        return {
            "status": "connected",
            "url": current_gis.url,
            "username": me.username if me else None,
            "role": me.role if me else None,
            "org": current_gis.properties.get("name"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def arcgis_auth_connect(
    method: str,
    url: str = "",
    client_id: str = "",
    profile: str = "",
) -> dict:
    """Cambia el método de autenticación en caliente sin reiniciar el servidor.

    method:
        "pro"      — ArcGIS Pro (sesión activa abierta). No requiere parámetros.
        "oauth"    — OAuth2: abre el navegador. Requiere url para Enterprise.
                     Opcional: client_id (si no está en .env como ARCGIS_CLIENT_ID).
        "apikey"   — API Key leída desde ARCGIS_API_KEY en .env. Requiere url.
        "profile"  — Perfil nombrado. Indicá profile o configurá ARCGIS_PROFILE en .env.
        "token"    — Token crudo leído desde ARCGIS_TOKEN en .env. Requiere url.
        "userpass" — Usuario/contraseña leídos desde ARCGIS_USER/ARCGIS_PASS en .env.

    SEGURIDAD: api_key, token y password NO se aceptan como parámetros directos
    para evitar que queden expuestos en el historial del chat. Configurarlos en .env.
    """
    try:
        gis = connect_with_method(
            method=method,
            url=url or None,
            client_id=client_id or None,
            profile=profile or None,
        )
        me = gis.users.me
        return {
            "status": "ok",
            "method": method,
            "url": gis.url,
            "username": me.username if me else None,
            "org": gis.properties.get("name"),
        }
    except Exception as e:
        return {"status": "error", "method": method, "error": str(e)}


@mcp.tool()
def arcgis_auth_save_profile(profile_name: str = "arcgis-mcp") -> dict:
    """Guarda la sesión OAuth2 activa en el keyring del SO como perfil nombrado.

    Después de llamar este tool, el servidor reconectará automáticamente en
    cada reinicio sin abrir el navegador (usa el refresh token del keyring).
    También actualiza el .env para activar el perfil como método por defecto.

    Flujo recomendado (una sola vez):
        1. arcgis_auth_connect(method="oauth", url="...", client_id="...")  ← abre browser
        2. arcgis_auth_save_profile(profile_name="arcgis-mcp")             ← guarda para siempre

    profile_name: nombre del perfil en el keyring (default "arcgis-mcp").
    """
    try:
        env_path = save_session_as_profile(profile_name)
        return {
            "status": "ok",
            "profile_saved": profile_name,
            "env_updated": env_path,
            "note": (
                f"Perfil '{profile_name}' guardado en Windows Credential Manager. "
                "El servidor reconectará automáticamente desde ahora. "
                "Reiniciá el IDE para aplicar el cambio en el .env."
            ),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


