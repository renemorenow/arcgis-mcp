# Setup script para ArcGIS MCP en Windows
# Ejecutar: .\setup.ps1

Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host "SETUP COMPLETO - ArcGIS MCP"
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host ""

# Verificar que estamos en el directorio correcto
if (-not (Test-Path "arcgis_mcp.py")) {
    Write-Host "❌ Error: No se encontró arcgis_mcp.py" -ForegroundColor Red
    Write-Host "   Asegúrate de ejecutar este script desde el directorio arcgis-mcp" -ForegroundColor Yellow
    exit 1
}

# Verificar Python
Write-Host "Verificando Python..." -ForegroundColor Cyan
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python no encontrado en PATH" -ForegroundColor Red
    Write-Host "   Activa tu entorno conda primero:" -ForegroundColor Yellow
    Write-Host "   conda activate c:\Users\wmoreno\AppData\Local\ESRI\conda\envs\arcgispro-py3-clone" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Este script realizará:" -ForegroundColor Cyan
Write-Host "  1. Instalación inteligente de dependencias"
Write-Host "  2. Verificación post-instalación"
Write-Host "" 
Write-Host "IMPORTANTE:" -ForegroundColor Yellow
Write-Host "  setup.ps1 asume que el python activo YA es compatible con MCP." -ForegroundColor Yellow
Write-Host "  Si tienes ArcGIS Pro < 3.3, usa install.ps1 para que seleccione" -ForegroundColor Yellow
Write-Host "  automáticamente un Python externo 3.11+." -ForegroundColor Yellow
Write-Host ""

$response = Read-Host "¿Continuar? (S/N)"
if ($response -ne "S" -and $response -ne "s" -and $response -ne "") {
    Write-Host "Operación cancelada." -ForegroundColor Yellow
    exit 0
}

# Paso 1: Instalación
Write-Host ""
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host "PASO 1: Instalación de dependencias"
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host ""

python install_requirements.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ La instalación falló." -ForegroundColor Red
    exit $LASTEXITCODE
}

# Paso 2: Verificación
Write-Host ""
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host "PASO 2: Verificación post-instalación"
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host ""

python verify_installation.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "⚠️  La verificación detectó problemas." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

# Éxito
Write-Host ""
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host "🎉 SETUP COMPLETADO EXITOSAMENTE" -ForegroundColor Green
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host ""
Write-Host "✅ El servidor ArcGIS MCP está listo para usar." -ForegroundColor Green
Write-Host ""
Write-Host "Opciones de ejecución:" -ForegroundColor Cyan
Write-Host "  1. Modo MCP (servidor):  " -NoNewline
Write-Host "python arcgis_mcp.py" -ForegroundColor Yellow
Write-Host "  2. Modo HTTP (FastAPI):  " -NoNewline
Write-Host "python arcgis_mcp.py --http" -ForegroundColor Yellow
Write-Host ""
Write-Host "Documentación:" -ForegroundColor Cyan
Write-Host "  README.md - Guía completa de uso"
Write-Host "  .env.example - Ejemplo de configuración"
Write-Host "=" -NoNewline
Write-Host ("=" * 69)
Write-Host ""
