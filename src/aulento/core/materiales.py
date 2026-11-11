"""Materiales de estudio que cada cuenta sube desde la PC (048): el archivo en su carpeta y el texto en la base.

El archivo se guarda en `<datos>/usuarios/<id>/materiales/` con un nombre que genera el servidor; el nombre que
manda el navegador solo se muestra. El texto extraído queda en la tabla `materiales`, así el tutor puede buscar
por palabras clave aunque no haya PostgreSQL.
"""

import hashlib
import os
import re
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aulento.config import dir_de_cuenta, get_data_dir
from aulento.core import permisos
from aulento.core.almacenes import ServicioDeCuenta
from aulento.mcp.pdf_text import PdfSinTextoError, extraer_texto_pdf

MEGABYTE = 1024 * 1024
MAX_BYTES_POR_ARCHIVO = 25 * MEGABYTE
VARIABLE_CUOTA_MATERIALES_MB = "AULENTO_CUOTA_MATERIALES_MB"
CUOTA_POR_DEFECTO_MB = 200
ESPACIO_MINIMO_LIBRE_DISCO = 2 * 1024 * 1024 * 1024  # 2 GiB


def cuota_por_cuenta() -> int:
    """La cuota por cuenta en bytes, leída de AULENTO_CUOTA_MATERIALES_MB o 200 MB por defecto."""
    valor = os.getenv(VARIABLE_CUOTA_MATERIALES_MB)
    if valor is not None:
        try:
            mb = int(valor)
            if mb > 0:
                return mb * MEGABYTE
        except (ValueError, TypeError):
            pass
    return CUOTA_POR_CUENTA


CUOTA_POR_CUENTA = CUOTA_POR_DEFECTO_MB * MEGABYTE
# Un tope de seguridad, no de lectura: un PDF de 25 MB con texto rara vez pasa los 2 millones de caracteres
MAX_CARACTERES_POR_MATERIAL = 5_000_000
EXTENSIONES_ADMITIDAS = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}
CARPETA_DE_MATERIALES = "materiales"
MAX_LARGO_DEL_NOMBRE = 200

# Fragmentos alrededor de cada coincidencia, para que el tutor lea el pasaje y no solo la palabra
CARACTERES_POR_VENTANA = 1_500
MAX_COINCIDENCIAS_POR_PALABRA = 200
SEPARADOR_DE_FRAGMENTOS = "\n[…]\n"

PALABRAS_VACIAS = frozenset(
    ["sobre", "tengo", "tiene", "temas", "tema", "para", "según", "segun", "explicame", "explícame", "explica", "como", "cómo", "cual", "cuál", "cuales", "entre", "desde", "este", "esta", "estos", "estas", "donde", "dónde", "cuando", "cuándo", "quiero", "necesito", "puedes", "podes", "hacer", "about", "what", "which", "have", "with", "from", "that", "this"]
)
MAX_PALABRAS_CLAVE = 3

_CONTROLES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_COLUMNAS_PUBLICAS = "id, nombre, extension, tipo_mime, bytes, caracteres, creado_en"


def palabras_clave(query: str) -> list[str]:
    """Hasta tres palabras significativas de la consulta, las más largas primero."""
    unicas: list[str] = []
    for palabra in re.findall(r"[^\W\d_]{4,}", query.lower()):
        if palabra not in PALABRAS_VACIAS and palabra not in unicas:
            unicas.append(palabra)
    return sorted(unicas, key=len, reverse=True)[:MAX_PALABRAS_CLAVE]


def describir_bytes(cantidad: int) -> str:
    """Tamaño para mostrar en megabytes: «25 MB», «3,5 MB»."""
    megas = cantidad / MEGABYTE
    texto = f"{megas:.0f}" if megas >= 10 or megas == int(megas) else f"{megas:.1f}".replace(".", ",")
    return f"{texto} MB"


class ErrorDeMaterial(Exception):
    """Un material que no se puede guardar, leer o borrar; `codigo` es el estado HTTP que le corresponde."""

    codigo = 400


class MaterialDemasiadoGrande(ErrorDeMaterial):
    codigo = 413


class TipoNoAdmitido(ErrorDeMaterial):
    codigo = 415


class MaterialIlegible(ErrorDeMaterial):
    codigo = 422


class MaterialRepetido(ErrorDeMaterial):
    codigo = 409

    def __init__(self, material: dict[str, Any]) -> None:
        super().__init__(f"Ya subiste este archivo como «{material['nombre']}».")
        self.material = material


class MaterialNoEncontrado(ErrorDeMaterial):
    codigo = 404

    def __init__(self, identificador: object) -> None:
        super().__init__(f"Material con ID {identificador} no encontrado.")
        self.identificador = identificador


class EspacioEnDiscoInsuficiente(ErrorDeMaterial):
    codigo = 507


def _comprobar_espacio_libre(datos_bytes: int = 0) -> None:
    """Rechaza la subida si el espacio libre en el disco de datos es o quedaría menor a 2 GiB."""
    try:
        uso = shutil.disk_usage(get_data_dir())
    except OSError:
        return
    if (uso.free - datos_bytes) < ESPACIO_MINIMO_LIBRE_DISCO:
        raise EspacioEnDiscoInsuficiente(
            "Espacio en disco insuficiente en el servidor para guardar el material "
            "(se requieren al menos 2 GiB libres)."
        )


def _nombre_visible(nombre: str | None) -> str:
    """El nombre que mandó el navegador, sin carpetas ni caracteres de control: solo se muestra, nunca es una ruta."""
    base = re.split(r"[\\/]", nombre or "")[-1]
    return _CONTROLES.sub("", base).strip()[:MAX_LARGO_DEL_NOMBRE]


def _texto_plano(datos: bytes) -> str:
    if b"\x00" in datos:
        raise TipoNoAdmitido("El archivo no es texto: tiene contenido binario. Subí un PDF, Markdown o texto.")
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("latin-1")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROLES.sub("", texto)[:MAX_CARACTERES_POR_MATERIAL]


def extraer_texto(extension: str, datos: bytes) -> str:
    """Texto completo del archivo según su tipo, comprobando que el contenido sea del tipo que dice la extensión."""
    if extension == ".pdf":
        if not datos.startswith(b"%PDF-"):
            raise TipoNoAdmitido("El archivo dice ser un PDF pero su contenido no lo es.")
        try:
            texto = extraer_texto_pdf(datos, MAX_CARACTERES_POR_MATERIAL)
        except PdfSinTextoError as error:
            raise MaterialIlegible(f"No se pudo leer el texto del PDF: {error}.") from error
    else:
        texto = _texto_plano(datos)
    if not texto.strip():
        raise MaterialIlegible("El archivo no tiene texto para estudiar.")
    return texto


def _publico(fila: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": fila["id"],
        "nombre": fila["nombre"],
        "extension": fila["extension"],
        "tipo_mime": fila["tipo_mime"],
        "bytes": fila["bytes"],
        "caracteres": fila["caracteres"],
        "creado_en": fila["creado_en"],
    }


def _ventanas(texto: str, palabras: list[str]) -> list[tuple[int, int, int, set[str]]]:
    """Tramos del texto alrededor de cada coincidencia, unidos si se tocan.

    Cada tramo lleva su inicio, su fin, la posición de su primera coincidencia y las palabras que contiene.
    """
    medio = CARACTERES_POR_VENTANA // 2
    tramos: list[tuple[int, int, int, str]] = []
    for palabra in palabras:
        for numero, hallazgo in enumerate(re.finditer(re.escape(palabra), texto, re.IGNORECASE)):
            if numero >= MAX_COINCIDENCIAS_POR_PALABRA:
                break
            centro = hallazgo.start()
            tramos.append((max(0, centro - medio), min(len(texto), centro + medio), centro, palabra))
    tramos.sort()
    unidos: list[tuple[int, int, int, set[str]]] = []
    for inicio, fin, centro, palabra in tramos:
        if unidos and inicio <= unidos[-1][1]:
            anterior = unidos[-1]
            unidos[-1] = (anterior[0], max(anterior[1], fin), anterior[2], anterior[3] | {palabra})
        else:
            unidos.append((inicio, fin, centro, {palabra}))
    return unidos


class AlmacenDeMateriales(ServicioDeCuenta):
    """Materiales de una cuenta: guardar, listar, leer, buscar y borrar, siempre dentro de la cuenta."""

    def carpeta(self) -> Path:
        carpeta = dir_de_cuenta(self.user_id) / CARPETA_DE_MATERIALES
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta

    def uso(self) -> dict[str, int]:
        """Bytes que ocupan los archivos de la cuenta, el tope y lo que queda libre."""
        cuota = cuota_por_cuenta()
        with self._conexion() as conn:
            usado = conn.execute(
                "SELECT COALESCE(SUM(bytes), 0) FROM materiales WHERE user_id = ?;", (self.user_id,)
            ).fetchone()[0]
        return {"usado": usado, "tope": cuota, "libre": max(0, cuota - usado)}

    def limite_de_subida(self) -> int:
        """Lo más que puede pesar el próximo archivo: el tope por archivo o lo que queda libre, lo que sea menor."""
        return min(MAX_BYTES_POR_ARCHIVO, self.uso()["libre"])

    def error_de_tope(self) -> MaterialDemasiadoGrande:
        """El rechazo de un archivo que no entra, con el tope que pasó y cuánto queda libre."""
        libre = self.uso()["libre"]
        cuota = cuota_por_cuenta()
        if libre < MAX_BYTES_POR_ARCHIVO:
            return MaterialDemasiadoGrande(
                f"El archivo no entra en tu espacio de {describir_bytes(cuota)}: "
                f"quedan {describir_bytes(libre)} libres. Borrá algún material para hacer lugar."
            )
        return MaterialDemasiadoGrande(
            f"El archivo pasa el tope de {describir_bytes(MAX_BYTES_POR_ARCHIVO)} por archivo. "
            f"En tu espacio quedan {describir_bytes(libre)} libres."
        )

    def guardar(self, nombre: str | None, datos: bytes) -> dict[str, Any]:
        """Valida el archivo, extrae su texto completo y lo guarda a nombre de la cuenta; devuelve sus datos."""
        visible = _nombre_visible(nombre)
        extension = Path(visible).suffix.lower()
        if extension not in EXTENSIONES_ADMITIDAS:
            raise TipoNoAdmitido("Solo se pueden subir archivos PDF, Markdown (.md, .markdown) o de texto (.txt).")
        if not datos:
            raise MaterialIlegible("El archivo está vacío.")
        if len(datos) > self.limite_de_subida():
            raise self.error_de_tope()
        _comprobar_espacio_libre(len(datos))
        huella = hashlib.sha256(datos).hexdigest()
        repetido = self._por_huella(huella)
        if repetido is not None:
            raise MaterialRepetido(repetido)
        # Después del repetido: volver a subir uno que ya está no suma bytes y no debe chocar con un tope (062)
        with self._conexion() as conn:
            permisos.exigir(self.user_id, permisos.SUBIR_MATERIAL, conn, bytes=len(datos))
        texto = extraer_texto(extension, datos)

        archivo = f"{uuid.uuid4().hex}{extension}"
        destino = self.carpeta() / archivo
        parcial = destino.with_name(destino.name + ".parcial")
        parcial.write_bytes(datos)
        parcial.replace(destino)
        try:
            material_id = self._registrar(visible, extension, len(datos), huella, archivo, texto)
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
        return self.obtener(material_id, con_texto=False)

    def _registrar(self, nombre: str, extension: str, peso: int, huella: str, archivo: str, texto: str) -> int:
        with self._conexion() as conn:
            iniciada = False
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE;")
                iniciada = True
            try:
                permisos.exigir(self.user_id, permisos.SUBIR_MATERIAL, conn, bytes=peso)
                # La cuota se comprueba en la misma sentencia que inserta: dos subidas a la vez no la pasan
                cursor = conn.execute(
                    "INSERT INTO materiales (user_id, nombre, extension, tipo_mime, bytes, sha256, archivo, texto, "
                    "caracteres, creado_en) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ? "
                    "WHERE (SELECT COALESCE(SUM(bytes), 0) FROM materiales WHERE user_id = ?) + ? <= ?;",
                    (
                        self.user_id,
                        nombre,
                        extension,
                        EXTENSIONES_ADMITIDAS[extension],
                        peso,
                        huella,
                        archivo,
                        texto,
                        len(texto),
                        datetime.now(UTC).isoformat(timespec="seconds"),
                        self.user_id,
                        peso,
                        cuota_por_cuenta(),
                    ),
                )
                if iniciada:
                    conn.commit()
            except sqlite3.IntegrityError:
                if iniciada:
                    conn.rollback()
                repetido = self._por_huella(huella)
                if repetido is None:
                    raise
                raise MaterialRepetido(repetido) from None
            except Exception:
                if iniciada:
                    conn.rollback()
                raise
        if cursor.rowcount == 0:
            raise self.error_de_tope()
        return cursor.lastrowid

    def _por_huella(self, huella: str) -> dict[str, Any] | None:
        with self._conexion() as conn:
            fila = conn.execute(
                f"SELECT {_COLUMNAS_PUBLICAS} FROM materiales WHERE user_id = ? AND sha256 = ?;", (self.user_id, huella)
            ).fetchone()
        return None if fila is None else _publico(fila)

    def listar(self) -> list[dict[str, Any]]:
        """Los materiales de la cuenta, del más nuevo al más viejo, sin su texto."""
        with self._conexion() as conn:
            filas = conn.execute(
                f"SELECT {_COLUMNAS_PUBLICAS} FROM materiales WHERE user_id = ? ORDER BY creado_en DESC, id DESC;",
                (self.user_id,),
            ).fetchall()
        return [_publico(fila) for fila in filas]

    def obtener(self, material_id: int, con_texto: bool = True) -> dict[str, Any]:
        """Los datos de un material de la cuenta y, si se pide, su texto; uno de otra cuenta no se encuentra."""
        with self._conexion() as conn:
            fila = conn.execute(
                f"SELECT {_COLUMNAS_PUBLICAS}, texto FROM materiales WHERE id = ? AND user_id = ?;",
                (material_id, self.user_id),
            ).fetchone()
        if fila is None:
            raise MaterialNoEncontrado(material_id)
        material = _publico(fila)
        if con_texto:
            material["texto"] = fila["texto"]
        return material

    def borrar(self, material_id: int) -> None:
        """Borra el material de la cuenta y su archivo, y así libera su espacio."""
        with self._conexion() as conn:
            fila = conn.execute(
                "SELECT archivo FROM materiales WHERE id = ? AND user_id = ?;", (material_id, self.user_id)
            ).fetchone()
            if fila is None:
                raise MaterialNoEncontrado(material_id)
            conn.execute("DELETE FROM materiales WHERE id = ? AND user_id = ?;", (material_id, self.user_id))
            conn.commit()
        (self.carpeta() / fila["archivo"]).unlink(missing_ok=True)

    def buscar(self, consulta: str, limite: int = 5) -> list[dict[str, Any]]:
        """Los materiales que nombran las palabras clave de la consulta, los que más coinciden primero."""
        palabras = palabras_clave(consulta)
        if not palabras:
            return []
        condiciones = " OR ".join(["texto LIKE ? OR nombre LIKE ?"] * len(palabras))
        parametros = [patron for palabra in palabras for patron in (f"%{palabra}%",) * 2]
        with self._conexion() as conn:
            filas = conn.execute(
                f"SELECT {_COLUMNAS_PUBLICAS}, texto FROM materiales WHERE user_id = ? AND ({condiciones});",
                (self.user_id, *parametros),
            ).fetchall()
        puntuados = []
        for fila in filas:
            texto, nombre = fila["texto"].casefold(), fila["nombre"].casefold()
            puntaje = sum(texto.count(palabra) + 10 * nombre.count(palabra) for palabra in palabras)
            if puntaje:
                puntuados.append(_publico(fila) | {"puntaje": puntaje})
        puntuados.sort(key=lambda material: (-material["puntaje"], material["id"]))
        return puntuados[:limite]

    def fragmentos_relevantes(self, material_id: int, consulta: str, max_caracteres: int) -> str:
        """Los pasajes del material que tratan la consulta, de cualquier parte del texto, sin pasar `max_caracteres`.

        Sin coincidencias devuelve el principio del texto.
        """
        texto = self.obtener(material_id)["texto"]
        ventanas = _ventanas(texto, palabras_clave(consulta))
        if not ventanas:
            return texto[:max_caracteres]
        elegidas: list[tuple[int, int]] = []
        restante = max_caracteres
        # Primero los pasajes donde aparecen más palabras de la consulta; cada uno, salvo el primero, paga su separador
        for inicio, fin, centro, _ in sorted(ventanas, key=lambda v: (-len(v[3]), v[0])):
            disponible = restante - (len(SEPARADOR_DE_FRAGMENTOS) if elegidas else 0)
            if disponible <= 0:
                break
            if fin - inicio > disponible:
                # Un tramo que no entra entero se recorta alrededor de su coincidencia, no desde su principio
                inicio = max(inicio, centro - disponible // 2)
                fin = min(fin, inicio + disponible)
            elegidas.append((inicio, fin))
            restante = disponible - (fin - inicio)
        return SEPARADOR_DE_FRAGMENTOS.join(texto[inicio:fin] for inicio, fin in sorted(elegidas))
