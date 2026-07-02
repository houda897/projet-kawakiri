@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "INSTALL_TARGET=."
if "%~1"=="--dev" (
    set "INSTALL_TARGET=.[dev]"
) else if not "%~1"=="" (
    echo Usage: install.bat [--dev]
    exit /b 2
)

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo Python 3.10 or later is required.
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Kawakiri requires Python 3.10 or later.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip install -e "%INSTALL_TARGET%"
if errorlevel 1 exit /b 1

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo Created .env from .env.example.
) else (
    echo Keeping existing .env configuration.
)

echo.
echo Kawakiri installation completed.
echo Activate the environment with: .venv\Scripts\activate
echo Then verify the CLI with: kawakiri --help
echo Run the bundled example with: kawakiri run-all code/data --report example-report.json

endlocal
