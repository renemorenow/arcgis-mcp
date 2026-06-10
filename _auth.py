from __future__ import annotations

import inspect
import json
import os
import sys
from enum import Enum
from typing import Any, Optional

from arcgis.gis import GIS
from arcgis.features import FeatureLayer, FeatureLayerCollection, FeatureSet
from arcgis.features import FeatureCollection
from arcgis.geoprocessing import import_toolbox
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
from dotenv import load_dotenv
load_dotenv()

ARCGIS_URL = os.environ.get("ARCGIS_URL")
ARCGIS_USER = os.environ.get("ARCGIS_USER")
ARCGIS_PASS = os.environ.get("ARCGIS_PASS")
ARCGIS_API_KEY = os.environ.get("ARCGIS_API_KEY")
ARCGIS_PROFILE = os.environ.get("ARCGIS_PROFILE")
ARCGIS_TOKEN = os.environ.get("ARCGIS_TOKEN")
ARCGIS_CLIENT_ID = os.environ.get("ARCGIS_CLIENT_ID")  # Para OAuth2
ARCGIS_USE_OAUTH = os.environ.get("ARCGIS_USE_OAUTH", "false").lower() == "true"
WRITE_ENABLED = os.environ.get("ARCGIS_WRITE_ENABLED", "false").lower() == "true"

# Entra ID (Azure AD) — solo para modo SSE compartido con la organización
# Registrar una App en Entra ID y volcar los valores aquí o en .env
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")       # ej. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AZURE_CLIENT_ID_MCP = os.environ.get("AZURE_CLIENT_ID_MCP", "")  # App Registration del MCP server
AZURE_AUDIENCE = os.environ.get("AZURE_AUDIENCE", AZURE_CLIENT_ID_MCP or "")  # default = client_id

MIN_ENTERPRISE_FOR_API_KEY = (11, 4)

_gis: Optional[GIS] = None


class Platform(str, Enum):
    ONLINE = "online"
    ENTERPRISE = "enterprise"


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #
def _parse_version(value) -> Optional[tuple]:
    if not value:
        return None
    try:
        return tuple(int(p) for p in str(value).split(".")[:2])
    except ValueError:
        return None


def get_gis() -> GIS:
    """Crea (y cachea) el GIS eligiendo el método de auth disponible."""
    global _gis
    if _gis is not None:
        return _gis
    
    # 1. Intentar conexión activa de ArcGIS Pro
    try:
        print("[INFO] Intentando conectar con sesión activa de ArcGIS Pro...", file=sys.stderr)
        _gis = GIS("Pro")
        if _gis is not None:
            print(f"[OK] Conectado a ArcGIS Pro como: {_gis.users.me.username if _gis.users.me else 'usuario Pro'}", file=sys.stderr)
            return _gis
    except Exception as e:
        print(f"[INFO] No hay sesión Pro activa o no se pudo conectar: {e}", file=sys.stderr)
        pass
    
    # 2. OAuth2 interactivo (abre navegador para que el usuario se autentique)
    if ARCGIS_USE_OAUTH:
        print("[INFO] Iniciando autenticación OAuth2 en navegador...", file=sys.stderr)
        portal_url = ARCGIS_URL or "https://www.arcgis.com"
        is_agol = "arcgis.com" in portal_url.lower()
        if not ARCGIS_CLIENT_ID and not is_agol:
            raise RuntimeError(
                "OAuth2 con ArcGIS Enterprise requiere ARCGIS_CLIENT_ID. "
                "Registrá una aplicación en tu portal y configurá esa variable."
            )
        try:
            if ARCGIS_CLIENT_ID:
                # OAuth2 con client_id personalizado (Enterprise o AGOL)
                _gis = GIS(portal_url, client_id=ARCGIS_CLIENT_ID)
            else:
                # OAuth2 solo para ArcGIS Online (client_id propio de AGOL)
                _gis = GIS(portal_url, client_id='arcgisonline')
            
            if _gis is not None:
                print(f"[OK] Autenticación OAuth2 exitosa: {_gis.users.me.username if _gis.users.me else 'usuario OAuth'}", file=sys.stderr)
                return _gis
        except Exception as e:
            print(f"[ERROR] Fallo en OAuth2: {e}", file=sys.stderr)
            raise RuntimeError(f"Error en autenticación OAuth2: {e}")
    
    # 3. Perfil nombrado (más seguro)
    if ARCGIS_PROFILE:
        print(f"[INFO] Usando perfil: {ARCGIS_PROFILE}", file=sys.stderr)
        _gis = GIS(profile=ARCGIS_PROFILE)
        print(f"[OK] Conectado con perfil: {_gis.users.me.username if _gis.users.me else 'usuario perfil'}", file=sys.stderr)
        return _gis
    
    # 4. API Key
    if ARCGIS_API_KEY and ARCGIS_URL:
        print(f"[INFO] Usando API Key para: {ARCGIS_URL}", file=sys.stderr)
        _gis = GIS(ARCGIS_URL, api_key=ARCGIS_API_KEY)
        _warn_if_apikey_unsupported(_gis)
        print("[OK] Conectado con API Key", file=sys.stderr)
        return _gis
    
    # 5. Token crudo
    if ARCGIS_TOKEN and ARCGIS_URL:
        print(f"[INFO] Usando token para: {ARCGIS_URL}", file=sys.stderr)
        _gis = GIS(ARCGIS_URL, token=ARCGIS_TOKEN)
        print("[OK] Conectado con token", file=sys.stderr)
        return _gis
    
    # 6. Usuario/contraseña desde .env
    if all([ARCGIS_URL, ARCGIS_USER, ARCGIS_PASS]):
        print(f"[INFO] Autenticando como {ARCGIS_USER} en {ARCGIS_URL}", file=sys.stderr)
        _gis = GIS(ARCGIS_URL, ARCGIS_USER, ARCGIS_PASS)
        print(f"[OK] Conectado como: {ARCGIS_USER}", file=sys.stderr)
        return _gis
    
    raise RuntimeError(
        "No se pudo conectar a ArcGIS. Opciones disponibles:\n"
        "  1. ArcGIS Pro activo (automático)\n"
        "  2. OAuth2: ARCGIS_USE_OAUTH=true (abre navegador)\n"
        "  3. Perfil: ARCGIS_PROFILE=nombre_perfil\n"
        "  4. API Key: ARCGIS_URL + ARCGIS_API_KEY\n"
        "  5. Token: ARCGIS_URL + ARCGIS_TOKEN\n"
        "  6. Usuario/Pass: ARCGIS_URL + ARCGIS_USER + ARCGIS_PASS"
    )


def reset_gis() -> None:
    """Descarta la sesión GIS cacheada (permite cambiar método de auth)."""
    global _gis
    _gis = None


def connect_with_method(
    method: str,
    url: str | None = None,
    client_id: str | None = None,
    profile: str | None = None,
) -> GIS:
    """Conecta usando un método específico, omitiendo la cadena automática.

    Parámetros sensibles (api_key, token, password) se leen del entorno / .env.
    """
    global _gis
    _gis = None  # descarta sesión anterior

    portal = url or ARCGIS_URL or "https://www.arcgis.com"

    if method == "pro":
        print("[INFO] Conectando con sesión activa de ArcGIS Pro...", file=sys.stderr)
        _gis = GIS("Pro")

    elif method == "oauth":
        cid = client_id or ARCGIS_CLIENT_ID
        is_agol = "arcgis.com" in portal.lower()
        if not cid and not is_agol:
            raise ValueError(
                "OAuth2 con Enterprise requiere client_id. "
                "Pasalo como parámetro o configurá ARCGIS_CLIENT_ID en .env."
            )
        print(f"[INFO] Abriendo navegador para OAuth2 en {portal}...", file=sys.stderr)
        _gis = GIS(portal, client_id=cid or "arcgisonline")

    elif method == "apikey":
        key = ARCGIS_API_KEY
        if not key:
            raise ValueError("ARCGIS_API_KEY no está configurada en .env")
        print(f"[INFO] Conectando con API Key a {portal}...", file=sys.stderr)
        _gis = GIS(portal, api_key=key)

    elif method == "profile":
        p = profile or ARCGIS_PROFILE
        if not p:
            raise ValueError(
                "Indicá el nombre del perfil como parámetro o configurá ARCGIS_PROFILE en .env."
            )
        print(f"[INFO] Conectando con perfil '{p}'...", file=sys.stderr)
        _gis = GIS(profile=p)

    elif method == "token":
        tok = ARCGIS_TOKEN
        if not tok:
            raise ValueError("ARCGIS_TOKEN no está configurado en .env")
        print(f"[INFO] Conectando con token a {portal}...", file=sys.stderr)
        _gis = GIS(portal, token=tok)

    elif method == "userpass":
        u = ARCGIS_USER
        p = ARCGIS_PASS
        if not u or not p:
            raise ValueError(
                "ARCGIS_USER y ARCGIS_PASS deben estar configurados en .env. "
                "No se aceptan como parámetros del tool por seguridad."
            )
        print(f"[INFO] Conectando como '{u}' a {portal}...", file=sys.stderr)
        _gis = GIS(portal, u, p)

    else:
        raise ValueError(
            f"Método '{method}' no reconocido. "
            "Opciones: pro | oauth | apikey | profile | token | userpass"
        )

    username = _gis.users.me.username if _gis.users.me else "app/token"
    print(f"[OK] Conectado con método '{method}': {username}", file=sys.stderr)
    return _gis


def save_session_as_profile(profile_name: str) -> str:
    """Guarda la sesión GIS activa como perfil nombrado en el keyring del SO.

    Escribe también ARCGIS_PROFILE en el .env para que el siguiente arranque
    reconecte automáticamente sin abrir el navegador.

    Retorna la ruta del .env actualizado.
    """
    global _gis
    if _gis is None:
        raise RuntimeError("No hay sesión activa. Conectate primero con auth_connect.")

    # Guardar en Windows Credential Manager / OS keyring
    _gis.save(profile_name=profile_name, overwrite=True)
    print(f"[OK] Sesión guardada como perfil '{profile_name}' en el keyring.", file=sys.stderr)

    # Actualizar el .env para usar el perfil en el próximo arranque
    env_path = _find_env_file()
    _set_env_value(env_path, "ARCGIS_PROFILE", profile_name)
    _set_env_value(env_path, "ARCGIS_USE_OAUTH", "false")  # ya no necesita OAuth
    print(f"[OK] .env actualizado: ARCGIS_PROFILE={profile_name}", file=sys.stderr)
    return env_path


def _find_env_file() -> str:
    """Localiza el .env junto al script principal."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, ".env")


def _set_env_value(env_path: str, key: str, value: str) -> None:
    """Escribe o actualiza una variable en el .env sin tocar el resto."""
    lines: list[str] = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def detect_platform(gis: GIS) -> Platform:
    return Platform.ENTERPRISE if gis.properties.get("isPortal") else Platform.ONLINE


def _warn_if_apikey_unsupported(gis: GIS) -> None:
    if detect_platform(gis) is not Platform.ENTERPRISE:
        return
    ver = _parse_version(gis.properties.get("currentVersion"))
    if ver and ver < MIN_ENTERPRISE_FOR_API_KEY:
        print(
            f"[WARN] API key no soportada en Enterprise {ver}. "
            f"Requiere {MIN_ENTERPRISE_FOR_API_KEY}. Usa ARCGIS_PROFILE.",
            file=sys.stderr,
        )


def _require_write() -> None:
    if not WRITE_ENABLED:
        raise PermissionError(
            "Escritura deshabilitada. Activa ARCGIS_WRITE_ENABLED=true."
        )


def _require_enterprise(gis: GIS) -> None:
    if detect_platform(gis) is not Platform.ENTERPRISE:
        raise RuntimeError("Solo disponible en ArcGIS Enterprise.")


def _resolve_layer(ref: str, layer_index: int = 0) -> FeatureLayer:
    """Resuelve URL de servicio o item ID a un FeatureLayer.

    - Si 'ref' empieza con http(s)  -> FeatureLayer directo.
    - Si no                         -> asume item ID, toma layers[layer_index].
    """
    gis = get_gis()
    if ref.startswith("http"):
        return FeatureLayer(ref, gis=gis)
    item = gis.content.get(ref)
    if item is None:
        raise ValueError(f"Item no encontrado: {ref}")
    layers = item.layers
    if not layers:
        raise ValueError(f"El item {ref} no tiene layers.")
    if layer_index >= len(layers):
        raise ValueError(
            f"layer_index={layer_index} fuera de rango (tiene {len(layers)} layers)."
        )
    return layers[layer_index]


def _safe_result(obj: Any) -> Any:
    """Intenta convertir un resultado de arcgis a algo JSON-serializable."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return [_safe_result(i) for i in obj]
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        try:
            return _safe_result(obj.to_dict())
        except Exception:
            pass
    if hasattr(obj, "url"):
        return {"type": type(obj).__name__, "url": obj.url}
    try:
        normalized = json.loads(json.dumps(obj, default=str))
        if isinstance(normalized, str):
            text = normalized.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    return json.loads(text)
                except Exception:
                    pass
        return normalized
    except Exception:
        return str(obj)


