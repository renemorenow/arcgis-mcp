# deploy-azure.ps1
# Deploy ArcGIS MCP a Azure Container Apps con HTTPS automatico
#
# REQUISITOS:
#   - az CLI instalado: https://docs.microsoft.com/cli/azure/install-azure-cli
#   - Docker Desktop corriendo
#   - Permisos Contributor en la subscription
#
# USO:
#   .\deploy-azure.ps1

# ============================================================
# CONFIGURAR ESTAS VARIABLES
# ============================================================
$SUBSCRIPTION_ID   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # az account show --query id
$RESOURCE_GROUP    = "rg-arcgis-mcp"
$LOCATION          = "eastus"                                   # o "brazilsouth" si es mas rapido
$ACR_NAME          = "arcgismcpregistry"                        # must be globally unique, solo letras/numeros
$APP_NAME          = "arcgis-mcp"
$ENV_NAME          = "arcgis-mcp-env"

# ArcGIS Enterprise (autenticacion en el contenedor - NO usa GIS("Pro"))
$ARCGIS_URL        = "https://bnig.esri.co/portal"
$ARCGIS_USER       = "adminbni"
$ARCGIS_PASS       = ""    # completar - se envia como secret

# Entra ID (de tu App Registration)
$AZURE_TENANT_ID      = ""   # Directory (tenant) ID
$AZURE_CLIENT_ID_MCP  = ""   # Application (client) ID

# ============================================================
# NO EDITAR DESDE AQUI
# ============================================================

Write-Host "`n=== ArcGIS MCP - Deploy a Azure Container Apps ===" -ForegroundColor Cyan

# 1. Login y seleccionar subscription
Write-Host "`n[1/7] Autenticando en Azure..."
az login --output none
az account set --subscription $SUBSCRIPTION_ID

# 2. Crear resource group
Write-Host "`n[2/7] Creando resource group: $RESOURCE_GROUP..."
az group create --name $RESOURCE_GROUP --location $LOCATION --output none

# 3. Crear Azure Container Registry
Write-Host "`n[3/7] Creando ACR: $ACR_NAME..."
az acr create --resource-group $RESOURCE_GROUP `
              --name $ACR_NAME `
              --sku Basic `
              --admin-enabled true `
              --output none

$ACR_LOGIN_SERVER = (az acr show --name $ACR_NAME --query loginServer --output tsv)
Write-Host "  ACR: $ACR_LOGIN_SERVER"

# 4. Build y push de la imagen
Write-Host "`n[4/7] Build y push de imagen Docker..."
Set-Location $PSScriptRoot
az acr build --registry $ACR_NAME `
             --image "arcgis-mcp:latest" `
             --file Dockerfile `
             .

# 5. Crear Container Apps Environment
Write-Host "`n[5/7] Creando Container Apps Environment..."
az containerapp env create `
    --name $ENV_NAME `
    --resource-group $RESOURCE_GROUP `
    --location $LOCATION `
    --output none

# 6. Obtener credenciales ACR
$ACR_USERNAME = (az acr credential show --name $ACR_NAME --query username --output tsv)
$ACR_PASSWORD = (az acr credential show --name $ACR_NAME --query "passwords[0].value" --output tsv)

# 7. Crear Container App
Write-Host "`n[6/7] Creando Container App: $APP_NAME..."
az containerapp create `
    --name $APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --environment $ENV_NAME `
    --image "$ACR_LOGIN_SERVER/arcgis-mcp:latest" `
    --registry-server $ACR_LOGIN_SERVER `
    --registry-username $ACR_USERNAME `
    --registry-password $ACR_PASSWORD `
    --target-port 8080 `
    --ingress external `
    --min-replicas 1 `
    --max-replicas 3 `
    --cpu 1.0 `
    --memory 2.0Gi `
    --env-vars `
        "ARCGIS_URL=$ARCGIS_URL" `
        "ARCGIS_USER=$ARCGIS_USER" `
        "ARCGIS_PASS=secretref:arcgis-pass" `
        "ARCGIS_WRITE_ENABLED=false" `
        "AZURE_TENANT_ID=$AZURE_TENANT_ID" `
        "AZURE_CLIENT_ID_MCP=$AZURE_CLIENT_ID_MCP" `
    --secrets "arcgis-pass=$ARCGIS_PASS" `
    --output none

# 8. Obtener URL final
$APP_URL = (az containerapp show `
    --name $APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --query properties.configuration.ingress.fqdn `
    --output tsv)

Write-Host "`n[7/7] Verificando health check..."
Start-Sleep -Seconds 15   # esperar que el contenedor arranque
$health = Invoke-RestMethod -Uri "https://$APP_URL/health" -ErrorAction SilentlyContinue
if ($health.status -eq "ok") {
    Write-Host "  Health check: OK ($($health.tools) tools)" -ForegroundColor Green
} else {
    Write-Host "  Health check: pendiente (esperar ~30s mas y retry)" -ForegroundColor Yellow
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "DEPLOY COMPLETADO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  SSE endpoint : https://$APP_URL/sse"
Write-Host "  Health check : https://$APP_URL/health"
Write-Host ""
Write-Host "SIGUIENTE PASO - Registrar en Copilot Studio:"
Write-Host "  1. https://copilotstudio.microsoft.com"
Write-Host "  2. Tu agente -> Actions -> Add action -> MCP"
Write-Host "  3. URL: https://$APP_URL/sse"
Write-Host "  4. Auth: OAuth 2.0 / Entra ID"
Write-Host "     Tenant ID : $AZURE_TENANT_ID"
Write-Host "     Client ID : $AZURE_CLIENT_ID_MCP"
Write-Host ""
