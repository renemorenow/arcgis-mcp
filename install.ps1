# install.ps1 - ArcGIS MCP: Instalador automatico
#
# Uso: clic derecho -> "Ejecutar con PowerShell"
#      o desde terminal: .\install.ps1
#
# Que hace:
#   1. Detecta Python automaticamente en este orden:
#        a) Entorno conda de ArcGIS Pro >= 3.3 (conexion GIS("Pro") soportada)
#        b) Python externo del sistema / Miniconda / Anaconda (3.11+)
#           si ArcGIS Pro es < 3.3 o no existe
#        c) Instala Python 3.12 via winget si esta disponible
#        d) Muestra link de descarga y permite ingresar ruta manual
#   2. Instala las dependencias necesarias
#   3. Configura los IDEs instalados en tu maquina
#      (VS Code, Claude Desktop, Cursor, Codex, Claude Code, OpenCode, OpenClaw)
#
# No requiere ArcGIS Pro. Sin el, el modo GIS("Pro") no estara disponible,
# pero OAuth2, API Key, perfil y usuario/contrasena funcionan igual.

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

function Get-PythonVersionInfo {
    param([string]$PythonExe)

    try {
        $pyVerStr = & $PythonExe --version 2>&1
        if ($pyVerStr -match 'Python (\d+)\.(\d+)(?:\.(\d+))?') {
            return [PSCustomObject]@{
                Major   = [int]$Matches[1]
                Minor   = [int]$Matches[2]
                Patch   = if ($Matches[3]) { [int]$Matches[3] } else { 0 }
                Display = "$($Matches[1]).$($Matches[2])"
                Raw     = $pyVerStr
            }
        }
    } catch {
    }

    return $null
}

function Test-MinPython {
    param(
        [string]$PythonExe,
        [int]$MinMajor,
        [int]$MinMinor
    )

    $info = Get-PythonVersionInfo -PythonExe $PythonExe
    if (-not $info) { return $false }
    if ($info.Major -gt $MinMajor) { return $true }
    if ($info.Major -eq $MinMajor -and $info.Minor -ge $MinMinor) { return $true }
    return $false
}

function Get-ArcGISProEnvInfo {
    param([string]$PythonExe)

    try {
        $proVersion = & $PythonExe -c "from importlib.metadata import PackageNotFoundError, version;`ntry:`n    print(version('arcgispro'))`nexcept PackageNotFoundError:`n    print('')" 2>$null
        $proVersion = "$proVersion".Trim()
        if (-not $proVersion) { return $null }

        $majorMinor = ($proVersion -split '\.') | Select-Object -First 2
        if ($majorMinor.Count -lt 2) { return $null }

        $normalized = "$($majorMinor[0]).$($majorMinor[1])"
        $verObj = [version]$normalized

        return [PSCustomObject]@{
            PythonExe       = $PythonExe
            ProVersion      = $normalized
            SupportsMcp     = ($verObj -ge [version]'3.3')
            DisableProAuth  = ($verObj -lt [version]'3.3')
        }
    } catch {
        return $null
    }
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
    param(
        [string]$ConfigPath,
        [string]$PythonExe,
        [string]$ScriptPath,
        [bool]$DisableProMode,
        [string]$RuntimeMode,
        [string]$ProVersion
    )

    $dir = Split-Path $ConfigPath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    $pyEscaped = $PythonExe  -replace '\\', '\\'
    $scEscaped = $ScriptPath -replace '\\', '\\'

    $envBlock = @(
        '[mcp_servers.arcgis-mcp.env]',
        'ARCGIS_WRITE_ENABLED = "false"',
        ('ARCGIS_DISABLE_PRO = "' + $DisableProMode.ToString().ToLower() + '"'),
        ('ARCGIS_RUNTIME_MODE = "' + $RuntimeMode + '"')
    )

    if ($ProVersion) {
        $envBlock += ('ARCGIS_PRO_VERSION = "' + $ProVersion + '"')
    }

    $newBlock = "`n[mcp_servers.arcgis-mcp]`ncommand = `"$pyEscaped`"`nargs = [`"$scEscaped`"]`n`n" + ($envBlock -join "`n") + "`n"

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
# PASO 1: Detectar Python (ArcGIS Pro, sistema o instalar)
# ---------------------------------------------------------------------------

Write-Header "PASO 1 - Detectando Python y compatibilidad con ArcGIS Pro"

$PYTHON_EXE     = $null
$HAS_ARCGIS_PRO = $false
$ARCGIS_PRO_VERSION = $null
$PRO_SUPPORTS_INTEGRATED_RUNTIME = $false
$DISABLE_PRO_MODE = $false
$RUNTIME_MODE = "external"
$candidates     = [System.Collections.Generic.List[string]]::new()
# — A) Buscar entornos conda de ArcGIS Pro —
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

$esriPF = "C:\Program Files\ArcGIS\Pro\bin\Python\envs"
if (Test-Path $esriPF) {
    Get-ChildItem $esriPF -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $py = Join-Path $_.FullName "python.exe"
        if (Test-Path $py) { $candidates.Add($py) }
    }
}

# Preferir clone de ArcGIS Pro y decidir segun version
$selectedProPython = $candidates | Where-Object { $_ -like "*clone*" } | Select-Object -First 1
if (-not $selectedProPython) {
    $selectedProPython = $candidates | Select-Object -First 1
}

if ($selectedProPython) {
    $HAS_ARCGIS_PRO = $true
    $selectedProInfo = Get-ArcGISProEnvInfo -PythonExe $selectedProPython

    if ($selectedProInfo) {
        $ARCGIS_PRO_VERSION = $selectedProInfo.ProVersion
        $PRO_SUPPORTS_INTEGRATED_RUNTIME = $selectedProInfo.SupportsMcp
        $DISABLE_PRO_MODE = $selectedProInfo.DisableProAuth

        if ($PRO_SUPPORTS_INTEGRATED_RUNTIME) {
            $PYTHON_EXE = $selectedProPython
            $RUNTIME_MODE = "pro-integrated"
            Write-Ok "ArcGIS Pro $ARCGIS_PRO_VERSION detectado. Se usara su entorno Python: $PYTHON_EXE"
        } else {
            Write-Warn "ArcGIS Pro $ARCGIS_PRO_VERSION detectado. Las versiones inferiores a 3.3 usan Python externo compatible con MCP."
            Write-Host "  Se buscara o instalara Python 3.11+ fuera del entorno de Pro." -ForegroundColor Yellow
        }
    } else {
        $DISABLE_PRO_MODE = $true
        Write-Warn "Se detecto un entorno de ArcGIS Pro pero no se pudo determinar su version."
        Write-Host "  Por seguridad se usara Python externo 3.11+ y se deshabilitara GIS('Pro')." -ForegroundColor Yellow
    }
}

if (-not $PYTHON_EXE) {
    if ($HAS_ARCGIS_PRO) {
        Write-Skip "Buscando Python externo compatible con MCP..."
    } else {
        Write-Skip "ArcGIS Pro no encontrado. Buscando Python del sistema..."
    }

    # — B) Buscar Python en PATH —
    foreach ($cmd in @("python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $PYTHON_EXE = $found.Source; break }
    }

    # — C) Buscar en ubicaciones comunes de instalacion —
    if (-not $PYTHON_EXE) {
        $commonPatterns = @(
            "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
            "$env:ProgramFiles\Python3*\python.exe",
            "C:\Python3*\python.exe",
            "$env:USERPROFILE\miniconda3\python.exe",
            "$env:LOCALAPPDATA\miniconda3\python.exe",
            "$env:USERPROFILE\anaconda3\python.exe",
            "$env:LOCALAPPDATA\anaconda3\python.exe",
            "$env:ProgramData\miniconda3\python.exe",
            "$env:ProgramData\anaconda3\python.exe"
        )
        foreach ($pattern in $commonPatterns) {
            $hit = Resolve-Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { $PYTHON_EXE = $hit.Path; break }
        }
    }

    # Validar version (requiere 3.11+ para FastMCP/MCP)
    if ($PYTHON_EXE) {
        $pyInfo = Get-PythonVersionInfo -PythonExe $PYTHON_EXE
        if ($pyInfo) {
            $pyMaj = [int]$pyInfo.Major
            $pyMin = [int]$pyInfo.Minor
            if ($pyMaj -lt 3 -or ($pyMaj -eq 3 -and $pyMin -lt 11)) {
                Write-Warn "Python $pyMaj.$pyMin encontrado pero el runtime MCP requiere 3.11+. Ignorando."
                $PYTHON_EXE = $null
            } else {
                Write-Ok "Python $pyMaj.$pyMin del sistema: $PYTHON_EXE"
                if ($HAS_ARCGIS_PRO -and $DISABLE_PRO_MODE) {
                    $RUNTIME_MODE = "external-legacy-pro"
                    Write-Warn "ArcGIS Pro < 3.3 detectado: se usara Python externo y se deshabilitara GIS('Pro')."
                    Write-Warn "OAuth2, API Key, perfil, token y usuario/contrasena funcionan igual."
                } else {
                    $RUNTIME_MODE = "external"
                    Write-Warn "Sin ArcGIS Pro compatible, el modo GIS('Pro') no estara disponible."
                    Write-Warn "OAuth2, API Key, perfil y usuario/contrasena funcionan igual."
                }
            }
        } else {
            $PYTHON_EXE = $null
        }
    }

    # — D) Instalar Python si no hay nada —
    if (-not $PYTHON_EXE) {
        Write-Fail "No se encontro Python 3.11+ compatible con MCP en este equipo."
        Write-Host ""

        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            Write-Host "  winget detectado. Instalando Python 3.12 automaticamente..." -ForegroundColor Cyan
            Write-Host ""
            winget install --id Python.Python.3.12 --silent --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -eq 0) {
                # Recargar PATH en la sesion actual
                $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                            [System.Environment]::GetEnvironmentVariable("PATH", "User")
                $found = Get-Command python -ErrorAction SilentlyContinue
                if ($found) {
                    $PYTHON_EXE = $found.Source
                    $RUNTIME_MODE = if ($HAS_ARCGIS_PRO -and $DISABLE_PRO_MODE) { "external-legacy-pro" } else { "external" }
                    Write-Ok "Python instalado y listo: $PYTHON_EXE"
                } else {
                    Write-Warn "Python instalado. Cierra esta ventana, abre PowerShell nuevamente"
                    Write-Warn "y ejecuta el script otra vez para que el PATH se actualice."
                    Read-Host "`nPresiona ENTER para salir"
                    exit 0
                }
            } else {
                Write-Warn "winget no pudo completar la instalacion."
            }
        }

        # Fallback: link de descarga + ruta manual
        if (-not $PYTHON_EXE) {
            Write-Host ""
            Write-Host "  Instala Python manualmente (marcar 'Add Python to PATH'):" -ForegroundColor Yellow
            Write-Host "  https://www.python.org/downloads/release/python-3129/" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  Luego vuelve a ejecutar este script." -ForegroundColor Yellow
            Write-Host "  O bien ingresa ahora la ruta al python.exe que quieras usar:" -ForegroundColor Yellow
            $manual = Read-Host "  Ruta a python.exe (ENTER para cancelar)"
            if ($manual -and (Test-Path $manual)) {
                $PYTHON_EXE = $manual
                if (-not (Test-MinPython -PythonExe $PYTHON_EXE -MinMajor 3 -MinMinor 11)) {
                    Write-Fail "El Python ingresado no cumple el minimo 3.11 requerido por MCP."
                    Read-Host "`nPresiona ENTER para salir"
                    exit 1
                }
                $RUNTIME_MODE = if ($HAS_ARCGIS_PRO -and $DISABLE_PRO_MODE) { "external-legacy-pro" } else { "external" }
                Write-Ok "Usando: $PYTHON_EXE"
            } else {
                Write-Fail "Sin Python no es posible continuar. Abortando."
                Read-Host "`nPresiona ENTER para salir"
                exit 1
            }
        }
    }
}

$arcgisVersion = & $PYTHON_EXE -c "from importlib.metadata import PackageNotFoundError, version;`ntry:`n    print(version('arcgis'))`nexcept PackageNotFoundError:`n    print('')" 2>$null
if ($arcgisVersion) {
    Write-Ok "Paquete arcgis $arcgisVersion detectado"
} else {
    Write-Skip "Paquete arcgis no instalado aun. Se instalara en el siguiente paso."
}

# ---------------------------------------------------------------------------
# PASO 2: Instalar dependencias
# ---------------------------------------------------------------------------

Write-Header "PASO 2 - Instalando dependencias"

$installScript = Join-Path $SCRIPT_DIR "install_requirements.py"
Write-Host "  Ejecutando instalacion inteligente de dependencias ..." -ForegroundColor DarkGray

try {
    & $PYTHON_EXE $installScript
    if ($LASTEXITCODE -ne 0) { throw "install_requirements.py retorno codigo $LASTEXITCODE" }
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

$pyScript = @"
import sys
import traceback

sys.path.insert(0, r'$SCRIPT_DIR')

try:
    from _server import mcp  # noqa: F401
    import _auth  # noqa: F401
    import tools  # noqa: F401
    print('OK')
except Exception:
    print('VERIFY_ERROR')
    print(traceback.format_exc())
"@

$verifyResult = & $PYTHON_EXE -c $pyScript 2>&1

if ($verifyResult -match "OK") {
    Write-Ok "Servidor MCP verificado"
} else {
    Write-Warn "Verificacion con advertencias o error de importacion"
    Write-Host "  $verifyResult" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# PASO 4: Configurar IDEs
# ---------------------------------------------------------------------------

Write-Header "PASO 4 - Configurando IDEs"

# Objeto base del servidor (compatible PS 5.1 - sin hashtable cast a PSObject)
$baseEnv = New-Object PSObject
Add-Member -InputObject $baseEnv -NotePropertyName "ARCGIS_WRITE_ENABLED" -NotePropertyValue "false"
Add-Member -InputObject $baseEnv -NotePropertyName "ARCGIS_DISABLE_PRO" -NotePropertyValue ($DISABLE_PRO_MODE.ToString().ToLower())
Add-Member -InputObject $baseEnv -NotePropertyName "ARCGIS_RUNTIME_MODE" -NotePropertyValue $RUNTIME_MODE
if ($ARCGIS_PRO_VERSION) {
    Add-Member -InputObject $baseEnv -NotePropertyName "ARCGIS_PRO_VERSION" -NotePropertyValue $ARCGIS_PRO_VERSION
}

$serverBase = New-Object PSObject
Add-Member -InputObject $serverBase -NotePropertyName "command" -NotePropertyValue $PYTHON_EXE
Add-Member -InputObject $serverBase -NotePropertyName "args"    -NotePropertyValue @($MCP_SCRIPT)
Add-Member -InputObject $serverBase -NotePropertyName "env"     -NotePropertyValue $baseEnv

# OpenCode usa "type" + command como array + "environment"
$ocEnv = New-Object PSObject
Add-Member -InputObject $ocEnv -NotePropertyName "ARCGIS_WRITE_ENABLED" -NotePropertyValue "false"
Add-Member -InputObject $ocEnv -NotePropertyName "ARCGIS_DISABLE_PRO" -NotePropertyValue ($DISABLE_PRO_MODE.ToString().ToLower())
Add-Member -InputObject $ocEnv -NotePropertyName "ARCGIS_RUNTIME_MODE" -NotePropertyValue $RUNTIME_MODE
if ($ARCGIS_PRO_VERSION) {
    Add-Member -InputObject $ocEnv -NotePropertyName "ARCGIS_PRO_VERSION" -NotePropertyValue $ARCGIS_PRO_VERSION
}

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
            "--env", ("ARCGIS_DISABLE_PRO=" + $DISABLE_PRO_MODE.ToString().ToLower()),
            "--env", ("ARCGIS_RUNTIME_MODE=" + $RUNTIME_MODE),
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
                        -PythonExe $PYTHON_EXE -ScriptPath $MCP_SCRIPT `
                        -DisableProMode $DISABLE_PRO_MODE -RuntimeMode $RUNTIME_MODE `
                        -ProVersion $ARCGIS_PRO_VERSION
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
# PASO 5: Desplegar agente arcgis-apyt-dev en los IDEs detectados
# ---------------------------------------------------------------------------

Write-Header "PASO 5 - Instalando agente arcgis-apyt-dev"

$agentsDir    = Join-Path $SCRIPT_DIR "agents"
$agentsDeployed = [System.Collections.Generic.List[string]]::new()

# ---- VS Code ----------------------------------------------------------------
if ($configured -contains "VS Code") {
    $src  = Join-Path $agentsDir "arcgis-apyt-dev.vscode.agent.md"
    $dest = Join-Path $env:APPDATA "Code\User\prompts\arcgis-apyt-dev.agent.md"
    try {
        $promptsDir = Split-Path $dest -Parent
        if (-not (Test-Path $promptsDir)) { New-Item -ItemType Directory -Path $promptsDir -Force | Out-Null }
        Copy-Item $src $dest -Force
        Write-Ok "Agente VS Code desplegado"
        $agentsDeployed.Add("VS Code")
    } catch { Write-Warn "Agente VS Code: error -> $_" }
}

# ---- Cursor -----------------------------------------------------------------
if ($configured -contains "Cursor") {
    $src  = Join-Path $agentsDir "arcgis-apyt-dev.cursor.mdc"
    $dest = Join-Path $env:USERPROFILE ".cursor\rules\arcgis-apyt-dev.mdc"
    try {
        $rulesDir = Split-Path $dest -Parent
        if (-not (Test-Path $rulesDir)) { New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null }
        Copy-Item $src $dest -Force
        Write-Ok "Agente Cursor desplegado"
        $agentsDeployed.Add("Cursor")
    } catch { Write-Warn "Agente Cursor: error -> $_" }
}

# ---- Claude Code ------------------------------------------------------------
if ($configured -contains "Claude Code") {
    $src      = Join-Path $agentsDir "arcgis-apyt-dev.claude.md"
    $dest     = Join-Path $env:USERPROFILE ".claude\agents\arcgis-apyt-dev.md"
    try {
        $agDir = Split-Path $dest -Parent
        if (-not (Test-Path $agDir)) { New-Item -ItemType Directory -Path $agDir -Force | Out-Null }
        Copy-Item $src $dest -Force
        Write-Ok "Agente Claude Code desplegado"
        $agentsDeployed.Add("Claude Code")
    } catch { Write-Warn "Agente Claude Code: error -> $_" }
}

# ---- Codex ------------------------------------------------------------------
if ($configured -contains "Codex") {
    $src        = Join-Path $agentsDir "arcgis-apyt-dev.codex.md"
    $destAgents = Join-Path $env:USERPROFILE ".codex\AGENTS.md"
    try {
        $block = [System.IO.File]::ReadAllText($src, [System.Text.Encoding]::UTF8)
        if (Test-Path $destAgents) {
            $existing = [System.IO.File]::ReadAllText($destAgents, [System.Text.Encoding]::UTF8)
            if ($existing -notmatch "arcgis-apyt-dev") {
                [System.IO.File]::WriteAllText($destAgents, $existing + "`n" + $block, [System.Text.Encoding]::UTF8)
            }
        } else {
            [System.IO.File]::WriteAllText($destAgents, $block, [System.Text.Encoding]::UTF8)
        }
        Write-Ok "Agente Codex desplegado"
        $agentsDeployed.Add("Codex")
    } catch { Write-Warn "Agente Codex: error -> $_" }
}

if ($agentsDeployed.Count -eq 0) {
    Write-Skip "Ningun IDE compatible detectado para el agente"
}

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------

Write-Header "INSTALACION COMPLETADA"

Write-Host ""
Write-Host "  Python : $PYTHON_EXE" -ForegroundColor DarkGray
Write-Host "  Script : $MCP_SCRIPT"  -ForegroundColor DarkGray
Write-Host "  Runtime: $RUNTIME_MODE" -ForegroundColor DarkGray
if ($ARCGIS_PRO_VERSION) {
    Write-Host "  ArcGIS Pro detectado: $ARCGIS_PRO_VERSION" -ForegroundColor DarkGray
}
Write-Host ""

if ($configured.Count -gt 0) {
    Write-Host "  IDEs configurados (MCP):" -ForegroundColor Green
    foreach ($ide in $configured) { Write-Host "    + $ide" -ForegroundColor Green }
}

if ($agentsDeployed.Count -gt 0) {
    Write-Host ""
    Write-Host "  Agente arcgis-apyt-dev desplegado en:" -ForegroundColor Green
    foreach ($ide in $agentsDeployed) { Write-Host "    + $ide" -ForegroundColor Green }
}

if ($skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "  No encontrados (instalar y volver a ejecutar si los necesitas):" -ForegroundColor DarkGray
    foreach ($ide in $skipped) { Write-Host "    - $ide" -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "  PROXIMOS PASOS:" -ForegroundColor Cyan
if ($HAS_ARCGIS_PRO -and -not $DISABLE_PRO_MODE) {
    Write-Host "  1. Abre ArcGIS Pro y conectate a tu portal (modo Pro automatico)." -ForegroundColor White
} elseif ($HAS_ARCGIS_PRO -and $DISABLE_PRO_MODE) {
    Write-Host "  1. ArcGIS Pro < 3.3 detectado: el servidor usara Python externo y NO intentara GIS('Pro')." -ForegroundColor White
    Write-Host "     Configura autenticacion en el .env (OAuth2, API Key, perfil, token o usuario/pass)." -ForegroundColor DarkGray
} else {
    Write-Host "  1. Configura autenticacion en el .env de la carpeta arcgis-mcp." -ForegroundColor White
    Write-Host "     Opcion recomendada (abre navegador, sin contrasena en disco):" -ForegroundColor DarkGray
    Write-Host "       ARCGIS_USE_OAUTH=true" -ForegroundColor DarkGray
    Write-Host "     Otras opciones: ARCGIS_API_KEY, ARCGIS_PROFILE, ARCGIS_USER/PASS" -ForegroundColor DarkGray
}
Write-Host "  2. Reinicia los IDEs configurados arriba." -ForegroundColor White
Write-Host "  3. Busca 'arcgis-mcp' en la lista de servidores MCP." -ForegroundColor White
Write-Host "  4. Prueba con: 'con que usuario estoy conectado?'" -ForegroundColor White
Write-Host ""

Read-Host "  Presiona ENTER para cerrar"
