"""Importación, a una cuenta, de los archivos y variables que eran de toda la instalación (ADR 008).

Antes de que cada cuenta tuviera lo suyo, las claves de IA, los prompts, la caché de
Duolingo y el vault vivían en archivos sueltos del directorio de datos y en variables de entorno. Este módulo
los carga, una vez, en la cuenta que hereda la instalación. Es el único de `src/` que nombra esos archivos y
lee esas variables, y solo como origen de la importación: el servidor nunca vuelve a leerlos.

Reglas:

- Solo se carga lo que la cuenta no tiene: nada de lo que ya cargó se pisa.
- Nada se borra. Un archivo cuyo dato quedó en la cuenta (recién importado, o porque ya lo tenía) se mueve a
  `importado-<fecha>/` dentro del directorio de datos, para que no queden secretos en claro en su lugar.
- Un archivo que no se pudo leer o no tiene la forma esperada se informa y queda donde estaba.
- Un archivo de fuera del directorio de datos se importa pero no se mueve, y se avisa.
- El vault anterior se muda archivo por archivo y sin pisar ninguno: si se corta, otra pasada termina lo que
  faltó. La marca `.mudanza-a-la-cuenta.json`, dentro del vault anterior, dice a qué cuenta se está mudando.
"""

import filecmp
import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aulento.auth.modelos import ROL_ADMIN, UsuarioNoEncontrado
from aulento.auth.repositorio import RepositorioAuth
from aulento.config import get_data_dir
from aulento.connectors.duolingo import DuolingoClient, DuolingoProfile
from aulento.core.gemini_gateway import NIVELES, SECRETOS_DE_CLAVES, GeminiGateway
from aulento.core.secretos import (
    AJUSTE_DUOLINGO_CACHE,
    AJUSTE_DUOLINGO_USUARIO,
    AJUSTE_GEMINI_MODELO,
    AJUSTE_GEMINI_NIVEL_ACTIVO,
    AJUSTE_PROMPT_CLASE,
    AJUSTE_PROMPT_RUTA,
    SECRETO_GEMINI_CLAVE_GRATUITA,
    SECRETO_GEMINI_CLAVE_PAGA,
    AjustesDeCuenta,
    AlmacenDeSecretos,
    ClaveMaestraInvalida,
    SecretoIlegible,
)
from aulento.db.cuenta import exigir_cuenta
from aulento.roadmap.system_prompt_manager import SystemPromptManager
from aulento.vault.rutas import (
    MARCA_CARPETAS_DEL_TUTOR,
    CarpetaDeVaultInvalida,
    fijar_vault_externo,
    vault_externo_fijado,
    vault_propio,
)

ESTADO_IMPORTADO = "importado"
ESTADO_YA_LO_TENIA = "ya_lo_tenia"
ESTADO_NO_ESTABA = "no_estaba"
ESTADO_FALLO = "fallo"
ETIQUETAS = {
    ESTADO_IMPORTADO: "importado",
    ESTADO_YA_LO_TENIA: "ya lo tenía",
    ESTADO_NO_ESTABA: "no estaba",
    ESTADO_FALLO: "falló",
}

ELEMENTO_CLAVE_GRATUITA = "clave gratuita de Gemini"
ELEMENTO_CLAVE_PAGA = "clave paga de Gemini"
ELEMENTO_NIVEL = "nivel activo de Gemini"
ELEMENTO_MODELO = "modelo de Gemini"
ELEMENTO_PROMPT_DE_RUTAS = "prompt de sistema de rutas"
ELEMENTO_PROMPT_DE_CLASES = "prompt de sistema de clases"
ELEMENTO_DUOLINGO = "usuario y caché de Duolingo"
ELEMENTO_VAULT_EXTERNO = "vault externo"
ELEMENTO_VAULT = "vault anterior"

# La clave gratuita se buscaba primero en su archivo y después en el más antiguo, de cuando había una sola
ARCHIVOS_DE_LA_CLAVE_GRATUITA = ("gemini_key_free.txt", "gemini_key.txt")
ARCHIVOS_DE_LA_CLAVE_PAGA = ("gemini_key_paid.txt",)
ARCHIVO_DEL_NIVEL = "gemini_active_tier.txt"
ARCHIVO_DEL_MODELO = "gemini_model.txt"
ARCHIVO_DEL_PROMPT_DE_RUTAS = "prompts/roadmap_system_prompt.txt"
ARCHIVO_DEL_PROMPT_DE_CLASES = "prompts/lesson_system_prompt.txt"
ARCHIVO_DE_DUOLINGO = "duolingo_cache.json"
CARPETA_DEL_VAULT_ANTERIOR = "vault"
# Se escribe en el vault anterior antes de mover la primera nota y se quita al terminar: mientras esté, una
# pasada de la misma cuenta retoma la mudanza aunque su vault ya tenga notas (son las que alcanzó a mover)
MARCA_DE_MUDANZA = ".mudanza-a-la-cuenta.json"
SUFIJO_DE_COPIA_EN_CURSO = ".mudanza-en-curso"

# STUDY_ENGINE_VAULT_PATH es el nombre anterior (ADR 021): se lee aunque se fije después de importar `aulento`
VARIABLES_DEL_VAULT = ("AULENTO_VAULT_PATH", "STUDY_ENGINE_VAULT_PATH", "OBSIDIAN_VAULT_PATH")
VARIABLES_ANTERIORES = VARIABLES_DEL_VAULT

PREFIJO_DEL_RESPALDO = "importado-"
# Carpetas del directorio de datos que nunca son un vault anterior: ahí viven las cuentas y los respaldos
CARPETA_DE_LAS_CUENTAS = "usuarios"
MAX_BYTES_DE_UN_ARCHIVO = 1024 * 1024
LARGO_MAXIMO_DEL_MODELO = 100

# Lo que puede fallar al importar: en un elemento no corta a los demás, y en el alta no impide crear la cuenta
ERRORES_DE_IMPORTACION = (OSError, ValueError, TypeError, LookupError, RuntimeError, sqlite3.Error)

_es_union = getattr(os.path, "isjunction", lambda ruta: False)


class _ArchivoInservible(Exception):
    """Un archivo anterior no se pudo leer o no tiene la forma esperada; el mensaje no repite su contenido."""


@dataclass(frozen=True)
class Resultado:
    """Qué pasó con un elemento: `estado` es uno de los `ESTADO_*`; `detalle` nunca lleva contenido ni secretos."""

    elemento: str
    estado: str
    detalle: str = ""


@dataclass
class Informe:
    """Resultado de una importación, elemento por elemento, apto para mostrar: no contiene ningún secreto."""

    user_id: int
    resultados: list[Resultado] = field(default_factory=list)
    retirados: list[str] = field(default_factory=list)
    carpeta_de_respaldo: Path | None = None
    avisos: list[str] = field(default_factory=list)
    # La cuenta terminó sin ninguna clave de IA: ni la tenía ni estaba en los archivos
    sin_clave_de_ia: bool = False

    def estado_de(self, elemento: str) -> str | None:
        """Estado con que terminó ese elemento, o None si la importación no llegó a tratarlo."""
        return next((r.estado for r in self.resultados if r.elemento == elemento), None)

    def con_estado(self, estado: str) -> list[str]:
        """Elementos que terminaron en ese estado, en el orden en que se trataron."""
        return [r.elemento for r in self.resultados if r.estado == estado]

    @property
    def hubo_fallos(self) -> bool:
        return bool(self.con_estado(ESTADO_FALLO))

    @property
    def encontro_algo(self) -> bool:
        """Falso si no había nada anterior que importar: ni archivos, ni variables, ni vault."""
        return bool(self.avisos or self.retirados) or any(r.estado != ESTADO_NO_ESTABA for r in self.resultados)

    def resumen(self) -> str:
        """Una línea para el registro del servidor."""
        partes = [f"Importación de archivos anteriores a la cuenta {self.user_id}"]
        for estado in (ESTADO_IMPORTADO, ESTADO_YA_LO_TENIA):
            if self.con_estado(estado):
                partes.append(f"{ETIQUETAS[estado]}: {', '.join(self.con_estado(estado))}")
        fallidos = [f"{r.elemento} ({r.detalle})" for r in self.resultados if r.estado == ESTADO_FALLO]
        if fallidos:
            partes.append(f"{ETIQUETAS[ESTADO_FALLO]}: {', '.join(fallidos)}")
        if self.retirados:
            partes.append(
                f"{len(self.retirados)} archivo(s) retirados a {self.carpeta_de_respaldo}, que los guarda con sus "
                "secretos en claro: cuando compruebes que todo funciona, la podés borrar"
            )
        if self.avisos:
            partes.append(f"avisos: {' | '.join(self.avisos)}")
        return ". ".join(partes) + "."

    def lineas(self) -> list[str]:
        """El informe completo, una línea por elemento, para mostrar a quien pidió la importación."""
        ancho = max(len(etiqueta) for etiqueta in ETIQUETAS.values())
        lineas = [f"Importación de archivos anteriores a la cuenta {self.user_id}:"]
        for resultado in self.resultados:
            detalle = f" ({resultado.detalle})" if resultado.detalle else ""
            lineas.append(f"  {ETIQUETAS[resultado.estado]:<{ancho}}  {resultado.elemento}{detalle}")
        if self.retirados:
            lineas.append(f"Archivos retirados a {self.carpeta_de_respaldo}: {', '.join(self.retirados)}.")
            lineas.append(
                "Esa carpeta guarda los archivos anteriores tal como estaban, con sus secretos en claro: "
                "cuando compruebes que todo funciona, la podés borrar."
            )
        lineas.extend(f"Aviso: {aviso}" for aviso in self.avisos)
        return lineas


def _es_enlace(ruta: Path) -> bool:
    """La entrada es un enlace simbólico o una unión de directorios de Windows."""
    return ruta.is_symlink() or _es_union(ruta)


def _tiene_archivos(carpeta: Path) -> bool:
    """La carpeta tiene algún archivo; las marcas (de una mudanza y de las carpetas del tutor) y las copias a medio
    hacer no cuentan."""
    return any(
        entrada.is_file()
        and entrada.name not in (MARCA_DE_MUDANZA, MARCA_CARPETAS_DEL_TUTOR)
        and not entrada.name.endswith(SUFIJO_DE_COPIA_EN_CURSO)
        for entrada in carpeta.rglob("*")
    )


def _mover_sin_pisar(origen: Path, destino: Path) -> None:
    """Mueve un archivo sin reemplazar nunca el destino: si ya existe levanta `FileExistsError`.

    El origen se quita recién cuando el contenido está entero en el destino: un corte en el medio deja, a lo
    sumo, el archivo en los dos lados o una copia `.mudanza-en-curso` que la pasada siguiente vuelve a escribir.
    """
    try:
        os.link(origen, destino)
    except FileExistsError:
        raise
    except OSError:
        # Otro volumen, o un sistema de archivos sin enlaces duros: copia entera a un vecino y recién ahí se publica
        temporal = destino.with_name(destino.name + SUFIJO_DE_COPIA_EN_CURSO)
        try:
            shutil.copy2(origen, temporal)
            if os.path.lexists(destino):
                raise FileExistsError(str(destino))
            os.rename(temporal, destino)
        finally:
            temporal.unlink(missing_ok=True)
    os.unlink(origen)


def _leer_texto(archivo: Path) -> str:
    """Contenido del archivo sin espacios alrededor; levanta `_ArchivoInservible` si no se puede leer como texto."""
    try:
        if archivo.stat().st_size > MAX_BYTES_DE_UN_ARCHIVO:
            raise _ArchivoInservible(f"{archivo.name} es demasiado grande para ser lo que se espera")
        return archivo.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError:
        raise _ArchivoInservible(f"{archivo.name} no es un archivo de texto") from None
    except OSError as error:
        raise _ArchivoInservible(f"{archivo.name} no se pudo leer ({type(error).__name__})") from None


def _leer_objeto_json(archivo: Path) -> dict[str, Any]:
    """El objeto JSON que trae el archivo; levanta `_ArchivoInservible` si no es JSON o no es un objeto."""
    texto = _leer_texto(archivo)
    try:
        datos = json.loads(texto)
    except ValueError:
        raise _ArchivoInservible(f"{archivo.name} no es un JSON válido") from None
    if not isinstance(datos, dict):
        raise _ArchivoInservible(f"{archivo.name} no tiene la forma esperada")
    return datos


class _Importacion:
    """Una pasada de importación sobre el directorio `origen` para una cuenta."""

    def __init__(self, conn: sqlite3.Connection, user_id: int, es_admin: bool, origen: Path) -> None:
        self.conn = conn
        self.user_id = user_id
        self.es_admin = es_admin
        self.origen = origen
        self.raiz = origen.resolve()
        self.secretos = AlmacenDeSecretos(conn, user_id)
        self.ajustes = AjustesDeCuenta(conn, user_id)
        self.informe = Informe(user_id=user_id)

    # --- Informe y retiro ---

    def anotar(self, elemento: str, estado: str, detalle: str = "") -> None:
        self.informe.resultados.append(Resultado(elemento, estado, detalle))

    def _dentro_del_origen(self, ruta: Path) -> bool:
        return ruta.resolve().is_relative_to(self.raiz)

    def _carpeta_de_respaldo(self) -> Path:
        if self.informe.carpeta_de_respaldo is None:
            carpeta = self.origen / f"{PREFIJO_DEL_RESPALDO}{datetime.now().astimezone().date().isoformat()}"
            carpeta.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(carpeta, 0o700)
            except OSError:
                pass
            self.informe.carpeta_de_respaldo = carpeta
        return self.informe.carpeta_de_respaldo

    def retirar(self, archivo: Path) -> None:
        """Mueve el archivo a la carpeta de respaldo sin pisar nada; uno de fuera del origen se deja y se avisa."""
        if not archivo.is_file():
            return
        if not self._dentro_del_origen(archivo):
            self.informe.avisos.append(
                f"{archivo} está fuera del directorio de datos y no se movió: la cuenta ya tiene ese dato cargado, "
                "así que podés guardarlo en otro lado o borrarlo."
            )
            return
        relativa = archivo.resolve().relative_to(self.raiz)
        try:
            destino = self._carpeta_de_respaldo() / relativa
            intento = 1
            while destino.exists():
                intento += 1
                destino = destino.with_name(f"{relativa.name}.{intento}")
            destino.parent.mkdir(parents=True, exist_ok=True)
            os.rename(archivo, destino)
        except OSError as error:
            self.informe.avisos.append(
                f"{relativa.as_posix()} no se pudo retirar ({type(error).__name__}) y sigue en su lugar."
            )
            return
        self.informe.retirados.append(relativa.as_posix())

    def _paso(self, elemento: str, importar: Callable[[], None]) -> None:
        """Corre la importación de un elemento; lo que falle queda anotado y no corta el resto."""
        try:
            importar()
        except _ArchivoInservible as error:
            self.anotar(elemento, ESTADO_FALLO, f"{error}; quedó en su lugar")
        except SecretoIlegible:
            self.anotar(elemento, ESTADO_FALLO, "no se pudo descifrar lo que la cuenta ya tiene guardado")
        except ClaveMaestraInvalida:
            # Con la clave maestra mal formada no se puede guardar ningún secreto: se corta toda la importación
            raise
        except ERRORES_DE_IMPORTACION as error:
            # El mensaje de un error imprevisto podría repetir contenido de un archivo: solo se informa su tipo
            self.anotar(elemento, ESTADO_FALLO, f"error inesperado ({type(error).__name__})")

    # --- Formas comunes ---

    def _secreto_desde_archivos(
        self, elemento: str, secreto: str, archivos: list[Path], guardar: Callable[[str], None]
    ) -> Path | None:
        """Carga el secreto desde el primero de `archivos` que sirva, retira los que se pudieron leer y lo devuelve.

        `guardar` levanta `ValueError` si el contenido no es lo que se espera; su mensaje no repite el contenido.
        """
        presentes = [archivo for archivo in archivos if archivo.is_file()]
        if not presentes:
            self.anotar(elemento, ESTADO_NO_ESTABA)
            return None
        if self.secretos.tiene(secreto):
            self.anotar(elemento, ESTADO_YA_LO_TENIA)
            for archivo in presentes:
                self.retirar(archivo)
            return None
        importado_desde: Path | None = None
        fallas: dict[Path, str] = {}
        for archivo in presentes:
            try:
                contenido = _leer_texto(archivo)
                if contenido and importado_desde is None:
                    guardar(contenido)
                    importado_desde = archivo
            except (_ArchivoInservible, ValueError) as error:
                fallas[archivo] = str(error)
        if importado_desde is None:
            if fallas:
                raise _ArchivoInservible("; ".join(fallas.values()))
            self.anotar(elemento, ESTADO_NO_ESTABA, "el archivo estaba vacío")
            return None
        self.anotar(elemento, ESTADO_IMPORTADO, f"desde {importado_desde.name}")
        for archivo in presentes:
            if archivo in fallas:
                self.informe.avisos.append(f"{fallas[archivo]}: quedó en su lugar y puede tener un secreto en claro.")
            else:
                self.retirar(archivo)
        return importado_desde

    def _ajuste_desde_texto(
        self,
        elemento: str,
        ajuste: str,
        archivo: Path,
        guardar: Callable[[str], None],
        aceptable: Callable[[str], bool] = lambda valor: True,
    ) -> None:
        if not archivo.is_file():
            self.anotar(elemento, ESTADO_NO_ESTABA)
            return
        if self.ajustes.leer(ajuste) is not None:
            self.anotar(elemento, ESTADO_YA_LO_TENIA)
            self.retirar(archivo)
            return
        valor = _leer_texto(archivo)
        if not valor:
            self.anotar(elemento, ESTADO_NO_ESTABA, "el archivo estaba vacío")
            return
        if not aceptable(valor):
            raise _ArchivoInservible(f"{archivo.name} no trae un valor válido")
        guardar(valor)
        self.anotar(elemento, ESTADO_IMPORTADO)
        self.retirar(archivo)

    # --- IA ---

    def _claves_y_modelo(self) -> None:
        pasarela = GeminiGateway(self.conn, self.user_id)
        self._paso(
            ELEMENTO_CLAVE_GRATUITA,
            lambda: self._secreto_desde_archivos(
                ELEMENTO_CLAVE_GRATUITA,
                SECRETO_GEMINI_CLAVE_GRATUITA,
                [self.origen / nombre for nombre in ARCHIVOS_DE_LA_CLAVE_GRATUITA],
                lambda clave: pasarela.save_keys_config(free_key=clave),
            ),
        )
        self._paso(
            ELEMENTO_CLAVE_PAGA,
            lambda: self._secreto_desde_archivos(
                ELEMENTO_CLAVE_PAGA,
                SECRETO_GEMINI_CLAVE_PAGA,
                [self.origen / nombre for nombre in ARCHIVOS_DE_LA_CLAVE_PAGA],
                lambda clave: pasarela.save_keys_config(paid_key=clave),
            ),
        )
        self._paso(
            ELEMENTO_NIVEL,
            lambda: self._ajuste_desde_texto(
                ELEMENTO_NIVEL,
                AJUSTE_GEMINI_NIVEL_ACTIVO,
                self.origen / ARCHIVO_DEL_NIVEL,
                lambda nivel: pasarela.save_keys_config(tier=nivel),
                lambda nivel: nivel.lower() in NIVELES,
            ),
        )
        self._paso(
            ELEMENTO_MODELO,
            lambda: self._ajuste_desde_texto(
                ELEMENTO_MODELO,
                AJUSTE_GEMINI_MODELO,
                self.origen / ARCHIVO_DEL_MODELO,
                pasarela.save_model,
                lambda modelo: len(modelo) <= LARGO_MAXIMO_DEL_MODELO and len(modelo.split()) == 1,
            ),
        )

    # --- Prompts y Duolingo ---

    def _prompts(self) -> None:
        prompts = SystemPromptManager(self.conn, self.user_id)
        for elemento, ajuste, relativa, guardar in (
            (ELEMENTO_PROMPT_DE_RUTAS, AJUSTE_PROMPT_RUTA, ARCHIVO_DEL_PROMPT_DE_RUTAS, prompts.save_roadmap_system_prompt),
            (ELEMENTO_PROMPT_DE_CLASES, AJUSTE_PROMPT_CLASE, ARCHIVO_DEL_PROMPT_DE_CLASES, prompts.save_lesson_system_prompt),
        ):
            self._paso(
                elemento,
                lambda e=elemento, a=ajuste, r=relativa, g=guardar: self._ajuste_desde_texto(e, a, self.origen / r, g),
            )

    def _duolingo(self) -> None:
        archivo = self.origen / ARCHIVO_DE_DUOLINGO
        if not archivo.is_file():
            self.anotar(ELEMENTO_DUOLINGO, ESTADO_NO_ESTABA)
            return
        if any(self.ajustes.leer(ajuste) is not None for ajuste in (AJUSTE_DUOLINGO_USUARIO, AJUSTE_DUOLINGO_CACHE)):
            self.anotar(ELEMENTO_DUOLINGO, ESTADO_YA_LO_TENIA)
            self.retirar(archivo)
            return
        datos = _leer_objeto_json(archivo)
        # El usuario sale de la caché y de ningún otro lado: sin él no hay a quién atribuirla
        usuario = datos.get("username")
        if not isinstance(usuario, str) or not usuario.strip():
            raise _ArchivoInservible(f"{archivo.name} no trae el usuario de Duolingo")
        try:
            perfil = DuolingoProfile(**datos)
        except (TypeError, ValueError):
            raise _ArchivoInservible(f"{archivo.name} no tiene la forma de un perfil de Duolingo") from None
        DuolingoClient(self.conn, self.user_id).fijar_usuario(usuario)
        self.ajustes.guardar(AJUSTE_DUOLINGO_CACHE, perfil.model_dump())
        self.anotar(ELEMENTO_DUOLINGO, ESTADO_IMPORTADO)
        self.retirar(archivo)

    # --- Vault ---

    def _vault_externo(self) -> Path:
        """Trata el vault que venía por variable de entorno y devuelve la carpeta del vault anterior a mover."""
        anterior = self.origen / CARPETA_DEL_VAULT_ANTERIOR
        variable = next((v for v in VARIABLES_DEL_VAULT if (os.getenv(v) or "").strip()), None)
        if variable is None:
            self.anotar(ELEMENTO_VAULT_EXTERNO, ESTADO_NO_ESTABA)
            return anterior
        carpeta = Path(os.environ[variable].strip())
        if not carpeta.is_dir():
            self.anotar(ELEMENTO_VAULT_EXTERNO, ESTADO_FALLO, f"la carpeta de {variable} no existe")
        elif self._dentro_del_origen(carpeta):
            self.anotar(
                ELEMENTO_VAULT_EXTERNO,
                ESTADO_NO_ESTABA,
                f"la carpeta de {variable} está dentro del directorio de datos: se trata como vault anterior",
            )
            return carpeta
        elif vault_externo_fijado(self.conn, self.user_id) is not None:
            self.anotar(ELEMENTO_VAULT_EXTERNO, ESTADO_YA_LO_TENIA)
        elif not self.es_admin:
            self.anotar(
                ELEMENTO_VAULT_EXTERNO,
                ESTADO_FALLO,
                f"solo un administrador puede usar como vault la carpeta de {variable}, que está fuera del "
                "directorio de datos; la carpeta no se tocó",
            )
        else:
            try:
                fijar_vault_externo(self.conn, self.user_id, carpeta)
            except CarpetaDeVaultInvalida as error:
                self.anotar(ELEMENTO_VAULT_EXTERNO, ESTADO_FALLO, str(error))
            else:
                self.anotar(ELEMENTO_VAULT_EXTERNO, ESTADO_IMPORTADO, f"desde {variable}; la carpeta no se movió")
        return anterior

    def _cuenta_de_la_mudanza(self, anterior: Path) -> int | None:
        """Cuenta a la que se está mudando ese vault según su marca; None si no hay marca o no se entiende."""
        try:
            cuenta = json.loads((anterior / MARCA_DE_MUDANZA).read_text(encoding="utf-8"))["user_id"]
        except (OSError, ValueError, TypeError, LookupError):
            return None
        return cuenta if isinstance(cuenta, int) and not isinstance(cuenta, bool) else None

    def _mudar_notas(self, anterior: Path, propio: Path) -> tuple[int, list[str], list[str]]:
        """Pasa al vault de la cuenta cada archivo del anterior, sin pisar ninguno.

        Devuelve cuántos movió, los que ya existen con otro contenido en el destino y los que no se pudieron
        mover (rutas relativas); los de esos dos grupos quedan donde estaban. Un archivo que ya está idéntico
        en el destino se quita del origen: su contenido no se pierde.
        """
        movidos = 0
        distintos: list[str] = []
        pendientes: list[str] = []
        for carpeta, subcarpetas, nombres in os.walk(anterior, followlinks=False):
            actual = Path(carpeta)
            enlaces = [nombre for nombre in subcarpetas if _es_enlace(actual / nombre)]
            pendientes.extend((actual / nombre).relative_to(anterior).as_posix() for nombre in sorted(enlaces))
            subcarpetas[:] = sorted(nombre for nombre in subcarpetas if nombre not in enlaces)
            for nombre in sorted(nombres):
                origen = actual / nombre
                relativa = origen.relative_to(anterior).as_posix()
                if relativa == MARCA_DE_MUDANZA or nombre.endswith(SUFIJO_DE_COPIA_EN_CURSO):
                    continue
                destino = propio / relativa
                try:
                    if _es_enlace(origen) or not origen.is_file():
                        pendientes.append(relativa)
                    elif not os.path.lexists(destino):
                        destino.parent.mkdir(parents=True, exist_ok=True)
                        _mover_sin_pisar(origen, destino)
                        movidos += 1
                    elif destino.is_file() and not _es_enlace(destino) and filecmp.cmp(origen, destino, shallow=False):
                        # Un corte anterior lo dejó en los dos lados: el contenido ya está en el destino
                        origen.unlink()
                        movidos += 1
                    else:
                        distintos.append(relativa)
                except FileExistsError:
                    distintos.append(relativa)
                except OSError:
                    pendientes.append(relativa)
        return movidos, distintos, pendientes

    def _quitar_vault_vacio(self, anterior: Path) -> None:
        """Quita la marca, las copias a medio hacer y las carpetas del vault anterior, que ya no tiene notas."""
        try:
            for sobrante in [anterior / MARCA_DE_MUDANZA, *anterior.rglob(f"*{SUFIJO_DE_COPIA_EN_CURSO}")]:
                if sobrante.is_file() and not _es_enlace(sobrante):
                    sobrante.unlink()
            for carpeta, _, _ in os.walk(anterior, topdown=False, followlinks=False):
                os.rmdir(carpeta)
        except OSError:
            self.informe.avisos.append(f"{anterior} quedó sin notas pero no se pudo quitar: la podés borrar.")

    def _vault_anterior(self, anterior: Path) -> None:
        if not anterior.is_dir():
            self.anotar(ELEMENTO_VAULT, ESTADO_NO_ESTABA)
            return
        en_mudanza = self._cuenta_de_la_mudanza(anterior)
        if not _tiene_archivos(anterior) and en_mudanza != self.user_id:
            self.anotar(ELEMENTO_VAULT, ESTADO_NO_ESTABA)
            return
        resuelta = anterior.resolve()
        if _es_enlace(anterior) or not resuelta.is_relative_to(self.raiz):
            self.anotar(
                ELEMENTO_VAULT,
                ESTADO_FALLO,
                f"{anterior} es un enlace a una carpeta de fuera del directorio de datos y no se movió; un "
                "administrador puede registrarla como vault externo",
            )
            return
        relativa = resuelta.relative_to(self.raiz)
        if not relativa.parts or relativa.parts[0] == CARPETA_DE_LAS_CUENTAS or relativa.parts[0].startswith(PREFIJO_DEL_RESPALDO):
            self.anotar(ELEMENTO_VAULT, ESTADO_FALLO, f"{anterior} no es la carpeta de un vault anterior y no se movió")
            return
        if vault_externo_fijado(self.conn, self.user_id) is not None:
            self.anotar(ELEMENTO_VAULT, ESTADO_YA_LO_TENIA, f"la cuenta usa un vault externo; el anterior quedó en {anterior}")
            return
        if en_mudanza is not None and en_mudanza != self.user_id:
            self.anotar(
                ELEMENTO_VAULT,
                ESTADO_FALLO,
                f"{anterior} está a medio mudar a otra cuenta (la {en_mudanza}) y no se tocó: terminá esa mudanza "
                "corriendo la importación para esa cuenta",
            )
            return
        propio = vault_propio(self.user_id)
        if en_mudanza is None:
            if _tiene_archivos(propio):
                # Sin marca, las notas del vault propio las escribió la cuenta: los dos vaults no se mezclan
                self.anotar(
                    ELEMENTO_VAULT,
                    ESTADO_YA_LO_TENIA,
                    f"el vault de la cuenta ya tiene notas; el anterior quedó en {anterior}",
                )
                return
            (anterior / MARCA_DE_MUDANZA).write_text(json.dumps({"user_id": self.user_id}), encoding="utf-8")
        movidos, distintos, pendientes = self._mudar_notas(anterior, propio)
        if pendientes:
            self.anotar(
                ELEMENTO_VAULT,
                ESTADO_FALLO,
                f"{movidos} archivo(s) movidos al vault de la cuenta; {len(pendientes)} no se pudieron mover y siguen "
                f"en {anterior}: volvé a correr la importación para terminar",
            )
            return
        if distintos:
            muestra = ", ".join(distintos[:5]) + ("…" if len(distintos) > 5 else "")
            self.informe.avisos.append(
                f"{len(distintos)} nota(s) del vault anterior ya existen, con otro contenido, en el vault de la "
                f"cuenta y no se pisaron: quedaron en {anterior} ({muestra}). Revisalas y movelas o borralas a mano."
            )
        else:
            self._quitar_vault_vacio(anterior)
        if movidos:
            self.anotar(ELEMENTO_VAULT, ESTADO_IMPORTADO, f"{movidos} archivo(s) movidos al vault de la cuenta")
        elif distintos:
            self.anotar(
                ELEMENTO_VAULT,
                ESTADO_YA_LO_TENIA,
                f"las notas que quedan en {anterior} ya existen, con otro contenido, en el vault de la cuenta",
            )
        else:
            self.anotar(ELEMENTO_VAULT, ESTADO_YA_LO_TENIA, "la mudanza del vault anterior ya había terminado")

    # --- Pasada completa ---

    def correr(self) -> Informe:
        self._claves_y_modelo()
        self._prompts()
        self._paso(ELEMENTO_DUOLINGO, self._duolingo)
        self._paso(ELEMENTO_VAULT, lambda: self._vault_anterior(self._vault_externo()))
        self.informe.sin_clave_de_ia = not any(self.secretos.tiene(secreto) for secreto in SECRETOS_DE_CLAVES)
        definidas = [variable for variable in VARIABLES_ANTERIORES if (os.getenv(variable) or "").strip()]
        if definidas:
            self.informe.avisos.append(
                f"Estas variables de entorno ya no se leen y se pueden quitar: {', '.join(definidas)}."
            )
        return self.informe


def importar_archivos_anteriores(conn: sqlite3.Connection, user_id: int, origen: Path | str | None = None) -> Informe:
    """Carga en la cuenta lo que no tenga de los archivos y variables anteriores, y retira los archivos ya cargados.

    `origen` es el directorio de datos a recorrer; sin él, el del servidor. Se puede correr las veces que haga
    falta: no duplica ni pisa lo que la cuenta ya tiene. Un archivo ilegible queda informado y no corta el resto.
    Levanta `UsuarioNoEncontrado` si la cuenta no existe.
    """
    fila = RepositorioAuth(conn).usuario_por_id(exigir_cuenta(user_id))
    if fila is None:
        raise UsuarioNoEncontrado()
    carpeta = Path(origen) if origen is not None else get_data_dir()
    return _Importacion(conn, fila["id"], fila["rol"] == ROL_ADMIN, carpeta).correr()
