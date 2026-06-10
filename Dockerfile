FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para arcgis + cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    libkrb5-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python primero (aprovecha cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente
COPY arcgis_mcp.py .
COPY _server.py .
COPY _auth.py .
COPY tools/ ./tools/
COPY transport/ ./transport/

# Puerto expuesto (Container Apps lo mapea a HTTPS automáticamente)
EXPOSE 8080

# Modo SSE — requiere AZURE_TENANT_ID y AZURE_CLIENT_ID_MCP en env vars
CMD ["python", "arcgis_mcp.py", "--sse"]
