# Historial de Cambios - ArcGIS MCP

## [2.1.0] - 2026-06-03 - Renombramiento y Mejoras de Autenticación

### 🏷️ Renombramiento
- **Carpeta**: `arcgis-enterprise-mcp-admin` → `arcgis-mcp`
- **Razón**: Nombre más genérico que refleja soporte para ArcGIS Online y Enterprise
- **Impacto**: Solo cambios en rutas, código y funcionalidad sin cambios

### ✨ Nuevas funciones de autenticación
- **OAuth2 interactivo**: Abre navegador para autenticación del usuario
  - Variable `ARCGIS_USE_OAUTH=true`
  - Soporta ArcGIS Online y Enterprise
  - Client ID personalizable
- **Mejoras en GIS("Pro")**: Logs informativos de conexión
- **Orden de prioridad claro**: Pro → OAuth2 → Profile → API Key → Token → User/Pass

### 🌐 Modo HTTP integrado
- **`arcgis_mcp.py --http`**: Servidor FastAPI para testing y desarrollo
- Documentación interactiva en `/docs`
- Exposición de tools MCP vía REST API

### 🧪 Nuevos scripts de prueba
- `test_pro.py` - Valida conexión con ArcGIS Pro activo
- `test_oauth.py` - Prueba OAuth2 interactivo con navegador

### 📚 Documentación
- README actualizado con ejemplos de cada modo de autenticación
- Sección clara de "Funciones específicas de Enterprise"
- Guía de cuándo usar cada modo
- Instrucciones para ejecutar `arcgis_mcp.py --http`

## [2.0.0] - 2026-06-02 - Fusión Unificada

### ✨ Nuevo
- **Archivo consolidado único**: `arcgis_mcp.py` fusiona toda la funcionalidad
- **Autenticación mejorada**: Prioridad automática (Pro → Profile → API Key → Token → User/Pass)
- **49 tools MCP** disponibles en un solo servidor
- **Modo HTTP opcional**: `--http` para exposición FastAPI
- **Documentación completa**: README actualizado con ejemplos

### 🔀 Fusión de sesiones anteriores

**De `main.py` + `tools/`:**
- Arquitectura modular con funciones específicas de Enterprise
- Exposición HTTP vía FastAPI
- Funciones de administración: usuarios, grupos, contenido, sharing
- Funciones específicas: webhooks, notebooks, servidores federados

**De `arcgis_admin_mcp.py`:**
- Autenticación robusta (API_KEY, PROFILE, TOKEN)
- Guardarrailes de escritura (WRITE_ENABLED, dry_run)
- Detección de plataforma (Online vs Enterprise) y versión
- Análisis espacial completo (buffers, overlay, hot spots, etc.)
- Geoprocesamiento dinámico (discover + run)
- Geocodificación directa e inversa
- Helpers internos (_parse_version, _require_write, _safe_result)

### 📦 Tools disponibles (49 total)

**Introspección (2)**
- whoami, describe_feature_layer

**Contenido (3)**
- search_content, query_features, add_features

**Análisis Espacial (5)**
- create_buffers, overlay_layers, find_hot_spots, summarize_within, find_nearest

**Geoprocesamiento (2)**
- discover_gp_tools, run_gp_tool

**Geocodificación (2)**
- geocode_address, reverse_geocode_location

**Administración Básica (4)**
- list_users, list_groups, create_user, get_server_logs

**Usuarios (3)**
- listar_usuarios_admin, auditoria_inactivos, ver_licencias

**Contenido Auditoría (2)**
- buscar_items_pesados, auditoria_tags

**Servidores (2)**
- verificar_salud_servicios, listar_servidores_federados

**Webhooks (3)**
- listar_webhooks, historial_fallos_webhook, configuracion_webhook

**Notebooks (2)**
- ejecutar_notebook_id, estadisticas_contenedores

**Grupos (4)**
- listar_grupos, buscar_grupo, miembros_grupo, crear_grupo

**Compartir (3)**
- compartir_item, quitar_compartir_item, ver_compartidos

**Portal (2)**
- estado_portal, version_portal

### 📝 Cambios de comportamiento

1. **Autenticación**: Ahora intenta primero `GIS("Pro")` como fallback automático
2. **Escritura**: Todas las operaciones de escritura requieren `ARCGIS_WRITE_ENABLED=true`
3. **Dry run**: Operaciones destructivas tienen `dry_run=True` por defecto
4. **Enterprise check**: Tools específicas de Enterprise validan plataforma antes de ejecutar

### 🗂️ Archivos

- ✅ **`arcgis_mcp.py`** - Archivo principal consolidado (nuevo)
- 📚 `main.py` - Referencia histórica (mantener)
- 📚 `arcgis_admin_mcp.py` - Referencia histórica (mantener)
- 📚 `tools/*` - Referencia histórica (mantener)
- ✅ `requirements.txt` - Actualizado con todas las dependencias
- ✅ `README.md` - Documentación completa actualizada
- ✅ `.env.example` - Plantilla de configuración

### 🚀 Migración

Para migrar desde versiones anteriores:

```bash
# Ya no es necesario ejecutar main.py, usar directamente:
python arcgis_mcp.py

# O en modo HTTP:
python arcgis_mcp.py --http
```

Los módulos `tools/*` están integrados, no es necesario importarlos.

---

## [1.0.0] - Versión inicial

- Implementación modular con `main.py` + `tools/`
- Implementación monolítica con `arcgis_admin_mcp.py`
- Funcionalidad base de administración Enterprise
