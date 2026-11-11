#!/usr/bin/env bash
# Arranque local de Aulento en Linux y macOS: escucha solo en esta máquina (127.0.0.1) y no necesita Docker.
set -euo pipefail
cd "$(dirname "$0")"

echo "==============================================================="
echo "           Aulento - Sistema Maestro de Estudio"
echo "==============================================================="
echo ""

VERSION_MINIMA="import sys; sys.exit(sys.version_info < (3, 11))"
VENV_PYTHON=".venv/bin/python"
ARCHIVO_DE_HUELLA=".venv/.requirements.sha256"

# 1. Python 3.11 o posterior: el primero del PATH que lo cumpla
PYTHON_CMD=""
ENCONTRADOS=""
for candidato in python3 python; do
    if command -v "$candidato" >/dev/null 2>&1; then
        ENCONTRADOS="$ENCONTRADOS $candidato ($("$candidato" -V 2>&1))"
        if "$candidato" -c "$VERSION_MINIMA"; then
            PYTHON_CMD="$candidato"
            break
        fi
    fi
done
if [ -z "$ENCONTRADOS" ]; then
    echo "[ERROR] Python no está instalado. Instalá Python 3.11 o posterior."
    exit 1
fi
if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Aulento necesita Python 3.11 o posterior, y en el PATH hay:$ENCONTRADOS."
    exit 1
fi

# 2. Entorno virtual, creado con ese Python
if [ ! -x "$VENV_PYTHON" ]; then
    echo "[*] Creando entorno virtual local (.venv)..."
    "$PYTHON_CMD" -m venv .venv
    # Un entorno recreado está vacío aunque haya quedado la huella de la instalación anterior
    rm -f "$ARCHIVO_DE_HUELLA"
fi
if ! "$VENV_PYTHON" -c "$VERSION_MINIMA"; then
    echo "[ERROR] El entorno .venv usa $("$VENV_PYTHON" -V 2>&1) y Aulento necesita 3.11 o posterior."
    echo "        Borrá la carpeta .venv y volvé a ejecutar este script."
    exit 1
fi

# 3. Dependencias: se instalan al crear el entorno y se reinstalan si requirements.txt o pyproject.toml cambiaron
huella_de_requirements() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum requirements.txt pyproject.toml | cut -d ' ' -f 1 | tr -d '
'
    else
        shasum -a 256 requirements.txt pyproject.toml | cut -d ' ' -f 1 | tr -d '
'
    fi
}
HUELLA_ACTUAL="$(huella_de_requirements)"
HUELLA_GUARDADA=""
if [ -f "$ARCHIVO_DE_HUELLA" ]; then
    HUELLA_GUARDADA="$(cat "$ARCHIVO_DE_HUELLA")"
fi
if [ -z "$HUELLA_ACTUAL" ] || [ "$HUELLA_ACTUAL" != "$HUELLA_GUARDADA" ]; then
    echo "[*] Instalando dependencias..."
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r requirements.txt
    "$VENV_PYTHON" -m pip install --no-deps -e .
    echo "$HUELLA_ACTUAL" > "$ARCHIVO_DE_HUELLA"
    echo "[OK] Dependencias instaladas."
    echo ""
fi

# 4. Puerto: 8000, o 8001 si el 8000 está ocupado
PUERTO=8000
if "$VENV_PYTHON" -c "import socket, sys; s = socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1', 8000)) == 0 else 1)"; then
    echo "[AVISO] El puerto 8000 está ocupado: se usa el 8001."
    PUERTO=8001
fi

# 5. Servidor, también en la primera ejecución: sin cuentas, imprime en esta consola el código del primer
#    administrador, y la web guía el primer ingreso
echo "[*] Iniciando Aulento en http://127.0.0.1:${PUERTO} ..."
echo "    Para detenerlo, presioná Ctrl + C."
echo ""
exec "$VENV_PYTHON" -m aulento web start --host 127.0.0.1 --port "$PUERTO" --open-browser
