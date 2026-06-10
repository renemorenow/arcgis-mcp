from __future__ import annotations

import sys

from _server import mcp
from _auth import AZURE_TENANT_ID, AZURE_CLIENT_ID_MCP, AZURE_AUDIENCE

# --------------------------------------------------------------------------- #
# MODO SSE (MCP sobre HTTP+SSE para M365 Copilot / Copilot Studio)
# --------------------------------------------------------------------------- #

# Cache de claves JWKS para no llamar a Microsoft en cada request
_jwks_cache: dict = {"keys": [], "expires_at": 0.0}


def _validate_entra_token(token: str) -> dict:
    """Valida un Bearer token JWT de Entra ID usando JWKS público de Microsoft.

    Si AZURE_TENANT_ID / AZURE_CLIENT_ID_MCP no están configurados,
    omite la validación y emite un aviso (permite desarrollo local sin Entra).

    Requiere: pip install PyJWT cryptography
    """
    import time as _time

    if not AZURE_TENANT_ID or not AZURE_CLIENT_ID_MCP:
        print(
            "[WARN] AZURE_TENANT_ID / AZURE_CLIENT_ID_MCP no configurados. "
            "Validación de token Entra ID omitida.",
            file=sys.stderr,
        )
        return {}

    try:
        import jwt  # PyJWT
        from jwt.algorithms import RSAAlgorithm
    except ImportError as exc:
        raise RuntimeError(
            "PyJWT no instalado. Ejecutar: pip install 'PyJWT[cryptography]'"
        ) from exc

    import urllib.request
    import json as _json

    # Refrescar JWKS si el cache expiró (TTL = 1 hora)
    now = _time.time()
    if now > _jwks_cache["expires_at"]:
        jwks_url = (
            f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
            "/discovery/v2.0/keys"
        )
        with urllib.request.urlopen(jwks_url, timeout=10) as resp:  # noqa: S310
            _jwks_cache["keys"] = _json.loads(resp.read()).get("keys", [])
            _jwks_cache["expires_at"] = now + 3600

    # Obtener key id del header del token
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")

    public_key = None
    for key_data in _jwks_cache["keys"]:
        if key_data.get("kid") == kid:
            public_key = RSAAlgorithm.from_jwk(_json.dumps(key_data))
            break

    if public_key is None:
        raise ValueError(f"Clave pública Entra ID no encontrada para kid={kid!r}")

    audience = AZURE_AUDIENCE or AZURE_CLIENT_ID_MCP
    issuer = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/v2.0"

    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
    )


def run_sse_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Levanta el MCP en modo SSE con validación de token Entra ID.

    Usar para distribuir el MCP a la organización vía M365 Copilot / Copilot Studio.
    El protocolo es MCP estándar sobre HTTP+SSE — compatible con cualquier cliente MCP.

    Variables de entorno requeridas para auth:
        AZURE_TENANT_ID        — ID del tenant Azure de la organización
        AZURE_CLIENT_ID_MCP    — Client ID de la App Registration del MCP
        AZURE_AUDIENCE         — (opcional) audience del token; default = AZURE_CLIENT_ID_MCP

    Si las variables no están configuradas el servidor arranca sin auth
    (modo desarrollo) pero emite un aviso en stderr.

    Ejecutar con:
        python arcgis_mcp.py --sse
        python arcgis_mcp.py --sse --port 9090
    """
    import uvicorn
    from starlette.applications import Starlette
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route
    from mcp.server.sse import SseServerTransport

    class EntraIDAuthMiddleware(BaseHTTPMiddleware):
        """Middleware que valida tokens Bearer de Entra ID en cada request."""

        async def dispatch(self, request, call_next):
            # CORS preflight y health check pasan sin auth
            if request.method == "OPTIONS" or request.url.path == "/health":
                return await call_next(request)

            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse(
                    {"error": "Unauthorized", "detail": "Bearer token requerido"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )

            try:
                _validate_entra_token(auth[7:])
            except Exception as exc:
                return JSONResponse(
                    {"error": "Unauthorized", "detail": str(exc)},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )

            return await call_next(request)

    # Crear el transporte SSE apuntando al servidor MCP interno de FastMCP
    sse_transport = SseServerTransport("/messages/")
    _mcp_server = mcp._mcp_server  # servidor MCP subyacente de FastMCP

    async def handle_sse(scope, receive, send):
        async with sse_transport.connect_sse(scope, receive, send) as streams:
            await _mcp_server.run(
                streams[0],
                streams[1],
                _mcp_server.create_initialization_options(),
            )

    async def health(scope, receive, send):
        response = JSONResponse({"status": "ok", "tools": 145})
        await response(scope, receive, send)

    starlette_app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse_transport.handle_post_message),
            Route("/health", endpoint=health),
        ],
    )
    starlette_app.add_middleware(EntraIDAuthMiddleware)

    arcgis_auth_status = (
        f"Entra ID tenant={AZURE_TENANT_ID[:8]}..."
        if AZURE_TENANT_ID
        else "SIN AUTH (desarrollo) — configurar AZURE_TENANT_ID para produccion"
    )
    print(f"[SSE] ArcGIS MCP iniciando en https://{host}:{port}/sse")
    print(f"[SSE] Endpoint SSE : https://{host}:{port}/sse")
    print(f"[SSE] Health check : https://{host}:{port}/health")
    print(f"[SSE] Auth         : {arcgis_auth_status}")
    print(f"[SSE] Tools        : 145")

    uvicorn.run(starlette_app, host=host, port=port, log_level="info")


# --------------------------------------------------------------------------- #
