"""Pruebas unitarias para scripts/compilar_css.py sin requerir conexión de red."""

from pathlib import Path

import pytest

try:
    from scripts.compilar_css import (
        SUMAS_SHA256,
        armar_comando,
        obtener_nombre_binario,
        verificar_sha256,
    )
except ModuleNotFoundError:
    pytest.skip(
        "scripts/compilar_css.py no está presente en este entorno (ej. core extraído sin scripts de desarrollo)",
        allow_module_level=True,
    )


def test_tabla_de_sumas_sha256():
    """La tabla de sumas debe contener todas las plataformas y hashes válidos de 64 caracteres hex."""
    binarios_esperados = {
        "tailwindcss-linux-arm64",
        "tailwindcss-linux-armv7",
        "tailwindcss-linux-x64",
        "tailwindcss-macos-arm64",
        "tailwindcss-macos-x64",
        "tailwindcss-windows-arm64.exe",
        "tailwindcss-windows-x64.exe",
    }
    assert set(SUMAS_SHA256.keys()) == binarios_esperados

    for nombre, sha in SUMAS_SHA256.items():
        assert len(sha) == 64, f"Hash inválido para {nombre}: {sha}"
        assert all(c in "0123456789abcdef" for c in sha), f"No es hexadecimal: {sha}"


def test_obtener_nombre_binario_por_plataforma():
    """Detecta correctamente los nombres de binario por sistema operativo y arquitectura."""
    assert obtener_nombre_binario("Windows", "AMD64") == "tailwindcss-windows-x64.exe"
    assert obtener_nombre_binario("Windows", "ARM64") == "tailwindcss-windows-arm64.exe"
    assert obtener_nombre_binario("Linux", "x86_64") == "tailwindcss-linux-x64"
    assert obtener_nombre_binario("Linux", "aarch64") == "tailwindcss-linux-arm64"
    assert obtener_nombre_binario("Linux", "armv7l") == "tailwindcss-linux-armv7"
    assert obtener_nombre_binario("Darwin", "arm64") == "tailwindcss-macos-arm64"
    assert obtener_nombre_binario("Darwin", "x86_64") == "tailwindcss-macos-x64"

    with pytest.raises(RuntimeError, match="Plataforma no soportada"):
        obtener_nombre_binario("FreeBSD", "x86_64")


def test_verificar_sha256_aborta_con_suma_mala(tmp_path: Path):
    """Debe abortar levantando ValueError cuando el archivo no coincide con su suma registrada."""
    archivo_corrupto = tmp_path / "tailwindcss-linux-x64"
    archivo_corrupto.write_bytes(b"contenido fraudulento o corrupto")

    with pytest.raises(ValueError, match="Falla de verificación SHA-256"):
        verificar_sha256(archivo_corrupto, "tailwindcss-linux-x64")


def test_verificar_sha256_aborta_con_binario_desconocido(tmp_path: Path):
    """Debe abortar si se intenta verificar un binario no registrado en la tabla."""
    archivo = tmp_path / "desconocido"
    archivo.write_bytes(b"algo")
    with pytest.raises(ValueError, match="Binario desconocido"):
        verificar_sha256(archivo, "binario-inventado")


def test_armar_comando():
    """Arma correctamente el comando de compilación con las opciones deseadas."""
    binario = Path("/fake/bin/tailwindcss")
    entrada = Path("/fake/src/entrada.css")
    salida = Path("/fake/dist/tailwind.css")
    config = Path("/fake/tailwind.config.js")

    cmd = armar_comando(binario, entrada, salida, minify=True, ruta_config=config)
    assert cmd == [
        str(binario),
        "-i",
        str(entrada),
        "-o",
        str(salida),
        "--minify",
        "-c",
        str(config),
    ]

    cmd_simple = armar_comando(binario, entrada, salida, minify=False, ruta_config=None)
    assert cmd_simple == [
        str(binario),
        "-i",
        str(entrada),
        "-o",
        str(salida),
    ]
