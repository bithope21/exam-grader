<#
.SYNOPSIS
    Windows Development Launcher for Exam Grader.
.DESCRIPTION
    Launches Exam Grader directly from source using the local environment (.venv or uv).
.PARAMETER SelfCheck
    Run startup self-check diagnostics without GUI.
.PARAMETER SmokeUI
    Open GUI and automatically close after 700ms for verification.
.PARAMETER DataDir
    Override application data directory.
.EXAMPLE
    .\scripts\dev\run-windows.ps1
.EXAMPLE
    .\scripts\dev\run-windows.ps1 -SelfCheck
.EXAMPLE
    .\scripts\dev\run-windows.ps1 -SmokeUI
#>
[CmdletBinding()]
param(
    [switch]$SelfCheck,
    [switch]$SmokeUI,
    [string]$DataDir,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

$PyArgs = @()
if ($SelfCheck) { $PyArgs += "--self-check" }
if ($SmokeUI)   { $PyArgs += "--smoke-ui" }
if ($DataDir)   { $PyArgs += @("--data-dir", $DataDir) }
if ($ExtraArgs) { $PyArgs += $ExtraArgs }

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Push-Location $RepoRoot
try {
    if (Test-Path $VenvPython) {
        & $VenvPython -m exam_grader @PyArgs
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv run exam-grader @PyArgs
    } else {
        Write-Error "Could not find .venv or uv. Please run 'uv sync --extra dev' to initialize the environment."
        exit 1
    }
} finally {
    Pop-Location
}
