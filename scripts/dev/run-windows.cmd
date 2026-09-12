@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    "%REPO_ROOT%\.venv\Scripts\python.exe" -m exam_grader %*
) else (
    where uv >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        uv run exam-grader %*
    ) else (
        echo [ERROR] Neither .venv nor uv found. Please run 'uv sync --extra dev'.
        exit /b 1
    )
)
