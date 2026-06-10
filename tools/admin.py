from __future__ import annotations
from typing import Any

from _server import mcp
from _auth import (
    get_gis, detect_platform, _require_write, _require_enterprise, _safe_result,
)

# =========================================================================== #
#   ADMINISTRACIÓN BÁSICA
# =========================================================================== #
@mcp.tool()
def user_list(query: str = "", max_users: int = 50) -> list:
    """Lista usuarios de la organización."""
    gis = get_gis()
    users = gis.users.search(query=query or "*", max_users=max_users)
    return [{"username": u.username, "role": getattr(u, "role", None), "email": u.email} for u in users]


@mcp.tool()
def group_list(query: str = "", max_groups: int = 50) -> list:
    """Lista grupos de la organización."""
    gis = get_gis()
    groups = gis.groups.search(query=query or "*", max_groups=max_groups)
    return [{"id": g.id, "title": g.title, "owner": g.owner} for g in groups]


@mcp.tool()
def user_create(
    username: str,
    password: str,
    firstname: str,
    lastname: str,
    email: str,
    role: str = "org_user",
    dry_run: bool = True,
) -> dict:
    """Crea un usuario built-in. ESCRITURA con dry_run=True por defecto."""
    _require_write()
    gis = get_gis()
    if dry_run:
        return {"dry_run": True, "would_create": username, "role": role}
    user = gis.users.create(
        username=username, password=password,
        firstname=firstname, lastname=lastname,
        email=email, role=role,
    )
    return {"created": user.username if user else None}


# =========================================================================== #
#   arcgis.gis.admin.Logs — Logs del portal Enterprise  (prefijo portal_logs_)
#
#   Acceso: gis.admin.logs → Logs
#   API:  .query(start_time, end_time, level, query_filter, page_size,
#                federated_servers)
#         .clean()
#         .settings  (get/set)
#
#   NOTA: Distinto de server_logs_query() que opera sobre ArcGIS Server.
#         portal_logs_* opera sobre el portal Enterprise (sharing, admin, etc.)
# =========================================================================== #

@mcp.tool()
def portal_logs_query(
    start_time: str = "",
    end_time: str = "",
    level: str = "WARNING",
    query_filter: str = "*",
    page_size: int = 500,
    federated_servers: str = "",
) -> dict:
    """Consulta y filtra los logs del portal ArcGIS Enterprise.

    Equivale a gis.admin.logs.query(). Solo Enterprise.

    start_time: fecha/hora de inicio ISO 8601. Vacío = últimas 24 horas.
                Formatos aceptados:
                  '2025-02-01T15:18:22'  (string ISO)
                  timestamp en ms desde epoch (como string, ej: '1738396800000')
    end_time: fecha/hora de fin ISO 8601. Vacío = ahora.
    level: nivel mínimo de severidad.
        Valores: 'OFF', 'SEVERE', 'WARNING', 'INFO', 'FINE', 'VERBOSE', 'DEBUG'.
        Default: 'WARNING'
    query_filter: filtro en formato JSON string (objeto) o '*' para todo.
        Claves soportadas:
          'users'  — lista de usuarios. Ej: '{"users": ["gis_admin"]}'
          'codes'  — lista de códigos o rangos. Ej: '{"codes": ["204000-205999", 212015]}'
          'source' — lista de fuentes: 'SHARING', 'PORTAL_ADMIN', 'PORTAL'
          Ejemplo combinado: '{"codes": [200011], "users": ["admin"], "source": ["SHARING"]}'
    page_size: número máximo de registros a retornar. Default: 500.
    federated_servers: incluir logs de servidores federados.
        '' = excluir (default), 'all' = todos, URL específica = solo ese servidor.

    Retorna: dict con hasMore, startTime, endTime y logMessages (lista de eventos).
    """
    import datetime, json
    gis = get_gis()
    _require_enterprise(gis)

    # start_time es obligatorio en la API real — default a 24h atrás
    if not start_time:
        dt_start = datetime.datetime.now() - datetime.timedelta(hours=24)
        start_time_val: Any = dt_start
    else:
        start_time_val = start_time

    kwargs: dict[str, Any] = {
        "start_time": start_time_val,
        "level": level,
        "page_size": page_size,
    }

    if end_time:
        kwargs["end_time"] = end_time

    if query_filter and query_filter != "*":
        try:
            kwargs["query_filter"] = json.loads(query_filter)
        except (json.JSONDecodeError, ValueError):
            kwargs["query_filter"] = query_filter
    else:
        kwargs["query_filter"] = "*"

    if federated_servers:
        kwargs["federated_servers"] = federated_servers

    return gis.admin.logs.query(**kwargs)


@mcp.tool()
def portal_logs_clean(dry_run: bool = True) -> dict:
    """Elimina todos los archivos de log del portal Enterprise. IRREVERSIBLE.

    Libera espacio en disco. Los logs no pueden recuperarse tras esta operación.
    Solo Enterprise, requiere credenciales de administrador del portal.

    dry_run: True por defecto — simula la operación sin ejecutarla.

    Equivale a gis.admin.logs.clean().
    Retorna: True si la limpieza fue exitosa.
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)

    if dry_run:
        return {
            "dry_run": True,
            "action": "would_clean_portal_logs",
            "warning": "Esta operación elimina TODOS los logs del portal. IRREVERSIBLE.",
        }

    result = gis.admin.logs.clean()
    return {"success": result, "action": "portal_logs_cleaned"}


@mcp.tool()
def portal_logs_settings() -> dict:
    """Lee la configuración actual de logs del portal Enterprise.

    Retorna: logDir, logLevel, maxErrorReportsCount, maxLogFileAge,
             usageMeteringEnabled — y cualquier campo adicional configurado.

    Solo Enterprise. Equivale a gis.admin.logs.settings (getter).
    """
    gis = get_gis()
    _require_enterprise(gis)
    return dict(gis.admin.logs.settings)


@mcp.tool()
def portal_logs_settings_update(
    log_level: str = "",
    max_log_file_age: int = 0,
    max_error_reports_count: int = 0,
    usage_metering_enabled: bool | None = None,
    dry_run: bool = True,
) -> dict:
    """Actualiza la configuración de logs del portal Enterprise. OPERACIÓN DE ESCRITURA.

    Solo los parámetros con valor distinto del default se aplican.
    Los demás se conservan desde la configuración actual.

    log_level: nuevo nivel de log.
        Valores: 'OFF', 'SEVERE', 'WARNING', 'INFO', 'FINE', 'VERBOSE', 'DEBUG'.
        '' = sin cambio.
    max_log_file_age: días máximos de retención de logs (0 = sin cambio).
        Ejemplo: 90 = conservar 90 días.
    max_error_reports_count: número máximo de reportes de error (0 = sin cambio).
    usage_metering_enabled: True/False para habilitar/deshabilitar métricas de uso.
        None = sin cambio.
    dry_run: True por defecto — muestra qué cambiaría sin aplicar.

    Equivale a gis.admin.logs.settings = {...} (setter).
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)

    current = dict(gis.admin.logs.settings)
    new_settings = dict(current)  # copy

    if log_level:
        new_settings["logLevel"] = log_level
    if max_log_file_age > 0:
        new_settings["maxLogFileAge"] = max_log_file_age
    if max_error_reports_count > 0:
        new_settings["maxErrorReportsCount"] = max_error_reports_count
    if usage_metering_enabled is not None:
        new_settings["usageMeteringEnabled"] = usage_metering_enabled

    if dry_run:
        return {
            "dry_run": True,
            "current_settings": current,
            "proposed_settings": new_settings,
            "changes": {k: v for k, v in new_settings.items() if current.get(k) != v},
        }

    gis.admin.logs.settings = new_settings
    return {"success": True, "applied_settings": new_settings}


# =========================================================================== #
#   ADMINISTRACIÓN ENTERPRISE ESPECÍFICA (desde tools/)
# =========================================================================== #
@mcp.tool()
def admin_licenses() -> list:
    """Consulta disponibilidad de licencias de ArcGIS Pro."""
    gis = get_gis()
    _require_enterprise(gis)
    licencias = gis.admin.license.all()
    return [{"name": l["name"], "available": l["available"]} for l in licencias if "Pro" in l["name"]]


@mcp.tool()
def admin_services_health() -> list:
    """Identifica servicios de mapas o geoprocesamiento detenidos."""
    gis = get_gis()
    _require_enterprise(gis)
    servers = gis.admin.servers.list()
    result = []
    for s in servers:
        for svc in s.services.list():
            if svc.status != 'STARTED':
                result.append({
                    "server": s.url, 
                    "service": svc.serviceName, 
                    "status": svc.status
                })
    return result


@mcp.tool()
def admin_servers_list() -> list:
    """Muestra URLs de los servidores federados."""
    gis = get_gis()
    _require_enterprise(gis)
    return [s.url for s in gis.admin.servers.list()]



# =========================================================================== #
#   💳  CRÉDITOS Y USO — ArcGIS Online / Enterprise  (prefijo org_)
# =========================================================================== #

@mcp.tool()
def org_credits() -> dict:
    """Consulta el saldo de créditos disponibles de la organización (ArcGIS Online).

    Retorna: total de créditos disponibles, créditos consumidos en el período,
    alertas configuradas y créditos asignados por usuario si aplica.
    Solo disponible en ArcGIS Online.

    Equivale a gis.admin.credits.credits (AGOL).
    """
    gis = get_gis()
    try:
        credits_info = gis.admin.credits.credits
        return _safe_result(credits_info)
    except AttributeError:
        platform = detect_platform(gis).value
        return {"error": f"Créditos no disponibles en plataforma '{platform}'. Este endpoint es para ArcGIS Online."}


@mcp.tool()
def org_usage(
    period: str = "last30Days",
    report_type: str = "credits",
    user_filter: str = "",
    app_filter: str = "",
) -> dict:
    """Consulta estadísticas de uso de la organización por período.

    period: período de consulta. Valores:
        'today', 'last7Days', 'last14Days', 'last30Days', 'last60Days', 'last90Days'
    report_type: tipo de reporte. Valores:
        'credits' — consumo de créditos
        'requests' — número de solicitudes REST
        'storageUsage' — uso de almacenamiento
        'licenseUsage' — uso de licencias
    user_filter: filtrar por username específico. Vacío = toda la organización.
    app_filter: filtrar por nombre de aplicación. Vacío = todas.

    Equivale a gis.admin.usage_reports.generate(report_type=..., period=...).
    """
    gis = get_gis()
    try:
        kwargs: dict[str, Any] = {
            "report_type": report_type,
            "period": period,
        }
        if user_filter:
            kwargs["user"] = user_filter
        if app_filter:
            kwargs["app"] = app_filter

        result = gis.admin.usage_reports.generate(**kwargs)
        return _safe_result(result)
    except Exception as e:
        return {"error": str(e), "period": period, "report_type": report_type}



# =========================================================================== #
#   🔧  ADMIN PORTAL EXTENDED — arcgis.gis.admin  (extensión de sección existente)
# =========================================================================== #

@mcp.tool()
def admin_org_settings() -> dict:
    """Retorna la configuración general de la organización del portal.

    Retorna: nombre, descripción, idioma, región, unidades, URL del portal,
    configuración de thumbnail, acceso por defecto, y otras propiedades admin.
    Disponible en ArcGIS Online y Enterprise.

    Equivale a gis.properties con foco en campos de configuración organizacional.
    """
    gis = get_gis()
    props = gis.properties
    keys = [
        "name", "description", "culture", "region", "units", "urlKey",
        "customBaseUrl", "defaultExtent", "defaultBasemap",
        "allowPublicPortal", "access", "supportsHostedServices",
        "canSignInArcGIS", "canSignInIDP", "helpBase",
        "portalMode", "isPortal",
    ]
    result = {}
    for k in keys:
        val = props.get(k)
        if val is not None:
            result[k] = val
    return result


@mcp.tool()
def admin_system_info() -> dict:
    """Retorna información del sistema del servidor ArcGIS Enterprise.

    Retorna: versión del software, estado de los componentes (data store,
    hosting server, etc.), uso de CPU/RAM/disco si está disponible.
    Solo Enterprise. Requiere credenciales de administrador del portal.

    Equivale a gis.admin.system.info.
    """
    gis = get_gis()
    _require_enterprise(gis)
    try:
        info = gis.admin.system.info
        return _safe_result(info)
    except Exception as e:
        return {"error": str(e), "note": "Requiere credenciales de administrador del portal Enterprise."}


@mcp.tool()
def admin_reindex(
    mode: str = "full_search",
    dry_run: bool = True,
) -> dict:
    """Reindexar el contenido del portal ArcGIS Enterprise. OPERACIÓN DE ESCRITURA.

    mode: tipo de reindexación.
        'full_search' — reindexar todos los items para búsqueda.
        'incremental' — solo items modificados desde última indexación.
    dry_run: True por defecto.

    ⚠️ En portales grandes puede demorar varios minutos. No interrumpir.
    Solo Enterprise. Requiere rol de administrador del portal.
    Equivale a gis.admin.reindex(mode=mode).
    """
    _require_write()
    gis = get_gis()
    _require_enterprise(gis)

    if dry_run:
        return {
            "dry_run": True,
            "action": f"would_reindex",
            "mode": mode,
            "warning": "En portales grandes puede demorar varios minutos. No interrumpir durante el proceso.",
        }

    try:
        result = gis.admin.reindex(mode=mode)
        return {"success": True, "mode": mode, "result": _safe_result(result)}
    except Exception as e:
        return {"error": str(e), "mode": mode}


