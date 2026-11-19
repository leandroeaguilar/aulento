"""Gancho de construcción del paquete. Lo declarativo vive en `pyproject.toml`.

Los documentos que la app muestra en su pestaña de documentación se escriben en `docs/`, fuera del
paquete, y `package-data` no alcanza archivos de afuera. Sin este gancho, el wheel (y la imagen de la
nube, que instala el wheel) sale sin ellos y la app responde «Documentación en preparación». Al
construir, se copian a `aulento/documentos/`, donde `aulento.web.app` los busca primero.
"""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

RAIZ = Path(__file__).resolve().parent

# Los mismos que `DOCUMENTOS_DE_LA_APP` de `aulento.web.app`: un test construye el wheel y lo comprueba
DOCUMENTOS_DE_LA_APP = (
    "MANUAL_DE_USUARIO.md",
    "REFERENCIA_API.md",
    "GUIA_MCP.md",
    "REFERENCIA_CLI.md",
)


class BuildPyConDocumentos(build_py):
    """`build_py` que además copia los documentos de la app dentro del paquete."""

    def run(self):
        super().run()
        # En modo editable la app los lee de `docs/`, en el propio repo
        if getattr(self, "editable_mode", False):
            return
        destino = Path(self.build_lib) / "aulento" / "documentos"
        destino.mkdir(parents=True, exist_ok=True)
        for nombre in DOCUMENTOS_DE_LA_APP:
            origen = RAIZ / "docs" / nombre
            if not origen.is_file():
                # Mejor fallar al construir que publicar un paquete que muestra «en preparación»
                raise FileNotFoundError(f"Falta {origen}: el paquete tiene que llevar los documentos de la app")
            self.copy_file(str(origen), str(destino / nombre))


setup(cmdclass={"build_py": BuildPyConDocumentos})
