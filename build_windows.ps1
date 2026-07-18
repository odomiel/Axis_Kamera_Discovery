<#!/usr/bin/env powershell
# -*- coding: utf-8 -*-
# =============================================================================
# build_windows.ps1 - Automatisiertes Build-Skript für Axis_Kamera_Discovery
# =============================================================================
# Erstellt zwei Windows-Executables:
#   - Axis_Kamera_Discovery.exe      (GUI, ohne Konsolenfenster)
#   - Axis_Kamera_Discovery_cli.exe  (CLI, mit Konsolenfenster)
#
# Voraussetzung: Python 3.14 (mit Tkinter für GUI)
# =============================================================================

<#PSScriptInfo
.VERSION 1.0.0
.GUID file://build_windows.ps1
.AUTHOR Thomas
.DESCRIPTION Build-Skript für Axis_Kamera_Discovery Windows-Executables
#>

param (
    [switch]$ForceReinstall,  # Erzwinge Neuinstallation der Abhängigkeiten
    [switch]$Clean,          # Lösche Build- und Dist-Ordner vor dem Build
    [string]$PythonPath     # Manuell Pfad zu python.exe angeben
)

# =============================================================================
# Konfiguration
# =============================================================================
$ProjectDir = $PSScriptRoot
$SpecFile = "Axis_Kamera_Discovery.spec"
$DistDir = "dist"
$BuildDir = "build"

$PythonVersion = "3.14"

# Standard-Pfade für Python 3.14
$DefaultPythonPaths = @(
    "${env:ProgramFiles}\Python314\python.exe",
    "${env:LocalAppData}\Programs\Python\Python314\python.exe",
    "${env:USERPROFILE}\AppData\Local\Programs\Python\Python314\python.exe"
)

# =============================================================================
# Funktionen
# =============================================================================

function Write-Header {
    param([string]$Message)
    Write-Host "`n===============================================================================" -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor White
    Write-Host "===============================================================================" -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "  [FEHLER] $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Gray
}

function Find-Python {
    param([string]$CustomPath)

    if (-not [string]::IsNullOrEmpty($CustomPath) -and (Test-Path $CustomPath)) {
        return $CustomPath
    }

    # Python-Launcher: waehlt die geforderte Version auch dann zuverlaessig aus,
    # wenn mehrere Versionen installiert sind (das python.exe im PATH ist oft eine
    # aeltere -- damit entstuende eine .exe gegen die falsche Python-Version).
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $launched = & py "-$PythonVersion" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($launched) -and (Test-Path $launched)) {
            return $launched
        }
    }

    # Suche in Standardpfaden
    foreach ($path in $DefaultPythonPaths) {
        if (Test-Path $path) {
            return $path
        }
    }

    # Suche in PATH (nur brauchbar, wenn es die geforderte Version ist -- das
    # prueft der Aufrufer per Test-PythonVersion)
    $pythonInPath = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonInPath) {
        return $pythonInPath.Source
    }

    return $null
}

function Test-PythonVersion {
    param([string]$PythonExe, [string]$RequiredVersion)
    
    try {
        $versionOutput = & $PythonExe --version 2>$null
        if ($versionOutput -match "Python (\d+\.\d+)") {
            $installedVersion = $matches[1]
            $required = [version]$RequiredVersion
            $installed = [version]$installedVersion
            
            if ($installed -ge $required) {
                return $true
            } else {
                Write-ErrorMsg "Python $RequiredVersion oder hoher erforderlich (gefunden: $installedVersion)"
                return $false
            }
        }
        return $false
    } catch {
        return $false
    }
}


# =============================================================================
# Hauptskript
# =============================================================================

Write-Header "Axis_Kamera_Discovery - Windows Build"

# Arbeitsverzeichnis setzen
Set-Location $ProjectDir

# 1. Python finden
Write-Info "Suche nach Python $PythonVersion..."
$pythonExe = Find-Python $PythonPath

if (-not $pythonExe) {
    Write-ErrorMsg "Python $PythonVersion nicht gefunden!"
    Write-Info "Bitte installieren: https://www.python.org/downloads/"
    Write-Info "Oder geben Sie den Pfad mit -PythonPath an."
    exit 1
}

if (-not (Test-PythonVersion $pythonExe $PythonVersion)) {
    Write-Info "PyInstaller baut die .exe immer fuer genau diesen Interpreter."
    Write-Info "Installieren Sie Python $PythonVersion oder geben Sie ihn mit -PythonPath an."
    exit 1
}

Write-Step "Python gefunden: $pythonExe"
& $pythonExe --version | ForEach-Object { Write-Info $_ }

# 2. Optional: Bereiche bereinigen
if ($Clean) {
    Write-Info "Bereinige Build- und Dist-Ordner..."
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Step "Bereiche bereinigt"
}

# 3. Abhängigkeiten installieren
Write-Info "Installiere Abhaengigkeiten..."
$dependencies = @("pyinstaller", "zeroconf", "prettytable", "ifaddr", "sv-ttk")

if ($ForceReinstall) {
    & $pythonExe -m pip install --force-reinstall $dependencies
} else {
    & $pythonExe -m pip install $dependencies
}

if ($LASTEXITCODE -ne 0) {
    Write-ErrorMsg "Fehler beim Installieren der Abhängigkeiten"
    exit 1
}
Write-Step "Abhängigkeiten installiert"

# 4. PyInstaller ausfuehren
# Aufruf ueber "-m PyInstaller" statt ueber pyinstaller.exe: nur so ist garantiert,
# dass mit dem oben ausgewaehlten Interpreter gebaut wird und nicht mit einem
# anderen aus dem PATH.
Write-Info "Starte Build mit PyInstaller..."
Write-Info "Fuehre aus: $pythonExe -m PyInstaller --noconfirm $SpecFile"

& $pythonExe -m PyInstaller --noconfirm $SpecFile

if ($LASTEXITCODE -ne 0) {
    Write-ErrorMsg "Build fehlgeschlagen (Exit-Code: $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Step "Build erfolgreich"

# 5. Ergebnis anzeigen
Write-Header "Build abgeschlossen"

# Die Spec haengt die Versionsnummer an die Dateinamen an
# (Axis_Kamera_Discovery_<version>.exe) -- daher per Muster suchen.
$cliExe = Get-ChildItem -Path $DistDir -Filter "Axis_Kamera_Discovery_cli_*.exe" -ErrorAction SilentlyContinue |
          Select-Object -First 1
$guiExe = Get-ChildItem -Path $DistDir -Filter "Axis_Kamera_Discovery_*.exe" -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -notlike "Axis_Kamera_Discovery_cli_*" } |
          Select-Object -First 1

if ($guiExe) {
    $guiSizeRounded = [math]::Round($guiExe.Length / 1MB, 2)
    Write-Step "$($guiExe.Name) erstellt ($guiSizeRounded MB)"
} else {
    Write-ErrorMsg "GUI-Exe nicht gefunden"
}

if ($cliExe) {
    $cliSizeRounded = [math]::Round($cliExe.Length / 1MB, 2)
    Write-Step "$($cliExe.Name) erstellt ($cliSizeRounded MB)"
} else {
    Write-ErrorMsg "CLI-Exe nicht gefunden"
}

Write-Host "`n  Die Executables liegen in: $ProjectDir\$DistDir\`n" -ForegroundColor Yellow

# 6. Optional: Datei-Explorer öffnen
$openExplorer = Read-Host "Soll der Dist-Ordner geöffnet werden? (j/n)"
if ($openExplorer -eq "j" -or $openExplorer -eq "J") {
    Invoke-Item $DistDir
}

exit 0
