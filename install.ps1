# install.ps1 - ArcGIS MCP: Instalador automatico
#
# Uso: clic derecho -> "Ejecutar con PowerShell"
#      o desde terminal: .\install.ps1
#
# Que hace:
#   1. Detecta el entorno Python de ArcGIS Pro automaticamente
#   2. Instala las dependencias necesarias
#   3. Configura los IDEs instalados en tu maquina
#      (VS Code, Claude Desktop, Cursor, Codex, Claude Code, OpenCode, OpenClaw)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Header($text) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor DarkCyan
}

function Write-Ok($text)   { Write-Host "  [OK] $text" -ForegroundColor Green   }
function Write-Skip($text) { Write-Host "  [--] $text" -ForegroundColor DarkGray }
function Write-Warn($text) { Write-Host "  [!!] $text" -ForegroundColor Yellow  }
function Write-Fail($text) { Write-Host "  [XX] $text" -ForegroundColor Red     }

function Get-CmdPath($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# Merge seguro de un MCP server en un JSON existente
function Merge-McpJson {
    param(
        [string]$ConfigPath,
        [string]$ServerKey,
        [object]$ServerEntry,
        [string]$RootKey = "mcpServers"
    )

    $dir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (Test-Path $ConfigPath) {
        $raw = Get-Content $ConfigPath -Raw -Encoding UTF8
        $raw = $raw -replace '(?m)^\s*//.*$', ''
        try   { $json = $raw | ConvertFrom-Json }
        catch { $json = New-Object PSObject }
    } else {
        $json = New-Object PSObject
    }

    if (-not ($json.PSObject.Properties.Name -contains $RootKey)) {
        Add-Member -InputObject $json -NotePropertyName $RootKey `
                   -NotePropertyValue (New-Object PSObject)
    }

    $servers = $json.$RootKey
    if ($servers.PSObject.Properties.Name -contains $ServerKey) {
        $servers.PSObject.Properties.Remove($ServerKey)
    }
    Add-Member -InputObject $servers -NotePropertyName $ServerKey `
               -NotePropertyValue $ServerEntry

    $json | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
}

# Merge para VS Code settings.json (estructura bajo "mcp" -> "servers")
function Merge-VsCodeSettings {
    param([string]$SettingsPath, [string]$ServerKey, [object]$ServerEntry)

    $dir = Split-Path $SettingsPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (Test-Path $SettingsPath) {
        $raw = Get-Content $SettingsPath -Raw -Encoding UTF8
        $raw = $raw -replace '(?m)^\s*//.*$', ''
        try   { $json = $raw | ConvertFrom-Json }
        catch { $json = New-Object PSObject }
    } else {
        $json = New-Object PSObject
    }

    if (-not ($json.PSObject.Properties.Name -contains "mcp")) {
        Add-Member -InputObject $json -NotePropertyName "mcp" `
                   -NotePropertyValue (New-Object PSObject)
    }
    if (-not ($json.mcp.PSObject.Properties.Name -contains "servers")) {
        Add-Member -InputObject $json.mcp -NotePropertyName "servers" `
                   -NotePropertyValue (New-Object PSObject)
    }

    $servers = $json.mcp.servers
    if ($servers.PSObject.Properties.Name -contains $ServerKey) {
        $servers.PSObject.Properties.Remove($ServerKey)
    }
    Add-Member -InputObject $servers -NotePropertyName $ServerKey `
               -NotePropertyValue $ServerEntry

    $json | ConvertTo-Json -Depth 10 | Set-Content $SettingsPath -Encoding UTF8
}

# Merge para Codex config.toml (TOML manual)
function Merge-CodexToml {
    param([string]$ConfigPath, [string]$PythonExe, [string]$ScriptPath)

    $dir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $pyEscaped = $PythonExe  -replace '\\', '\\'
    $scEscaped = $ScriptPath -replace '\\', '\\'

    $newBlock = "`n[mcp_servers.arcgis-mcp]`ncommand = `"$pyEscaped`"`nargs = [`"$scEscaped`"]`n`n[mcp_servers.arcgis-mcp.env]`nARCGIS_WRITE_ENABLED = `"false`"`n"

    if (Test-Path $ConfigPath) {
        $content = Get-Content $ConfigPath -Raw -Encoding UTF8
        $content = $content -replace '(?s)\[mcp_servers\.arcgis-mcp\].*?(?=\n\[|\z)', ''
        $content = $content.TrimEnd() + $newBlock
    } else {
        $content = $newBlock.TrimStart()
    }

    Set-Content $ConfigPath $content -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

Clear-Host
Write-Host ""
Write-Host "  +--------------------------------------------------+" -ForegroundColor Cyan
Write-Host "  |     ArcGIS MCP - Instalador automatico           |" -ForegroundColor Cyan
Write-Host "  |  Configura VS Code, Claude, Cursor y mas         |" -ForegroundColor Cyan
Write-Host "  +--------------------------------------------------+" -ForegroundColor Cyan
Write-Host ""

$SCRIPT_DIR = $PSScriptRoot
$MCP_SCRIPT  = Join-Path $SCRIPT_DIR "arcgis_mcp.py"

if (-not (Test-Path $MCP_SCRIPT)) {
    Write-Fail "No se encontro arcgis_mcp.py en: $SCRIPT_DIR"
    Write-Host "  Ejecuta este script desde la carpeta arcgis-mcp." -ForegroundColor Yellow
    Read-Host "`nPresiona ENTER para salir"
    exit 1
}

# ---------------------------------------------------------------------------
# PASO 1: Detectar Python de ArcGIS Pro
# ---------------------------------------------------------------------------

Write-Header "PASO 1 - Detectando entorno Python de ArcGIS Pro"

$PYTHON_EXE = $null
$candidates = [System.Collections.Generic.List[string]]::new()

$esriLocal = Join-Path $env:LOCALAPPDATA "ESRI\conda\envs"
if (Test-Path $esriLocal) {
    Get-ChildItem $esriLocal -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $py = Join-Path $_.FullName "python.exe"
        if (Test-Path $py) { $candidates.Add($py) }
    }
}

$esriData = Join-Path $env:ProgramData "ESRI\conda\envs"
if (Test-Path $esriData) {
    Get-ChildItem $esriData -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $py = Join-Path $_.FullName "python.exe"
        if (Test-Path $py) { $candidates.Add($py) }
    }
}

$staticPy = "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
if (Test-Path $staticPy) { $candidates.Add($staticPy) }

$PYTHON_EXE = $candidates | Where-Object { $_ -like "*clone*" } | Select-Object -First 1
if (-not $PYTHON_EXE) {
    $PYTHON_EXE = $candidates | Select-Object -First 1
}

if (-not $PYTHON_EXE) {
    Write-Fail "No se encontro ArcGIS Pro ni su entorno Python."
    Write-Host ""
    Write-Host "  Opciones:" -ForegroundColor Yellow
    Write-Host "  1. Instala ArcGIS Pro y vuelve a ejecutar este script." -ForegroundColor Yellow
    Write-Host "  2. Ingresa la ruta manualmente:" -ForegroundColor Yellow
    $PYTHON_EXE = Read-Host "     Ruta al python.exe de ArcGIS Pro"
    if (-not (Test-Path $PYTHON_EXE)) {
        Write-Fail "Ruta invalida. Abortando."
        Read-Host "`nPresiona ENTER para salir"
        exit 1
    }
}

Write-Ok "Python: $PYTHON_EXE"

$hasArcgis = & $PYTHON_EXE -c "import arcgis; print(arcgis.__version__)" 2>$null
if ($hasArcgis) {
    Write-Ok "arcgis $hasArcgis detectado"
} else {
    Write-Warn "El entorno no tiene arcgis. Se intentara instalar."
}

# ---------------------------------------------------------------------------
# PASO 2: Instalar dependencias
# ---------------------------------------------------------------------------

Write-Header "PASO 2 - Instalando dependencias"

$reqFile = Join-Path $SCRIPT_DIR "requirements.txt"
Write-Host "  Instalando desde requirements.txt ..." -ForegroundColor DarkGray

try {
    & $PYTHON_EXE -m pip install -r $reqFile --quiet --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "pip retorno codigo $LASTEXITCODE" }
    Write-Ok "Dependencias instaladas"
} catch {
    Write-Fail "Error: $_"
    Read-Host "`nPresiona ENTER para salir"
    exit 1
}

# ---------------------------------------------------------------------------
# PASO 3: Verificar que el servidor arranca
# ---------------------------------------------------------------------------

Write-Header "PASO 3 - Verificando el servidor MCP"

$pyScript = "import sys; sys.path.insert(0, r'" + $SCRIPT_DIR + "'); from _server import mcp; import _auth, tools; print('OK')"
$verifyResult = & $PYTHON_EXE -c $pyScript 2>&1

if ($verifyResult -match "OK") {
    Write-Ok "Servidor MCP verificado"
} else {
    Write-Warn "Verificacion con advertencias (normal si ArcGIS Pro no esta abierto)"
    Write-Host "  $verifyResult" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# PASO 4: Configurar IDEs
# ---------------------------------------------------------------------------

Write-Header "PASO 4 - Configurando IDEs"

# Objeto base del servidor (compatible PS 5.1 - sin hashtable cast a PSObject)
$baseEnv = New-Object PSObject
Add-Member -InputObject $baseEnv -NotePropertyName "ARCGIS_WRITE_ENABLED" -NotePropertyValue "false"

$serverBase = New-Object PSObject
Add-Member -InputObject $serverBase -NotePropertyName "command" -NotePropertyValue $PYTHON_EXE
Add-Member -InputObject $serverBase -NotePropertyName "args"    -NotePropertyValue @($MCP_SCRIPT)
Add-Member -InputObject $serverBase -NotePropertyName "env"     -NotePropertyValue $baseEnv

# OpenCode usa "type" + command como array + "environment"
$ocEnv = New-Object PSObject
Add-Member -InputObject $ocEnv -NotePropertyName "ARCGIS_WRITE_ENABLED" -NotePropertyValue "false"

$serverOpenCode = New-Object PSObject
Add-Member -InputObject $serverOpenCode -NotePropertyName "type"        -NotePropertyValue "local"
Add-Member -InputObject $serverOpenCode -NotePropertyName "command"     -NotePropertyValue @($PYTHON_EXE, $MCP_SCRIPT)
Add-Member -InputObject $serverOpenCode -NotePropertyName "environment" -NotePropertyValue $ocEnv

$configured = [System.Collections.Generic.List[string]]::new()
$skipped    = [System.Collections.Generic.List[string]]::new()

# ---- VS Code -----------------------------------------------------------------
$vsCodeSettings = Join-Path $env:APPDATA "Code\User\settings.json"
$vsCodeBin      = Get-CmdPath "code"
$vsCodeFound    = $vsCodeBin -or
                  (Test-Path "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe") -or
                  (Test-Path "$env:ProgramFiles\Microsoft VS Code\Code.exe") -or
                  (Test-Path (Split-Path $vsCodeSettings -Parent))

if ($vsCodeFound) {
    try {
        Merge-VsCodeSettings -SettingsPath $vsCodeSettings `
                             -ServerKey "arcgis-mcp" `
                             -ServerEntry $serverBase
        Write-Ok "VS Code configurado"
        $configured.Add("VS Code")
    } catch {
        Write-Warn "VS Code: error -> $_"
    }
} else {
    Write-Skip "VS Code - no encontrado"
    $skipped.Add("VS Code")
}

# ---- Claude Desktop ----------------------------------------------------------
$claudeConfig = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$claudeFound  = (Test-Path "$env:LOCALAPPDATA\AnthropicClaude\claude.exe") -or
                (Test-Path "$env:ProgramFiles\Claude\claude.exe") -or
                (Test-Path (Split-Path $claudeConfig -Parent))

if ($claudeFound) {
    try {
        Merge-McpJson -ConfigPath $claudeConfig -ServerKey "arcgis-mcp" `
                      -ServerEntry $serverBase -RootKey "mcpServers"
        Write-Ok "Claude Desktop configurado"
        Write-Warn "Claude Desktop: reinicia la app para aplicar cambios"
        $configured.Add("Claude Desktop")
    } catch {
        Write-Warn "Claude Desktop: error -> $_"
    }
} else {
    Write-Skip "Claude Desktop - no encontrado"
    $skipped.Add("Claude Desktop")
}

# ---- Cursor ------------------------------------------------------------------
$cursorConfig = Join-Path $env:USERPROFILE ".cursor\mcp.json"
$cursorBin    = Get-CmdPath "cursor"
$cursorFound  = $cursorBin -or
                (Test-Path "$env:LOCALAPPDATA\Programs\cursor\Cursor.exe") -or
                (Test-Path "$env:ProgramFiles\Cursor\Cursor.exe") -or
                (Test-Path (Split-Path $cursorConfig -Parent))

if ($cursorFound) {
    try {
        Merge-McpJson -ConfigPath $cursorConfig -ServerKey "arcgis-mcp" `
                      -ServerEntry $serverBase -RootKey "mcpServers"
        Write-Ok "Cursor configurado"
        $configured.Add("Cursor")
    } catch {
        Write-Warn "Cursor: error -> $_"
    }
} else {
    Write-Skip "Cursor - no encontrado"
    $skipped.Add("Cursor")
}

# ---- Claude Code (CLI) -------------------------------------------------------
$claudeCodeExe = Get-CmdPath "claude"

if ($claudeCodeExe) {
    try {
        $addArgs = @(
            "mcp", "add",
            "--scope", "user",
            "--transport", "stdio",
            "--env", "ARCGIS_WRITE_ENABLED=false",
            "arcgis-mcp", "--",
            $PYTHON_EXE, $MCP_SCRIPT
        )
        & $claudeCodeExe @addArgs 2>$null
        Write-Ok "Claude Code (CLI) configurado"
        $configured.Add("Claude Code")
    } catch {
        Write-Warn "Claude Code: error -> $_"
    }
} else {
    Write-Skip "Claude Code (CLI) - no encontrado"
    $skipped.Add("Claude Code")
}

# ---- Codex CLI ---------------------------------------------------------------
$codexConfig = Join-Path $env:USERPROFILE ".codex\config.toml"
$codexBin    = Get-CmdPath "codex"
$codexFound  = $codexBin -or (Test-Path (Split-Path $codexConfig -Parent))

if ($codexFound) {
    try {
        Merge-CodexToml -ConfigPath $codexConfig `
                        -PythonExe $PYTHON_EXE -ScriptPath $MCP_SCRIPT
        Write-Ok "Codex configurado"
        $configured.Add("Codex")
    } catch {
        Write-Warn "Codex: error -> $_"
    }
} else {
    Write-Skip "Codex CLI - no encontrado"
    $skipped.Add("Codex")
}

# ---- OpenCode ----------------------------------------------------------------
$openCodeConfig = Join-Path $env:USERPROFILE ".config\opencode\opencode.json"
$openCodeBin    = Get-CmdPath "opencode"
$openCodeFound  = $openCodeBin -or (Test-Path (Split-Path $openCodeConfig -Parent))

if ($openCodeFound) {
    try {
        Merge-McpJson -ConfigPath $openCodeConfig -ServerKey "arcgis-mcp" `
                      -ServerEntry $serverOpenCode -RootKey "mcp"
        Write-Ok "OpenCode configurado"
        $configured.Add("OpenCode")
    } catch {
        Write-Warn "OpenCode: error -> $_"
    }
} else {
    Write-Skip "OpenCode - no encontrado"
    $skipped.Add("OpenCode")
}

# ---- OpenClaw ----------------------------------------------------------------
$openClawConfig = Join-Path $env:APPDATA "OpenClaw\mcp.json"
$openClawAlt    = Join-Path $env:USERPROFILE ".openclaw\mcp.json"

$openClawBin   = Get-CmdPath "openclaw"
$openClawFound = $openClawBin -or
                 (Test-Path "$env:LOCALAPPDATA\Programs\OpenClaw") -or
                 (Test-Path "$env:ProgramFiles\OpenClaw") -or
                 (Test-Path (Split-Path $openClawConfig -Parent)) -or
                 (Test-Path (Split-Path $openClawAlt -Parent))

$usedClawPath = if (Test-Path (Split-Path $openClawAlt -Parent)) { $openClawAlt } else { $openClawConfig }

if ($openClawFound) {
    try {
        Merge-McpJson -ConfigPath $usedClawPath -ServerKey "arcgis-mcp" `
                      -ServerEntry $serverBase -RootKey "mcpServers"
        Write-Ok "OpenClaw configurado"
        $configured.Add("OpenClaw")
    } catch {
        Write-Warn "OpenClaw: error -> $_"
    }
} else {
    Write-Skip "OpenClaw - no encontrado"
    $skipped.Add("OpenClaw")
}

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------

Write-Header "INSTALACION COMPLETADA"

Write-Host ""
Write-Host "  Python : $PYTHON_EXE" -ForegroundColor DarkGray
Write-Host "  Script : $MCP_SCRIPT"  -ForegroundColor DarkGray
Write-Host ""

if ($configured.Count -gt 0) {
    Write-Host "  IDEs configurados:" -ForegroundColor Green
    foreach ($ide in $configured) { Write-Host "    + $ide" -ForegroundColor Green }
}

if ($skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "  No encontrados (instalar y volver a ejecutar si los necesitas):" -ForegroundColor DarkGray
    foreach ($ide in $skipped) { Write-Host "    - $ide" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "  PROXIMOS PASOS:" -ForegroundColor Cyan
Write-Host "  1. Abre ArcGIS Pro y conectate a tu portal." -ForegroundColor White
Write-Host "  2. Reinicia los IDEs configurados arriba." -ForegroundColor White
Write-Host "  3. Busca 'arcgis-mcp' en la lista de servidores MCP." -ForegroundColor White
Write-Host "  4. Prueba con: 'con que usuario estoy conectado?'" -ForegroundColor White
Write-Host ""

Read-Host "  Presiona ENTER para cerrar"
