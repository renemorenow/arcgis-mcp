"""
arcgis-mcp — Servidor MCP unificado para ArcGIS Online / Enterprise.

Modos de ejecución:
    python arcgis_mcp.py           → stdio  (Claude Desktop, VS Code MCP, IDEs)
    python arcgis_mcp.py --sse     → SSE+Entra ID (M365 Copilot, Copilot Studio)
    python arcgis_mcp.py --http    → FastAPI REST (Swagger UI en /docs)
    python arcgis_mcp.py --sse --port 9090  → SSE en puerto personalizado

Requisitos: pip install arcgis fastmcp python-dotenv uvicorn fastapi PyJWT cryptography
"""
from __future__ import annotations

# Importar el servidor FastMCP (define mcp = FastMCP("arcgis-mcp"))
from _server import mcp  # noqa: F401

# Importar modos de transporte alternativos
from transport.http_mode import run_http_server
from transport.sse_mode import run_sse_server

if __name__ == "__main__":
    import sys

    _args = sys.argv[1:]

    # Leer --port N si se pasa
    _port = 8080
    if "--port" in _args:
        _idx = _args.index("--port")
        try:
            _port = int(_args[_idx + 1])
        except (IndexError, ValueError):
            pass

    if "--sse" in _args:
        # Modo SSE: MCP sobre HTTP+SSE con auth Entra ID
        # Usar para distribución organizacional (M365 Copilot / Copilot Studio)
        run_sse_server(port=_port)
    elif "--http" in _args:
        # Modo HTTP: FastAPI custom (endpoints REST, Swagger UI)
        run_http_server()
    else:
        # Modo stdio: MCP estándar para desarrolladores / clientes locales
        # (Claude Desktop, VS Code MCP, etc.)
        mcp.run()
