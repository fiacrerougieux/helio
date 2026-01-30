@echo off
REM Sun Sleuth - Complete Installation Script for Windows
REM Installs everything: Python dependencies, security sandbox, and sets up environment

echo ========================================
echo Sun Sleuth - Complete Installation
echo ========================================
echo.
echo This will install:
echo   1. Python dependencies (pvlib, pandas, numpy, etc.)
echo   2. Security sandbox (pywin32 for Job Objects)
echo   3. Configure environment
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.9+ first.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Step 1/3: Installing Python dependencies...
echo ========================================
echo.

REM Install main dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python dependencies.
    echo Please check your internet connection and try again.
    pause
    exit /b 1
)

echo.
echo Step 2/3: Configuring security sandbox...
echo ========================================
echo.

REM Configure Windows security (no external deps needed)
if exist scripts\install_sandbox.py (
    python scripts\install_sandbox.py
) else (
    echo Sandbox configuration script not found, skipping...
)

if errorlevel 1 (
    echo.
    echo WARNING: Sandbox configuration had issues.
    echo You can still use the system with basic isolation.
    echo.
)

echo.
echo Step 3/3: Testing installation...
echo ========================================
echo.

REM Test basic imports
python -c "import pvlib; import pandas; import numpy; print('✓ Core dependencies OK')"
if errorlevel 1 (
    echo ERROR: Dependency test failed.
    pause
    exit /b 1
)

REM Test OpenRouter client (if API key is set)
python -c "from agent.openrouter_client import OpenRouterClient; print('✓ OpenRouter client OK')" 2>nul
if errorlevel 1 (
    echo ⚠ OpenRouter client not configured (optional - set OPENROUTER_API_KEY to use cloud LLM)
) else (
    echo ✓ OpenRouter client OK
)

REM Test secure executor
python -c "from agent.secure_executor import SecureExecutor; SecureExecutor().test_environment()"

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo You can now run Sun Sleuth:
echo   helio.bat
echo.
echo Or use python directly:
echo   python helio.py
echo.
echo Optional: Set OPENROUTER_API_KEY for cloud LLM access
echo   set OPENROUTER_API_KEY=your-key-here
echo.

pause
