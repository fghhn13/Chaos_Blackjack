@echo off
setlocal
title Chaos Blackjack

rem Always run from the checkout, including when launched by double-click.
pushd "%~dp0"
if errorlevel 1 (
    echo [ERROR] Cannot open the game directory.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYGAME_HIDE_SUPPORT_PROMPT=1"
set "GAME_PYTHON_ARGS="
set "GAME_EXIT_CODE=1"

rem Prefer the project's virtual environment, then the active Python.
if exist ".venv\Scripts\python.exe" (
    set "GAME_PYTHON=.venv\Scripts\python.exe"
    goto check_python
)
if exist "venv\Scripts\python.exe" (
    set "GAME_PYTHON=venv\Scripts\python.exe"
    goto check_python
)
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    set "GAME_PYTHON=python"
    goto check_python
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    set "GAME_PYTHON=py"
    set "GAME_PYTHON_ARGS=-3"
    goto check_python
)
echo [ERROR] Python 3.10 or newer was not found.
echo Install Python with "Add python.exe to PATH", then run this file again.
goto failed

:check_python
"%GAME_PYTHON%" %GAME_PYTHON_ARGS% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The selected Python environment requires Python 3.10 or newer.
    goto failed
)

"%GAME_PYTHON%" %GAME_PYTHON_ARGS% -c "import pygame" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing game dependencies. An internet connection is required.
"%GAME_PYTHON%" %GAME_PYTHON_ARGS% -m pip install -e ".[gui]"
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check the output above.
    goto failed
)

:launch
echo Starting Chaos Blackjack...
"%GAME_PYTHON%" %GAME_PYTHON_ARGS% -m chaos_blackjack.gui %*
set "GAME_EXIT_CODE=%ERRORLEVEL%"
if "%GAME_EXIT_CODE%"=="0" goto finish
echo [ERROR] The game exited with code %GAME_EXIT_CODE%. Check the output above.

:failed
echo.
pause

:finish
popd
endlocal & exit /b %GAME_EXIT_CODE%
