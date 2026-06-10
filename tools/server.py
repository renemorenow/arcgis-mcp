from __future__ import annotations
from typing import Any

import concurrent.futures

from _server import mcp
from _auth import (
    get_gis, _require_write, _require_enterprise, _safe_result,
)

# =========================================================================== #
#   arcgis.gis.server — Administración de ArcGIS Server  (prefijo server_)
#
#   Acceso: gis.admin.servers → ServerManager
#           server = gis.admin.servers.get(role="HOSTING_SERVER")
#           server.services → ServiceManager
#           server.logs     → LogManager
#           server.machines → MachineManager
# =========================================================================== #

def _get_server(role: str = "HOSTING_SERVER"):
    """Helper: obtiene el primer server ArcGIS federado.

    Intenta primero filtrar por rol; si no hay coincidencia (servidores con
    role UNKNOWN / federados genéricos) devuelve el primero disponible.
    """
    gis = get_gis()
    _require_enterprise(gis)
    all_servers = gis.admin.servers.list()
    if not all_servers:
        raise ValueError("No hay ArcGIS Servers federados en este portal.")
    # Intentar match por rol
    role_upper = role.upper()
    matched = [
        s for s in all_servers
        if str(getattr(s, "serverRole", "") or "").upper() == role_upper
        or str((s.properties if hasattr(s, "properties") else {}).get("serverRole", "")).upper() == role_upper
    ]
    return matched[0] if matched else all_servers[0]


def _get_service(server, service_name: str, folder: str = ""):
    """Helper: busca un servicio por nombre en un server, opcionalmente en una carpeta.

    ServiceManager no expone un método .get(); hay que iterar .list().
    """
    target_folder = folder or None
    svcs = server.services.list(folder=target_folder)
    for svc in svcs:
        sp = svc.properties if hasattr(svc, "properties") else {}
        if sp.get("serviceName", "") == service_name:
            return svc
    return None


@mcp.tool()
def server_list() -> list:
    """Lista todos los ArcGIS Servers federados en el Enterprise.

    Solo Enterprise. Accede a gis.admin.servers.list().
    Retorna: nombre, URL, role, function y estado de cada servidor.
    Usar antes de cualquier operación de administración de servidor.
    """
    gis = get_gis()
    _require_enterprise(gis)
    result = []
    for s in gis.admin.servers.list():
        try:
            result.append({
                "url": s.url,
                "role": getattr(s, "serverRole", None),
                "function": getattr(s, "serverFunction", None),
                "id": getattr(s, "id", None),
                "admin_url": getattr(s, "adminUrl", None),
            })
        except Exception:
            result.append({"url": getattr(s, "url", "unknown")})
    return result


@mcp.tool()
def server_services_list(
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
) -> list:
    """Lista los servicios disponibles en un ArcGIS Server.

    folder: carpeta del server (vacío = raíz). Ejemplo: 'Utilities', 'System'.
    server_role: rol del servidor a consultar.
        Valores: 'HOSTING_SERVER', 'FEDERATED_SERVER'.

    Retorna: nombre, tipo, descripción y estado de cada servicio.
    Equivalente a Server.services.list(folder).
    """
    server = _get_server(server_role)
    services = server.services.list(folder=folder or None)
    result = []
    for svc in services:
        try:
            result.append({
                "name": svc.properties.get("serviceName"),
                "type": svc.properties.get("type"),
                "description": svc.properties.get("description", ""),
                "capabilities": svc.properties.get("capabilities"),
                "folder": folder or "/",
                "url": svc.url,
            })
        except Exception as e:
            result.append({"error": str(e)})
    return result


@mcp.tool()
def server_service_status(
    service_name: str,
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
) -> dict:
    """Obtiene el estado (STARTED/STOPPED) y estadísticas de un servicio.

    service_name: nombre del servicio. Ejemplo: 'MyService'.
    folder: carpeta del servidor donde está el servicio.
    server_role: rol del servidor donde está el servicio.

    Retorna: configuredState, realTimeState, y estadísticas de uso.
    Equivalente a Service.status + Service.statistics.
    """
    server = _get_server(server_role)
    svc = _get_service(server, service_name, folder)
    if svc is None:
        raise ValueError(f"Servicio no encontrado: '{service_name}' en folder='{folder}'")
    return {
        "service_name": service_name,
        "folder": folder or "/",
        "status": svc.status,
        "statistics": svc.statistics,
        "url": svc.url,
    }


@mcp.tool()
def server_service_start(
    service_name: str,
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
    dry_run: bool = True,
) -> dict:
    """Inicia un servicio detenido en ArcGIS Server. OPERACIÓN DE ESCRITURA.

    service_name: nombre del servicio.
    folder: carpeta del servidor.
    server_role: rol del servidor.
    dry_run: True por defecto — muestra el estado actual sin iniciar.

    Equivalente a Service.start().
    """
    _require_write()
    server = _get_server(server_role)
    svc = _get_service(server, service_name, folder)
    if svc is None:
        raise ValueError(f"Servicio no encontrado: '{service_name}'")

    if dry_run:
        return {
            "dry_run": True,
            "service_name": service_name,
            "current_status": svc.status,
            "action": "would_start",
        }

    result = svc.start()
    return {"success": result, "service_name": service_name, "action": "started"}


@mcp.tool()
def server_service_stop(
    service_name: str,
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
    dry_run: bool = True,
) -> dict:
    """Detiene un servicio en ArcGIS Server. OPERACIÓN DE ESCRITURA.

    service_name: nombre del servicio.
    folder: carpeta del servidor.
    server_role: rol del servidor.
    dry_run: True por defecto — muestra el estado actual sin detener.

    Equivalente a Service.stop().
    """
    _require_write()
    server = _get_server(server_role)
    svc = _get_service(server, service_name, folder)
    if svc is None:
        raise ValueError(f"Servicio no encontrado: '{service_name}' (folder='{folder}')")

    if dry_run:
        return {
            "dry_run": True,
            "service_name": service_name,
            "current_status": svc.status,
            "action": "would_stop",
        }

    result = svc.stop()
    return {"success": result, "service_name": service_name, "action": "stopped"}


@mcp.tool()
def server_service_restart(
    service_name: str,
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
    dry_run: bool = True,
) -> dict:
    """Reinicia un servicio en ArcGIS Server. OPERACIÓN DE ESCRITURA.

    service_name: nombre del servicio.
    folder: carpeta del servidor.
    server_role: rol del servidor.
    dry_run: True por defecto — muestra el estado actual sin reiniciar.

    Equivalente a Service.restart(). Útil tras cambiar configuración.
    """
    _require_write()
    server = _get_server(server_role)
    svc = _get_service(server, service_name, folder)
    if svc is None:
        raise ValueError(f"Servicio no encontrado: '{service_name}' (folder='{folder}')")

    if dry_run:
        return {
            "dry_run": True,
            "service_name": service_name,
            "current_status": svc.status,
            "action": "would_restart",
        }

    result = svc.restart()
    return {"success": result, "service_name": service_name, "action": "restarted"}


@mcp.tool()
def server_logs_query(
    start_time: str = "",
    end_time: str = "",
    log_level: str = "WARNING",
    services: str = "*",
    machines: str = "*",
    num_messages: int = 100,
    server_role: str = "HOSTING_SERVER",
) -> list:
    """Consulta los logs de ArcGIS Server con filtros.

    start_time: fecha/hora de inicio ISO 8601 (vacío = últimas 24h).
                Ejemplo: '2024-01-15T08:00:00'
    end_time: fecha/hora de fin ISO 8601 (vacío = ahora).
    log_level: nivel mínimo de log.
        Valores: 'SEVERE', 'WARNING', 'INFO', 'FINE', 'VERBOSE', 'DEBUG'.
    services: filtro de servicios. '*' = todos. Ejemplo: 'MyService.MapServer'.
    machines: filtro de máquinas. '*' = todas.
    num_messages: número máximo de mensajes a retornar.
    server_role: rol del servidor a consultar.

    Retorna: timestamp, tipo, mensaje, servicio, máquina y código de cada log.
    Equivalente a Server.logs.query().
    """
    server = _get_server(server_role)
    query_kwargs: dict[str, Any] = {
        "level": log_level,
        "num": num_messages,
    }
    if start_time:
        query_kwargs["start_time"] = start_time
    if end_time:
        query_kwargs["end_time"] = end_time
    if services != "*":
        query_kwargs["services"] = services
    if machines != "*":
        query_kwargs["machines"] = machines

    result = server.logs.query(**query_kwargs)

    # LogManager.query() retorna un dict con 'logMessages'
    messages = result.get("logMessages", result) if isinstance(result, dict) else result
    return messages if isinstance(messages, list) else [messages]


@mcp.tool()
def server_logs_clean(
    server_role: str = "HOSTING_SERVER",
    dry_run: bool = True,
) -> dict:
    """Limpia todos los logs del ArcGIS Server. OPERACIÓN DE ESCRITURA.

    server_role: rol del servidor cuyos logs se limpiarán.
    dry_run: True por defecto — simula sin limpiar.

    Equivalente a Server.logs.clean(). IRREVERSIBLE.
    """
    _require_write()
    server = _get_server(server_role)

    if dry_run:
        return {
            "dry_run": True,
            "server_url": server.url,
            "action": "would_clean_logs",
            "warning": "Esta operación elimina TODOS los logs. IRREVERSIBLE.",
        }

    result = server.logs.clean()
    return _safe_result(result)


@mcp.tool()
def server_machines_list(server_role: str = "HOSTING_SERVER") -> list:
    """Lista las máquinas registradas en el ArcGIS Server site.

    server_role: rol del servidor a consultar.

    Retorna: nombre, estado, plataforma, URL de admin de cada máquina.
    Equivalente a Server.machines.list().
    Útil para verificar el estado del clúster y detectar máquinas caídas.
    """
    server = _get_server(server_role)
    machines = server.machines.list()
    result = []
    for m in machines:
        try:
            result.append({
                "name": m.properties.get("machineName"),
                "status": m.status,
                "platform": m.properties.get("platform"),
                "url": m.url,
                "ssl_certs": list((m.ssl_certificates or {}).keys()),
            })
        except Exception as e:
            result.append({"error": str(e), "url": getattr(m, "url", "unknown")})
    return result


@mcp.tool()
def server_machine_hardware(
    machine_name: str,
    server_role: str = "HOSTING_SERVER",
) -> dict:
    """Obtiene información de hardware de una máquina del ArcGIS Server.

    machine_name: nombre de la máquina (usar server_machines_list() para obtenerlo).
    server_role: rol del servidor.

    Retorna: CPU, RAM, disco, SO, arquitectura — se actualiza al reiniciar.
    Equivalente a Machine.hardware.
    """
    server = _get_server(server_role)
    machine = server.machines.get(machine_name)
    if machine is None:
        raise ValueError(f"Máquina no encontrada: '{machine_name}'")
    return machine.hardware


@mcp.tool()
def server_service_manifest(
    service_name: str,
    folder: str = "",
    file_type: str = "json",
    server_role: str = "HOSTING_SERVER",
) -> str:
    """Obtiene el manifest de un servicio (fuentes de datos y recursos).

    service_name: nombre del servicio.
    folder: carpeta del servidor.
    file_type: formato de salida — 'json' o 'xml'.
    server_role: rol del servidor.

    El manifest documenta los datos y recursos que potencian el servicio:
    bases de datos, rutas, archivos de configuración.
    Equivalente a Service.service_manifest(file_type).
    """
    server = _get_server(server_role)
    svc = _get_service(server, service_name, folder)
    if svc is None:
        raise ValueError(f"Servicio no encontrado: '{service_name}'")
    return svc.service_manifest(file_type=file_type)


@mcp.tool()
def server_services_directory_list(
    folder: str = "",
    server_role: str = "HOSTING_SERVER",
) -> list:
    """Lista servicios del Services Directory (REST endpoint público).

    folder: carpeta a listar (vacío = raíz).
    server_role: rol del servidor.

    A diferencia de server_services_list() que usa la API de admin,
    este tool accede al Services Directory REST público — retorna el tipo
    de objeto Python correspondiente (FeatureLayerCollection, Toolbox, etc.).
    Equivalente a Server.content.list(folder).
    """
    server = _get_server(server_role)
    services = server.content.list(folder=folder or None)
    result = []
    for svc in services:
        try:
            result.append({
                "name": getattr(svc, "title", None) or getattr(svc, "name", None),
                "type": type(svc).__name__,
                "url": getattr(svc, "url", None),
            })
        except Exception as e:
            result.append({"error": str(e)})
    return result


@mcp.tool()
def server_services_folders(server_role: str = "HOSTING_SERVER") -> list:
    """Lista las carpetas del Services Directory del ArcGIS Server.

    server_role: rol del servidor.
    Equivalente a Server.content.folders.
    """
    server = _get_server(server_role)
    return list(server.content.folders or [])


# ─────────────────────────────────────────────────────────────────────────────
# Hace GET autenticado a cada servicio REST y reporta si responde OK o no.
# Cubre TODOS los servidores federados (arcgis, image, etc.)
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def server_ping_all(folder: str = "", parallel: bool = True) -> list[dict]:
    """
    Verifica el estado REST de cada servicio en todos los servidores federados.

    Parámetros
    ----------
    folder  : str — filtrar por carpeta (vacío = todas)
    parallel: bool — usar ThreadPoolExecutor para velocidad (default True)

    Retorna
    -------
    Lista de dicts con: server_role, server_url, folder, service_name,
                        service_type, rest_url, status, raster_count,
                        layer_count, error
    """
    gis = get_gis()
    def _ping_service(svc_info: dict) -> dict:
        """Hace GET al endpoint REST del servicio y retorna su estado."""
        rest_url = svc_info["rest_url"]
        try:
            resp = gis._con.get(rest_url, {"f": "json"})

            if "error" in resp:
                return {**svc_info,
                        "status"      : "ERROR",
                        "raster_count": None,
                        "layer_count" : None,
                        "error"       : resp["error"].get("message", str(resp["error"]))}

            return {**svc_info,
                    "status"      : "OK",
                    "raster_count": resp.get("rasterCount"),
                    "layer_count" : resp.get("layerCount") or resp.get("numLayers"),
                    "error"       : None}

        except Exception as e:
            return {**svc_info,
                    "status"      : "UNREACHABLE",
                    "raster_count": None,
                    "layer_count" : None,
                    "error"       : str(e)}

    # ── Recopilar todos los servicios de todos los servidores ────────────────
    all_services: list[dict] = []

    for server in gis.admin.servers.list():
        role       = getattr(server, "serverRole", "UNKNOWN")
        server_url = server.url.replace("/admin", "").replace("/rest/services", "")

        try:
            folders_to_scan = server.services.folders
        except Exception:
            continue

        if folder:
            folders_to_scan = [f for f in folders_to_scan if f.lower() == folder.lower()]

        for fld in folders_to_scan:
            if fld in ("System", "Utilities"):
                continue
            try:
                services = server.services.list(folder=fld)
            except Exception:
                continue

            for svc in services:
                svc_name = svc.properties.get("serviceName") or svc.properties.get("name", "")
                svc_type = svc.properties.get("type", "")
                fld_name = svc.properties.get("folderName", fld).lstrip("/")

                # Construir URL REST según tipo
                type_suffix = {
                    "MapServer"    : "MapServer",
                    "ImageServer"  : "ImageServer",
                    "FeatureServer": "FeatureServer",
                    "GPServer"     : "GPServer",
                    "GeocodeServer": "GeocodeServer",
                }.get(svc_type, svc_type)

                rest_url = (
                    f"{server_url}/rest/services/"
                    f"{fld_name + '/' if fld_name and fld_name != '/' else ''}"
                    f"{svc_name}/{type_suffix}"
                )

                all_services.append({
                    "server_role" : role,
                    "server_url"  : server_url,
                    "folder"      : fld_name or "/",
                    "service_name": svc_name,
                    "service_type": svc_type,
                    "rest_url"    : rest_url,
                })

    # ── Ping en paralelo o secuencial ────────────────────────────────────────
    if parallel and all_services:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(_ping_service, all_services))
    else:
        results = [_ping_service(s) for s in all_services]

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Como admin_services_health pero para TODOS los servidores federados.
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def server_services_health_all() -> dict:
    """
    Retorna el estado admin (STARTED/STOPPED) de cada servicio
    en todos los servidores federados.

    Retorna
    -------
    Dict con:
      - servers    : lista de {role, url, services: [{name, folder, type, configured, realtime}]}
      - stopped    : lista de servicios detenidos
      - total      : conteo total
      - ok_count   : conteo STARTED
      - error_count: conteo STOPPED/ERROR
    """
    all_results  = []
    stopped      = []
    gis = get_gis()
    for server in gis.admin.servers.list():
        role       = getattr(server, "serverRole", "UNKNOWN")
        server_url = server.url

        server_entry = {"role": role, "url": server_url, "services": []}

        try:
            folders = server.services.folders
        except Exception:
            continue

        for fld in folders:
            if fld in ("System", "Utilities"):
                continue
            try:
                services = server.services.list(folder=fld)
            except Exception:
                continue

            for svc in services:
                try:
                    status   = svc.status
                    cfg      = status.get("configuredState", "UNKNOWN")
                    realtime = status.get("realTimeState",   "UNKNOWN")
                    name     = svc.properties.get("serviceName", "")
                    svc_type = svc.properties.get("type", "")
                    fld_name = svc.properties.get("folderName", fld).lstrip("/")

                    entry = {
                        "name"      : name,
                        "folder"    : fld_name or "/",
                        "type"      : svc_type,
                        "configured": cfg,
                        "realtime"  : realtime,
                    }
                    server_entry["services"].append(entry)

                    if realtime != "STARTED":
                        stopped.append({
                            "server_role": role,
                            "server_url" : server_url,
                            **entry,
                        })

                except Exception:
                    pass

        all_results.append(server_entry)

    total     = sum(len(s["services"]) for s in all_results)
    ok_count  = total - len(stopped)

    return {
        "servers"    : all_results,
        "stopped"    : stopped,
        "total"      : total,
        "ok_count"   : ok_count,
        "error_count": len(stopped),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lista servicios del Image Server por carpeta usando gis.admin.servers.get()
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def image_server_services_list(folder: str = "") -> list[dict]:
    """
    Lista servicios publicados en el Image Server federado.

    Parámetros
    ----------
    folder: str — carpeta a listar (vacío = todas)

    Retorna
    -------
    Lista de dicts con: folder, name, type, status, rest_url
    """
    results = []
    gis = get_gis()
    # Buscar el servidor con rol IMAGE_SERVER entre los federados
    image_server = None
    for server in gis.admin.servers.list():
        role = getattr(server, "serverRole", "")
        if "IMAGE" in role.upper():
            image_server = server
            break

    if image_server is None:
        # Fallback: buscar por URL que contenga /image/
        for server in gis.admin.servers.list():
            if "/image/" in server.url.lower() or "image" in server.url.lower():
                image_server = server
                break

    if image_server is None:
        return [{"error": "No se encontró un Image Server federado"}]

    server_base = image_server.url.replace("/admin", "")
    folders_to_scan = [folder] if folder else image_server.services.folders

    for fld in folders_to_scan:
        if fld in ("System", "Utilities"):
            continue
        try:
            services = image_server.services.list(folder=fld)
        except Exception as e:
            results.append({"folder": fld, "error": str(e)})
            continue

        for svc in services:
            name     = svc.properties.get("serviceName", "")
            svc_type = svc.properties.get("type", "")
            fld_name = svc.properties.get("folderName", fld).lstrip("/")

            try:
                status   = svc.status
                cfg      = status.get("configuredState", "UNKNOWN")
                realtime = status.get("realTimeState",   "UNKNOWN")
            except Exception:
                cfg = realtime = "UNKNOWN"

            type_suffix = {
                "ImageServer": "ImageServer",
                "MapServer"  : "MapServer",
            }.get(svc_type, svc_type)

            rest_url = (
                f"{server_base}/rest/services/"
                f"{fld_name + '/' if fld_name else ''}"
                f"{name}/{type_suffix}"
            )

            results.append({
                "folder"    : fld_name or "/",
                "name"      : name,
                "type"      : svc_type,
                "configured": cfg,
                "realtime"  : realtime,
                "rest_url"  : rest_url,
            })

    return results
