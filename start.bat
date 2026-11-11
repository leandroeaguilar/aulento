@echo off
setlocal enabledelayedexpansion
title Aulento - Sistema Maestro de Estudio
color 0B

echo ===============================================================
echo            Aulento - Sistema Maestro de Estudio
echo ===============================================================
echo.

REM 1. Asegurar que estamos en la carpeta del proyecto
cd /d "%~dp0"

set "VERSION_MINIMA=import sys; sys.exit(sys.version_info < (3, 11))"
set "VENV_PYTHON=.venv\Scripts\python.exe"
set "ARCHIVO_DE_HUELLA=.venv\.requirements.sha256"

REM 2. Verificar Python 3.11 o posterior
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no se encuentra en el PATH.
    echo Por favor instala Python 3.11+ desde https://www.python.org/
    pause
    exit /b 1
)
python -c "!VERSION_MINIMA!"
if errorlevel 1 (
    echo [ERROR] Aulento necesita Python 3.11 o posterior. Version encontrada:
    python -V
    pause
    exit /b 1
)

REM 3. Crear entorno virtual si no existe, y verificar su version de Python
if not exist "!VENV_PYTHON!" (
    echo [*] Creando entorno virtual local .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    REM Un entorno recreado esta vacio aunque haya quedado la huella de la instalacion anterior
    if exist "!ARCHIVO_DE_HUELLA!" del "!ARCHIVO_DE_HUELLA!"
)
"!VENV_PYTHON!" -c "!VERSION_MINIMA!"
if errorlevel 1 (
    echo [ERROR] El entorno .venv usa una version de Python anterior a la 3.11.
    echo Borra la carpeta .venv y volve a ejecutar este script.
    pause
    exit /b 1
)

REM 4. Dependencias: se instalan al crear el entorno y se reinstalan si requirements.txt o pyproject.toml cambiaron
set "HUELLA_REQUIREMENTS="
for /f "skip=1 delims=" %%h in ('certutil -hashfile requirements.txt SHA256') do (
    if not defined HUELLA_REQUIREMENTS set "HUELLA_REQUIREMENTS=%%h"
)
set "HUELLA_PYPROJECT="
for /f "skip=1 delims=" %%h in ('certutil -hashfile pyproject.toml SHA256') do (
    if not defined HUELLA_PYPROJECT set "HUELLA_PYPROJECT=%%h"
)
set "HUELLA_ACTUAL=!HUELLA_REQUIREMENTS!!HUELLA_PYPROJECT!"
set "HUELLA_ACTUAL=!HUELLA_ACTUAL: =!"
set "HUELLA_GUARDADA="
if exist "!ARCHIVO_DE_HUELLA!" set /p HUELLA_GUARDADA=<"!ARCHIVO_DE_HUELLA!"
set "INSTALAR=0"
if /i not "!HUELLA_ACTUAL!"=="!HUELLA_GUARDADA!" set "INSTALAR=1"
REM Sin huella (certutil fallo) se instala siempre y no se guarda nada: dos vacios iguales nunca saltean la instalacion
if "!HUELLA_ACTUAL!"=="" set "INSTALAR=1"
if "!INSTALAR!"=="1" (
    echo [*] Instalando dependencias...
    "!VENV_PYTHON!" -m pip install --upgrade pip
    "!VENV_PYTHON!" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Error al instalar dependencias.
        pause
        exit /b 1
    )
    "!VENV_PYTHON!" -m pip install --no-deps -e .
    if errorlevel 1 (
        echo [ERROR] Error al instalar Aulento en el entorno.
        pause
        exit /b 1
    )
    if not "!HUELLA_ACTUAL!"=="" >"!ARCHIVO_DE_HUELLA!" echo !HUELLA_ACTUAL!
    echo [OK] Dependencias instaladas con exito.
    echo.
)

REM 5. Contenedor Docker PostgreSQL pgvector: opcional, sin Docker se sigue con SQLite
echo [*] Comprobando contenedor Docker PostgreSQL pgvector...
where docker >nul 2>nul
if !errorlevel! equ 0 (
    docker compose up -d >nul 2>&1
    if !errorlevel! equ 0 (
        echo   [OK] PostgreSQL pgvector activo en 127.0.0.1:5432
    ) else (
        echo   [INFO] Docker no pudo iniciar el contenedor - verifica si Docker Desktop esta activo.
        echo   [INFO] Continuando con SQLite local...
    )
) else (
    echo   [INFO] Docker no encontrado en PATH. Continuando con SQLite local...
)
echo.

REM 6. Detectar puerto disponible: 8000, o 8001 si el 8000 esta ocupado
set "PORT=8000"
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo   [AVISO] El puerto 8000 esta ocupado por otra aplicacion.
    echo   [*] Conmutando automaticamente al puerto 8001...
    set "PORT=8001"
) else (
    echo   [OK] Puerto 8000 disponible.
)
echo.

REM 7. Iniciar el servidor, tambien en la primera ejecucion: sin cuentas, imprime en esta ventana el codigo
REM    del primer administrador, y la web guia el primer ingreso
echo [*] Iniciando servidor Aulento en http://127.0.0.1:!PORT! ...
echo ===============================================================
echo  Para detener la aplicacion, presiona Ctrl + C en esta ventana.
echo ===============================================================
echo.

"!VENV_PYTHON!" -m aulento web start --host 127.0.0.1 --port !PORT! --open-browser

pause
