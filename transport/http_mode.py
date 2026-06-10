from __future__ import annotations

import inspect
import json
import sys
import traceback
from typing import Any

# Importar todas las funciones de tools (necesario para el dict TOOLS)
from tools.discovery import (
    whoami, gis_properties, gis_version,
    content_search, content_find_large,
)
from tools.geoprocessing import (
    gp_discover, gp_run, gp_run_async,
    gp_tool_help, gp_search_services, gp_service_info,
    gp_linear_unit, gp_data_file, gp_raster_data, gp_run_with_env,
)
from tools.admin import (
    user_list, user_create, group_list,
    portal_logs_query, portal_logs_clean, portal_logs_settings, portal_logs_settings_update,
    admin_licenses, admin_services_health, admin_servers_list,
    org_credits, org_usage,
    admin_org_settings, admin_system_info, admin_reindex,
)
from tools.items import (
    item_get, item_update, item_protect, item_unprotect,
    item_metadata, item_download, item_delete, item_move,
    item_clone, item_publish, item_export, item_share,
    item_layers, item_dependent_upon, item_dependent_to,
    item_related_items, item_reassign, item_get_data,
    item_thumbnail, item_add_comment, item_resources,
)
from tools.users_groups import (
    user_get, user_update, user_disable, user_enable,
    user_set_role, user_content,
    group_get, group_update, group_add_users, group_remove_users,
    group_content, group_members, group_create,
    share_get_access, share_set_access, share_status, share_bulk_set_access,
    share_audit_public, share_audit_by_owner,
    share_group_add, share_group_remove, share_group_list,
    share_group_replace, share_group_copy, share_group_audit,
)
from tools.features import (
    feature_get, feature_get_value, feature_update,
    fl_fields, fl_query_advanced, fl_edit, fl_delete_by_query,
    fl_calculate, fl_capabilities,
    table_query, table_edit, table_fields,
    flc_describe, flc_update_definition, flc_truncate,
    fset_from_query, fset_statistics, fset_to_geojson,
    fc_describe, fc_query, fc_to_feature_layer,
)
from tools.server import (
    server_list, server_services_list,
    server_service_status, server_service_start,
    server_service_stop, server_service_restart,
    server_logs_query, server_logs_clean,
    server_machines_list, server_machine_hardware,
    server_service_manifest, server_services_directory_list,
    server_services_folders,
)
from tools.maps import (
    webmap_get, webmap_layers, webmap_add_layer,
    webmap_remove_layer, webmap_update_layer, webmap_create,
    mil_info, mil_sublayers, mil_query,
    webscene_get, webscene_layers,
)
from tools.geo import (
    geocode, reverse_geocode, geocode_suggest, batch_geocode,
    geometry_project, geometry_buffer, geometry_area_length, geometry_simplify,
)
from tools.spatial import (
    fl_add_field, fl_delete_fields,
    fl_attachments_list, fl_attachment_add,
    fl_related_records, fl_append,
    fl_view_list, fl_create_view,
)
from tools.org import (
    webhook_list, webhook_create, webhook_delete,
    notebook_list, notebook_execute,
    enrich_countries, enrich_data_collections, enrich_areas,
)

# --------------------------------------------------------------------------- #
# MODO HTTP (FastAPI opcional)
# --------------------------------------------------------------------------- #
def run_http_server():
    """Levanta servidor FastAPI para exposición HTTP de las tools MCP."""
    from fastapi import FastAPI, Body, HTTPException
    from fastapi.responses import JSONResponse, HTMLResponse
    import uvicorn

    app = FastAPI(
        title="ArcGIS MCP",
        description="Servidor MCP unificado para ArcGIS Online / Enterprise con exposición HTTP",
        version="2.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    # Mapeo manual de funciones disponibles (las que están decoradas con @mcp.tool())
    TOOLS = {
        # Introspección
        "whoami": whoami,
        "gis_properties": gis_properties,
        "gis_version": gis_version,
        # Descubrimiento
        "content_search": content_search,
        "content_find_large": content_find_large,
        # GP Dinámico
        "gp_discover": gp_discover,
        "gp_run": gp_run,
        "gp_run_async": gp_run_async,
        # GP Extendido
        "gp_tool_help": gp_tool_help,
        "gp_search_services": gp_search_services,
        "gp_service_info": gp_service_info,
        "gp_linear_unit": gp_linear_unit,
        "gp_data_file": gp_data_file,
        "gp_raster_data": gp_raster_data,
        "gp_run_with_env": gp_run_with_env,
        # Admin Básica
        "user_list": user_list,
        "user_create": user_create,
        "group_list": group_list,
        # Portal Logs
        "portal_logs_query": portal_logs_query,
        "portal_logs_clean": portal_logs_clean,
        "portal_logs_settings": portal_logs_settings,
        "portal_logs_settings_update": portal_logs_settings_update,
        # Admin Enterprise
        "admin_licenses": admin_licenses,
        "admin_services_health": admin_services_health,
        "admin_servers_list": admin_servers_list,
        # Items
        "item_get": item_get,
        "item_update": item_update,
        "item_protect": item_protect,
        "item_unprotect": item_unprotect,
        "item_metadata": item_metadata,
        "item_download": item_download,
        "item_delete": item_delete,
        "item_move": item_move,
        "item_clone": item_clone,
        "item_publish": item_publish,
        "item_export": item_export,
        "item_share": item_share,
        "item_layers": item_layers,
        "item_dependent_upon": item_dependent_upon,
        "item_dependent_to": item_dependent_to,
        "item_related_items": item_related_items,
        "item_reassign": item_reassign,
        "item_get_data": item_get_data,
        "item_thumbnail": item_thumbnail,
        "item_add_comment": item_add_comment,
        "item_resources": item_resources,
        # Usuarios
        "user_get": user_get,
        "user_update": user_update,
        "user_disable": user_disable,
        "user_enable": user_enable,
        "user_set_role": user_set_role,
        "user_content": user_content,
        # Grupos
        "group_get": group_get,
        "group_update": group_update,
        "group_add_users": group_add_users,
        "group_remove_users": group_remove_users,
        "group_content": group_content,
        "group_members": group_members,
        "group_create": group_create,
        # Sharing
        "share_get_access": share_get_access,
        "share_set_access": share_set_access,
        "share_status": share_status,
        "share_bulk_set_access": share_bulk_set_access,
        "share_audit_public": share_audit_public,
        "share_audit_by_owner": share_audit_by_owner,
        "share_group_add": share_group_add,
        "share_group_remove": share_group_remove,
        "share_group_list": share_group_list,
        "share_group_replace": share_group_replace,
        "share_group_copy": share_group_copy,
        "share_group_audit": share_group_audit,
        # Feature / Table / FLC / FSet / FC
        "feature_get": feature_get,
        "feature_get_value": feature_get_value,
        "feature_update": feature_update,
        "table_query": table_query,
        "table_edit": table_edit,
        "table_fields": table_fields,
        "flc_describe": flc_describe,
        "flc_update_definition": flc_update_definition,
        "flc_truncate": flc_truncate,
        "fset_from_query": fset_from_query,
        "fset_statistics": fset_statistics,
        "fset_to_geojson": fset_to_geojson,
        "fc_describe": fc_describe,
        "fc_query": fc_query,
        "fc_to_feature_layer": fc_to_feature_layer,
        # Feature Layer
        "fl_fields": fl_fields,
        "fl_query_advanced": fl_query_advanced,
        "fl_edit": fl_edit,
        "fl_delete_by_query": fl_delete_by_query,
        "fl_calculate": fl_calculate,
        "fl_capabilities": fl_capabilities,
        # ArcGIS Server
        "server_list": server_list,
        "server_services_list": server_services_list,
        "server_service_status": server_service_status,
        "server_service_start": server_service_start,
        "server_service_stop": server_service_stop,
        "server_service_restart": server_service_restart,
        "server_logs_query": server_logs_query,
        "server_logs_clean": server_logs_clean,
        "server_machines_list": server_machines_list,
        "server_machine_hardware": server_machine_hardware,
        "server_service_manifest": server_service_manifest,
        "server_services_directory_list": server_services_directory_list,
        "server_services_folders": server_services_folders,
        # Web Maps
        "webmap_get": webmap_get,
        "webmap_layers": webmap_layers,
        "webmap_add_layer": webmap_add_layer,
        "webmap_remove_layer": webmap_remove_layer,
        "webmap_update_layer": webmap_update_layer,
        "webmap_create": webmap_create,
        # Geocodificación
        "geocode": geocode,
        "reverse_geocode": reverse_geocode,
        "geocode_suggest": geocode_suggest,
        "batch_geocode": batch_geocode,
        # Geometría
        "geometry_project": geometry_project,
        "geometry_buffer": geometry_buffer,
        "geometry_area_length": geometry_area_length,
        "geometry_simplify": geometry_simplify,
        # Map Image Layer
        "mil_info": mil_info,
        "mil_sublayers": mil_sublayers,
        "mil_query": mil_query,
        # FL Extended
        "fl_add_field": fl_add_field,
        "fl_delete_fields": fl_delete_fields,
        "fl_attachments_list": fl_attachments_list,
        "fl_attachment_add": fl_attachment_add,
        "fl_related_records": fl_related_records,
        "fl_append": fl_append,
        # Layer Views
        "fl_view_list": fl_view_list,
        "fl_create_view": fl_create_view,
        # Créditos
        "org_credits": org_credits,
        "org_usage": org_usage,
        # Admin Extended
        "admin_org_settings": admin_org_settings,
        "admin_system_info": admin_system_info,
        "admin_reindex": admin_reindex,
        # Webhooks
        "webhook_list": webhook_list,
        "webhook_create": webhook_create,
        "webhook_delete": webhook_delete,
        # Notebooks
        "notebook_list": notebook_list,
        "notebook_execute": notebook_execute,
        # GeoEnrichment
        "enrich_countries": enrich_countries,
        "enrich_data_collections": enrich_data_collections,
        "enrich_areas": enrich_areas,
        # Web Scenes
        "webscene_get": webscene_get,
        "webscene_layers": webscene_layers,
    }

    @app.get("/", response_class=HTMLResponse, tags=["Root"])
    def root():
        """Página de inicio del servidor MCP."""
        return f"""
        <html>
            <head>
                <title>ArcGIS MCP Server</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                    h1 {{ color: #0079c1; }}
                    a {{ color: #0079c1; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    .links {{ margin: 20px 0; }}
                    .links a {{ display: block; margin: 10px 0; }}
                </style>
            </head>
            <body>
                <h1>🌐 ArcGIS MCP Server</h1>
                <p>Servidor MCP para ArcGIS Online y Enterprise</p>
                <div class="links">
                    <a href="/docs">📚 Documentación Interactiva (Swagger UI)</a>
                    <a href="/redoc">📖 Documentación ReDoc</a>
                    <a href="/tools">🔧 Listar herramientas disponibles</a>
                </div>
                <p><strong>Versión:</strong> 2.1.0</p>
                <p><strong>Tools disponibles:</strong> {len(TOOLS)}</p>
            </body>
        </html>
        """

    @app.get("/tools", tags=["MCP Tools"])
    def list_tools_http():
        """Lista todas las herramientas MCP disponibles."""
        tools_info = []
        for name, func in TOOLS.items():
            doc = (func.__doc__ or "").strip().split("\n")[0][:200]
            sig = str(inspect.signature(func))
            tools_info.append({
                "name": name,
                "description": doc,
                "signature": f"{name}{sig}"
            })
        return {
            "total": len(tools_info),
            "tools": tools_info
        }

    @app.post("/tools/{tool_name}", tags=["MCP Tools"])
    def call_tool_http(tool_name: str, params: dict = Body(default={})):
        """Llama a cualquier tool MCP registrada usando HTTP POST.
        
        Ejemplo: POST /tools/whoami {}
        """
        try:
            if tool_name not in TOOLS:
                available = list(TOOLS.keys())
                raise HTTPException(
                    status_code=404,
                    detail=f"Tool '{tool_name}' no encontrada. Disponibles: {available[:10]}..."
                )
            
            func = TOOLS[tool_name]
            
            # Ejecutar la función con los parámetros
            if params and any(v is not None for v in params.values()):
                result = func(**params)
            else:
                result = func()
            
            return {"tool": tool_name, "result": result}
        except TypeError as e:
            # Error de parámetros
            sig = str(inspect.signature(func))
            raise HTTPException(
                status_code=400,
                detail=f"Parámetros inválidos para {tool_name}{sig}: {e}"
            )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"Error en tool {tool_name}: {e}\n{tb}", file=sys.stderr)
            raise HTTPException(status_code=500, detail=str(e))

    print("Iniciando servidor HTTP en http://0.0.0.0:8080")
    print("Documentación interactiva: http://localhost:8080/docs")
    print(f"Tools disponibles: {len(TOOLS)}")
    
    # Ejecutar uvicorn con la aplicación
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    server.run()


