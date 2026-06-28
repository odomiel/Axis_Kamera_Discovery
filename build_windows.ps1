<#!/usr/bin/env powershell
# -*- coding: utf-8 -*-
# =============================================================================
# build_windows.ps1 - Automatisiertes Build-Skript für Axis_Kamera_Discovery
# =============================================================================
# Erstellt zwei Windows-Executables:
#   - Axis_Kamera_Discovery.exe      (GUI, ohne Konsolenfenster)
#   - Axis_Kamera_Discovery_cli.exe  (CLI, mit Konsolenfenster)
#
# Voraussetzung: Python 3.13 (mit Tkinter für GUI)
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

# Standard-Pfade für Python 3.13
$DefaultPythonPaths = @(
    "${env:ProgramFiles}\Python313\python.exe",
    "${env:LocalAppData}\Programs\Python\Python313\python.exe",
    "${env:USERPROFILE}\AppData\Local\Programs\Python\Python313\python.exe"
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
    
    # Suche in Standardpfaden
    foreach ($path in $DefaultPythonPaths) {
        if (Test-Path $path) {
            return $path
        }
    }
    
    # Suche in PATH
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

function Get-PyInstallerPath {
    param([string]$PythonExe)
    
    $pythonDir = [System.IO.Path]::GetDirectoryName($PythonExe)
    $scriptsDir = [System.IO.Path]::Combine($pythonDir, "Scripts")
    $pyinstallerPath = [System.IO.Path]::Combine($scriptsDir, "pyinstaller.exe")
    
    if (Test-Path $pyinstallerPath) {
        return $pyinstallerPath
    }
    
    return "pyinstaller"
}

# =============================================================================
# Hauptskript
# =============================================================================

Write-Header "Axis_Kamera_Discovery - Windows Build"

# Arbeitsverzeichnis setzen
Set-Location $ProjectDir

# 1. Python finden
Write-Info "Suche nach Python 3.13..."
$pythonExe = Find-Python $PythonPath

if (-not $pythonExe) {
    Write-ErrorMsg "Python 3.13 nicht gefunden!"
    Write-Info "Bitte installieren: https://www.python.org/downloads/release/python-31314/"
    Write-Info "Oder geben Sie den Pfad mit -PythonPath an."
    exit 1
}

if (-not (Test-PythonVersion $pythonExe "3.13")) {
    exit 1
}

Write-Step "Python gefunden: $pythonExe"

# 2. Optional: Bereiche bereinigen
if ($Clean) {
    Write-Info "Bereinige Build- und Dist-Ordner..."
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Step "Bereiche bereinigt"
}

# 3. Abhängigkeiten installieren
Write-Info "Installiere Abhaengigkeiten..."
$dependencies = @("pyinstaller", "zeroconf", "prettytable", "ifaddr")

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
Write-Info "Starte Build mit PyInstaller..."
$pyinstallerExe = Get-PyInstallerPath $pythonExe

$buildCommand = "$pyinstallerExe --noconfirm $SpecFile"
Write-Info "Führe aus: $buildCommand"

Invoke-Expression $buildCommand

if ($LASTEXITCODE -ne 0) {
    Write-ErrorMsg "Build fehlgeschlagen (Exit-Code: $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Step "Build erfolgreich"

# 5. Ergebnis anzeigen
Write-Header "Build abgeschlossen"

$guiExePath = "$DistDir\Axis_Kamera_Discovery.exe"
$cliExePath = "$DistDir\Axis_Kamera_Discovery_cli.exe"

if (Test-Path $guiExePath) {
    $guiSize = (Get-Item $guiExePath).Length / 1MB
    $guiSizeRounded = [math]::Round($guiSize, 2)
    Write-Step "Axis_Kamera_Discovery.exe erstellt ($guiSizeRounded MB)"
} else {
    Write-ErrorMsg "Axis_Kamera_Discovery.exe nicht gefunden"
}

if (Test-Path $cliExePath) {
    $cliSize = (Get-Item $cliExePath).Length / 1MB
    $cliSizeRounded = [math]::Round($cliSize, 2)
    Write-Step "Axis_Kamera_Discovery_cli.exe erstellt ($cliSizeRounded MB)"
} else {
    Write-ErrorMsg "Axis_Kamera_Discovery_cli.exe nicht gefunden"
}

Write-Host "`n  Die Executables liegen in: $ProjectDir\$DistDir\`n" -ForegroundColor Yellow

# 6. Optional: Datei-Explorer öffnen
$openExplorer = Read-Host "Soll der Dist-Ordner geöffnet werden? (j/n)"
if ($openExplorer -eq "j" -or $openExplorer -eq "J") {
    Invoke-Item $DistDir
}

exit 0
