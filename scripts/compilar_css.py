"""Recompila src/aulento/web/static/css/tailwind.css con el CLI standalone de Tailwind.

Baja el binario oficial de la versión fijada, verifica su SHA-256 contra la tabla de abajo
(copiada de sha256sums.txt del release en GitHub) y recién entonces lo ejecuta. Si la suma
no coincide, aborta sin ejecutar nada.

Uso:
    python scripts/compilar_css.py
"""

from __future__ import annotations

import hashlib
import os
import platform
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

VERSION = "v3.4.17"

# https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/sha256sums.txt
SUMAS_SHA256: dict[str, str] = {
    "tailwindcss-linux-arm64": "69b1378b8133192d7d2feb12a116fa12d035594f58db3eff215879e4ad8cf39b",
    "tailwindcss-linux-armv7": "704e7d91afba6e1f630889afd0d7db36b4634e628512cc141d504a5beae28860",
    "tailwindcss-linux-x64": "7d24f7fa191d2193b78cd5f5a42a6093e14409521908529f42d80b11fde1f1d4",
    "tailwindcss-macos-arm64": "a1d0c7985759accca0bf12e51ac1dcbf0f6cf2fffb62e6e0f62d091c477a10a3",
    "tailwindcss-macos-x64": "6cbdad74be776c087ffa5e9a057512c54898f9fe8828d3362212dfe32fc933a3",
    "tailwindcss-windows-arm64.exe": "76f516476784c00f1562160b5758e3d8f0e6c48957efb26b5b50fbdfd76aa382",
    "tailwindcss-windows-x64.exe": "67f1c5e3f5a03406a7bf5badf5ada09b79f3ae78ec43450c15f7e983068da346",
}

RAIZ = Path(__file__).resolve().parents[1]
ESTATICO = RAIZ / "src" / "aulento" / "web" / "static"
ENTRADA = ESTATICO / "css" / "entrada.css"
SALIDA = ESTATICO / "css" / "tailwind.css"
CONFIG = RAIZ / "tailwind.config.js"
CACHE = Path(os.environ.get("AULENTO_TAILWIND_CACHE", Path.home() / ".cache" / "aulento" / "tailwindcss")) / VERSION

_ARQUITECTURAS = {
    "x86_64": "x64",
    "amd64": "x64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "armv7",
}
_SISTEMAS = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}


def obtener_nombre_binario(sistema: str, arquitectura: str) -> str:
    """Nombre del binario del release para este sistema operativo y arquitectura."""
    so = _SISTEMAS.get(sistema)
    arq = _ARQUITECTURAS.get(arquitectura.lower())
    nombre = f"tailwindcss-{so}-{arq}" + (".exe" if so == "windows" else "")
    if so is None or arq is None or nombre not in SUMAS_SHA256:
        raise RuntimeError(f"Plataforma no soportada: {sistema} {arquitectura}")
    return nombre


def verificar_sha256(ruta: Path, nombre: str) -> None:
    """Levanta ValueError si el archivo no coincide con la suma registrada para ese binario."""
    esperado = SUMAS_SHA256.get(nombre)
    if esperado is None:
        raise ValueError(f"Binario desconocido: {nombre}")
    obtenido = hashlib.sha256(ruta.read_bytes()).hexdigest()
    if obtenido != esperado:
        raise ValueError(f"Falla de verificación SHA-256 para {nombre}: esperado {esperado}, obtenido {obtenido}")


def armar_comando(
    binario: Path, entrada: Path, salida: Path, *, minify: bool, ruta_config: Path | None
) -> list[str]:
    cmd = [str(binario), "-i", str(entrada), "-o", str(salida)]
    if minify:
        cmd.append("--minify")
    if ruta_config is not None:
        cmd += ["-c", str(ruta_config)]
    return cmd


def obtener_binario() -> Path:
    nombre = obtener_nombre_binario(platform.system(), platform.machine())
    ruta = CACHE / nombre
    if ruta.exists():
        try:
            verificar_sha256(ruta, nombre)
            return ruta
        except ValueError:
            ruta.unlink()  # caché corrupta: se vuelve a bajar
    CACHE.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{VERSION}/{nombre}"
    print(f"bajando {url}")
    temporal = ruta.with_suffix(ruta.suffix + ".parcial")
    with urllib.request.urlopen(url, timeout=120) as respuesta:  # noqa: S310 (URL fija de GitHub)
        temporal.write_bytes(respuesta.read())
    try:
        verificar_sha256(temporal, nombre)
    except ValueError:
        temporal.unlink()
        raise
    temporal.replace(ruta)
    ruta.chmod(ruta.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return ruta


def main() -> int:
    binario = obtener_binario()
    cmd = armar_comando(binario, ENTRADA, SALIDA, minify=True, ruta_config=CONFIG)
    # El binario standalone trae su propia copia de caniuse-lite: "npx update-browserslist-db" no la
    # actualiza y la versión de Tailwind está fijada a propósito, así que el aviso de datos viejos es ruido.
    entorno = {**os.environ, "BROWSERSLIST_IGNORE_OLD_DATA": "1"}
    resultado = subprocess.run(cmd, cwd=RAIZ, env=entorno, check=False)  # noqa: S603 (binario verificado por SHA-256)
    return resultado.returncode


if __name__ == "__main__":
    sys.exit(main())
