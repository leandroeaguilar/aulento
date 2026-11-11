"""Módulo de Diagnóstico y Depuración Local para Aulento (Core Open-Source).

Proporciona utilidades para auditar el estado del motor SQLite, la conectividad con IA local (Ollama),
la lectura acotada de logs del sistema y la generación de reportes anonimizados para GitHub Issues.
"""

import json
import logging
import platform
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from aulento.config import get_data_dir, get_db_path, get_engine_mode
from aulento.db.connection import get_connection

logger = logging.getLogger(__name__)


def anonimizar_texto(texto: str) -> str:
    """Elimina información sensible (nombres de usuario en rutas, tokens, IPs privadas) de un texto."""
    # Anonimizar rutas de Windows tipo C:\Users\<usuario>\ o C:/Users/<usuario>/
    texto = re.sub(r"([A-Za-z]:[/\\][Uu]sers[/\\])[^/\\\s]+([/\\]?)", r"\1[USUARIO]\2", texto)
    # Anonimizar rutas de Unix tipo /home/<usuario>/ o /Users/<usuario>/
    texto = re.sub(r"/(home|Users)/[^/]+/", r"/\1/[USUARIO]/", texto)
    # Anonimizar claves tipo sk-..., gsk_..., AIza...
    texto = re.sub(r"\b(sk-[a-zA-Z0-9_-]{20,}|gsk_[a-zA-Z0-9_-]{20,}|AIza[a-zA-Z0-9_-]{20,})\b", "[CLAVE_OCULTA]", texto)
    # Anonimizar tokens JWT (formato eyJ...)
    texto = re.sub(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b", "[JWT_ANONIMO]", texto)
    # Anonimizar tokens Bearer en logs
    texto = re.sub(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer [TOKEN_ANONIMO]", texto)
    # Anonimizar tokens hex o UUIDs largos en logs
    texto = re.sub(r"\b[a-fA-F0-9]{32,64}\b", "[HASH_ANONIMO]", texto)
    return texto


def leer_ultimas_lineas_log(max_lineas: int = 150) -> list[str]:
    """Retorna las últimas líneas del archivo de log local, si existe."""
    log_path = get_data_dir() / "aulento.log"
    if not log_path.exists():
        # Buscar en directorio actual
        log_path = Path("aulento.log")
        if not log_path.exists():
            return ["[INFO] No se encontró archivo aulento.log en disco (la salida fue a consola)."]

    try:
        tamano = log_path.stat().st_size
        with open(log_path, encoding="utf-8", errors="replace") as f:
            if tamano > 200 * 1024:
                # Si el archivo supera 200 KB, saltamos cerca del final para evitar sobrecarga en memoria
                f.seek(max(0, tamano - 64 * 1024))
                f.readline()  # Descartar línea truncada
            lineas = f.readlines()
            ultimas = lineas[-max_lineas:] if len(lineas) > max_lineas else lineas
            return [anonimizar_texto(linea.rstrip()) for linea in ultimas]
    except OSError as exc:
        return [f"[ERROR] No se pudo leer el archivo de log: {exc}"]


def comprobar_salud_sqlite(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Evalúa la salud y configuración de la base de datos SQLite."""
    cerrar = False
    if conn is None:
        conn = get_connection()
        cerrar = True

    try:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version;")
        row_version = cur.fetchone()
        version_esquema = row_version[0] if row_version else 0

        cur.execute("PRAGMA journal_mode;")
        row_journal = cur.fetchone()
        journal_mode = row_journal[0] if row_journal else "unknown"

        cur.execute("PRAGMA integrity_check;")
        row_integrity = cur.fetchone()
        integridad = row_integrity[0] if row_integrity else "unknown"

        db_path = get_db_path()
        try:
            tamano_bytes = db_path.stat().st_size if db_path.exists() else 0
        except OSError:
            tamano_bytes = 0

        return {
            "estado": "saludable" if integridad == "ok" else "advertencia",
            "version_esquema": version_esquema,
            "journal_mode": journal_mode,
            "integridad": integridad,
            "tamano_bytes": tamano_bytes,
            "tamano_humano": f"{tamano_bytes / 1024:.1f} KB",
        }
    except (sqlite3.Error, OSError) as exc:
        return {
            "estado": "error",
            "error": str(exc),
        }
    finally:
        if cerrar:
            conn.close()


def comprobar_ollama_local() -> dict[str, Any]:
    """Verifica si hay una instancia de Ollama ejecutándose en local sin bloquear."""
    import http.client
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=0.6)
        conn.request("GET", "/api/tags", headers={"User-Agent": "StudyEngineDiagnostic/1.0"})
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            modelos = [m.get("name", "") for m in data.get("models", [])]
            return {"disponible": True, "modelos": modelos}
    except (OSError, TimeoutError, json.JSONDecodeError):
        logger.debug("Ollama no está disponible en localhost:11434")
    return {"disponible": False, "modelos": []}


def obtener_resumen_diagnostico(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Construye un diagnóstico completo del entorno de ejecución local."""
    return {
        "modo_motor": get_engine_mode(),
        "sistema": {
            "os": platform.system(),
            "os_release": platform.release(),
            "python_version": sys.version.split()[0],
            "arquitectura": platform.machine(),
        },
        "sqlite": comprobar_salud_sqlite(conn),
        "ollama": comprobar_ollama_local(),
        "logs_recientes": leer_ultimas_lineas_log(100),
    }


def exportar_reporte_anonimizado(conn: sqlite3.Connection | None = None) -> str:
    """Genera un reporte técnico formateado en Markdown apto para GitHub Issues."""
    resumen = obtener_resumen_diagnostico(conn)
    sqlite_info = resumen["sqlite"]
    ollama_info = resumen["ollama"]
    sistema = resumen["sistema"]

    lineas = [
        "### Aulento - Reporte de Diagnóstico del Sistema",
        "",
        f"- **Modo de Operación:** `{resumen['modo_motor']}`",
        f"- **Sistema Operativo:** {sistema['os']} {sistema['os_release']} ({sistema['arquitectura']})",
        f"- **Versión de Python:** `{sistema['python_version']}`",
        "",
        "#### Estado de Base de Datos SQLite",
        f"- **Integridad:** `{sqlite_info.get('integridad', 'N/A')}`",
        f"- **Versión de Esquema (Migraciones):** `{sqlite_info.get('version_esquema', 'N/A')}`",
        f"- **Modo Diario (Journal):** `{sqlite_info.get('journal_mode', 'N/A')}`",
        f"- **Tamaño de Base de Datos:** `{sqlite_info.get('tamano_humano', '0 KB')}`",
        "",
        "#### Estado de IA Local (Ollama)",
        f"- **Ollama Activo:** `{'Sí' if ollama_info.get('disponible') else 'No detectado en localhost:11434'}`",
    ]

    if ollama_info.get("modelos"):
        lineas.append(f"- **Modelos Instalados:** {', '.join(ollama_info['modelos'])}")

    lineas.extend([
        "",
        "#### Logs Recientes (Anonimizados)",
        "```text",
    ])
    lineas.extend(resumen.get("logs_recientes", [])[-40:])
    lineas.append("```")
    lineas.append("")

    return "\n".join(lineas)
