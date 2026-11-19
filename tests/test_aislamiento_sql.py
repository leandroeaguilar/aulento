"""Recorrido estático del SQL de `src/` (033, R6): ninguna sentencia lee ni escribe una tabla raíz sin la cuenta.

El constructor de cada repositorio guarda la cuenta, pero el filtro lo escribe a mano cada sentencia. Este test
lee el código con `ast`, reconstruye cada sentencia SQL (también las que se arman con f-strings, concatenación,
`+=` o listas de condiciones) y falla si una nombra una tabla raíz sin condicionarla a `user_id`.

Qué exige, por cada `SELECT` (cada subconsulta y cada rama de un `UNION` se mira por separado):

- `INSERT INTO <raíz> (...)`: `user_id` entre las columnas.
- `UPDATE <raíz> ... WHERE`: una comparación de `user_id` después del `WHERE` (el `SET user_id = ?` no cuenta).
- `FROM <raíz>` y `JOIN <raíz>` (lecturas y borrados): una comparación de `user_id` en esa misma consulta.

Además de las ocho tablas raíz mira `knowledge_embeddings`, la tabla del almacén de vectores (R11),
`secretos_usuario` y `ajustes_usuario`, los almacenes por cuenta de la 034, y `materiales`, de la 048.
Una tabla puesta por una variable (`FROM {tabla}`) se trata como raíz. `user_id IS NULL` no es una comparación:
no ata la sentencia a ninguna cuenta. El DDL (`CREATE`, `ALTER`, `DROP`) no lee ni escribe filas y no se mira.

Qué NO ve (lo cubren las baterías de dos cuentas de `test_nube_aislamiento_api.py` y `test_nube_aislamiento_mcp.py`):

- Que el valor comparado sea la cuenta correcta, o que la comparación esté dentro de un `OR` que la anule.
- Las tablas dependientes (cursos, temas, clases, repasos...) leídas por su `id` sin subir hasta la raíz.
- SQL cuyos pedazos viajan entre funciones o módulos como argumentos, o que sale de `str.join` sobre datos
  de ejecución, de un archivo o de la base.
- El orden de ejecución: de una variable armada por ramas se juntan todos los `+=` que siguen a cada asignación.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ_DEL_CODIGO = Path(__file__).resolve().parents[1] / "src"

TABLAS_RAIZ = (
    "plataformas",
    "libros_lectura",
    "bloques_horarios",
    "fsrs_items",
    "sesiones_estudio",
    "rutas_aprendizaje",
    "api_usage_logs",
    "mcp_audit_logs",
)
# La tabla del almacén de vectores opcional (PostgreSQL) también lleva dueño por fila (R11)
# Los secretos cifrados y los ajustes de cada cuenta (034): una lectura sin dueño mezclaría claves de dos personas
TABLAS_POR_CUENTA = ("secretos_usuario", "ajustes_usuario")
# Los materiales subidos desde la PC (048): el texto de los apuntes de una cuenta no se lee desde otra
TABLAS_VIGILADAS = (*TABLAS_RAIZ, "knowledge_embeddings", *TABLAS_POR_CUENTA, "materiales")

# Lo que el recorrido no puede resolver (una variable, una llamada) queda entre estas comillas
ABRE, CIERRA = "«", "»"
_TABLA = rf"(?:{'|'.join(TABLAS_VIGILADAS)})(?![\w{CIERRA}])|{ABRE}[^{CIERRA}]*{CIERRA}"
MENCION = re.compile(rf"\b(FROM|JOIN|INTO|UPDATE)\s+[\"`\[]?({_TABLA})", re.IGNORECASE)
COMPARACION = re.compile(r"\buser_id\s*(?:=|\bIN\b)|=\s*(?:\w+\.)?user_id\b", re.IGNORECASE)
EMPIEZA_COMO_SQL = re.compile(r"^\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH|REPLACE)\b", re.IGNORECASE)
ABRE_SUBCONSULTA = re.compile(r"\(\s*(?:SELECT|WITH)\b", re.IGNORECASE)
UNION = re.compile(r"\b(?:UNION(?:\s+ALL)?|EXCEPT|INTERSECT)\b", re.IGNORECASE)


# --- El analizador ---


def consultas_de(sentencia: str) -> list[str]:
    """Parte una sentencia en sus consultas: la exterior, cada subconsulta entre paréntesis y cada rama de un UNION."""
    consultas: list[list[str]] = [[]]
    pila: list[tuple[int, int]] = []  # (índice de la consulta, profundidad de paréntesis donde se abrió)
    actual, profundidad, i = 0, 0, 0
    while i < len(sentencia):
        caracter = sentencia[i]
        if caracter == "(":
            profundidad += 1
            if ABRE_SUBCONSULTA.match(sentencia, i):
                pila.append((actual, profundidad))
                consultas.append([])
                actual = len(consultas) - 1
                i += 1
                continue
        elif caracter == ")":
            if pila and pila[-1][1] == profundidad:
                actual = pila.pop()[0]
                profundidad -= 1
                i += 1
                continue
            profundidad -= 1
        consultas[actual].append(caracter)
        i += 1
    return [rama for consulta in consultas for rama in UNION.split("".join(consulta)) if rama.strip()]


def faltas_de(sql: str) -> list[str]:
    """Las faltas de un texto SQL: una por cada mención de una tabla raíz que no queda atada a una cuenta."""
    faltas = []
    sin_comentarios = re.sub(r"--[^\n]*", " ", sql)
    for sentencia in sin_comentarios.split(";"):
        if not EMPIEZA_COMO_SQL.match(sentencia):
            continue  # prosa, o un fragmento: se mira dentro de la sentencia que lo usa
        for consulta in consultas_de(sentencia):
            for mencion in MENCION.finditer(consulta):
                verbo, tabla = mencion.group(1).upper(), mencion.group(2)
                if verbo == "INTO":
                    columnas = re.match(r"[\"`\]]?\s*\(([^()]*)\)", consulta[mencion.end():])
                    atada = columnas is not None and "user_id" in {c.strip() for c in columnas.group(1).split(",")}
                    falta = "el INSERT no lleva `user_id` entre sus columnas"
                elif verbo == "UPDATE":
                    donde = re.search(r"\bWHERE\b(.*)", consulta[mencion.end():], re.IGNORECASE | re.DOTALL)
                    atada = donde is not None and COMPARACION.search(donde.group(1)) is not None
                    falta = "el UPDATE no compara `user_id` en su WHERE"
                else:
                    atada = COMPARACION.search(consulta) is not None
                    falta = f"el {verbo} no compara `user_id` en su consulta"
                if not atada:
                    faltas.append(f"{tabla}: {falta}")
    return faltas


@dataclass(frozen=True)
class Hallazgo:
    archivo: str
    contexto: str
    linea: int
    falta: str
    sql: str

    @property
    def lugar(self) -> tuple[str, str]:
        return self.archivo, self.contexto

    @property
    def sentencia(self) -> tuple[str, str, str]:
        """Lo que identifica a la sentencia en la lista de excepciones: dónde está y su texto, sin saltos de línea."""
        return self.archivo, self.contexto, " ".join(self.sql.split())

    def __str__(self) -> str:
        return f"{self.archivo}:{self.linea} ({self.contexto}) — {self.falta}\n      {self.sentencia[2][:300]}"


class _Ambito:
    """Una función (o el módulo): sus variables de texto y dónde buscar las que no define."""

    def __init__(self, nombre: str, exterior: "_Ambito | None"):
        self.nombre = nombre
        self.exterior = exterior
        # Cada variable: sus unidades en orden de aparición; una asignación abre una unidad y un `+=` la extiende
        self.variables: dict[str, list[list[ast.expr]]] = {}

    def unidades(self, nombre: str) -> list[list[ast.expr]] | None:
        ambito: _Ambito | None = self
        while ambito is not None:
            if nombre in ambito.variables:
                return ambito.variables[nombre]
            ambito = ambito.exterior
        return None


def _texto(nodo: ast.expr, ambito: _Ambito, en_curso: frozenset[str] = frozenset()) -> str | None:
    """El texto que arma una expresión, o None si no arma texto. Lo que no se puede resolver queda como «expresión»."""

    def o_incognita(parte: ast.expr) -> str:
        if isinstance(parte, ast.Name) and parte.id not in en_curso:
            unidades = ambito.unidades(parte.id)
            if unidades is not None:
                dentro = en_curso | {parte.id}
                return " ".join(_texto(valor, ambito, dentro) or "" for unidad in unidades for valor in unidad)
        resuelto = _texto(parte, ambito, en_curso)
        return resuelto if resuelto is not None else f"{ABRE}{ast.unparse(parte)}{CIERRA}"

    if isinstance(nodo, ast.Constant):
        return nodo.value if isinstance(nodo.value, str) else None
    if isinstance(nodo, ast.JoinedStr):
        return "".join(
            o_incognita(parte.value) if isinstance(parte, ast.FormattedValue) else str(parte.value) for parte in nodo.values
        )
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        izquierda, derecha = _texto(nodo.left, ambito, en_curso), _texto(nodo.right, ambito, en_curso)
        if izquierda is None and derecha is None:
            return None
        return o_incognita(nodo.left) + o_incognita(nodo.right)
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Mod):
        plantilla = _texto(nodo.left, ambito, en_curso)
        return None if plantilla is None else re.sub(r"%\(?\w*\)?[sdr]", f"{ABRE}%{CIERRA}", plantilla)
    if isinstance(nodo, ast.IfExp):
        ramas = [_texto(nodo.body, ambito, en_curso), _texto(nodo.orelse, ambito, en_curso)]
        return None if ramas == [None, None] else " ".join(rama or "" for rama in ramas)
    if isinstance(nodo, ast.List | ast.Tuple):
        elementos = [_texto(elemento, ambito, en_curso) for elemento in nodo.elts]
        return " ".join(e for e in elementos if e is not None) if any(e is not None for e in elementos) else None
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
        if nodo.func.attr == "format":
            plantilla = _texto(nodo.func.value, ambito, en_curso)
            return None if plantilla is None else re.sub(r"\{[^{}]*\}", f"{ABRE}format{CIERRA}", plantilla)
        if nodo.func.attr == "join" and len(nodo.args) == 1 and _texto(nodo.func.value, ambito, en_curso) is not None:
            return o_incognita(nodo.args[0])
    return None


class _Recorrido(ast.NodeVisitor):
    """Junta, por ámbito, las variables de texto y las expresiones de texto sueltas (argumentos, retornos...)."""

    def __init__(self) -> None:
        self.ambito = _Ambito("<módulo>", None)
        self.sueltas: list[tuple[_Ambito, ast.expr]] = []
        self.ambitos: list[_Ambito] = [self.ambito]

    def _entrar(self, nodo: ast.AST, nombre: str) -> None:
        exterior = self.ambito
        calificado = nombre if exterior.nombre == "<módulo>" else f"{exterior.nombre}.{nombre}"
        self.ambito = _Ambito(calificado, exterior)
        self.ambitos.append(self.ambito)
        for hijo in ast.iter_child_nodes(nodo):
            self.visit(hijo)
        self.ambito = exterior

    def visit_FunctionDef(self, nodo: ast.FunctionDef) -> None:
        self._entrar(nodo, nodo.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, nodo: ast.ClassDef) -> None:
        # Una clase no es un ámbito de variables para sus métodos: solo les presta el nombre
        exterior = self.ambito
        self.ambito = _Ambito(nodo.name if exterior.nombre == "<módulo>" else f"{exterior.nombre}.{nodo.name}", exterior)
        self.ambitos.append(self.ambito)
        for hijo in nodo.body:
            self.visit(hijo)
        self.ambito = exterior

    def _anotar(self, nombre: str, valor: ast.expr, abre_unidad: bool) -> None:
        unidades = self.ambito.variables.setdefault(nombre, [])
        if abre_unidad or not unidades:
            unidades.append([])
        unidades[-1].append(valor)
        if _texto(valor, self.ambito) is None:
            # No es texto (una llamada, una comprensión...): el SQL puede estar adentro
            self.visit(valor)

    def visit_Assign(self, nodo: ast.Assign) -> None:
        if len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            self._anotar(nodo.targets[0].id, nodo.value, abre_unidad=True)
        else:
            self.visit(nodo.value)

    def visit_AnnAssign(self, nodo: ast.AnnAssign) -> None:
        if isinstance(nodo.target, ast.Name) and nodo.value is not None:
            self._anotar(nodo.target.id, nodo.value, abre_unidad=True)
        elif nodo.value is not None:
            self.visit(nodo.value)

    def visit_AugAssign(self, nodo: ast.AugAssign) -> None:
        if isinstance(nodo.target, ast.Name):
            self._anotar(nodo.target.id, nodo.value, abre_unidad=False)
        else:
            self.visit(nodo.value)

    def visit_Expr(self, nodo: ast.Expr) -> None:
        if isinstance(nodo.value, ast.Constant):
            return  # una cadena suelta es un docstring: prosa, no SQL
        llamada = nodo.value
        if (
            isinstance(llamada, ast.Call)
            and isinstance(llamada.func, ast.Attribute)
            and llamada.func.attr in ("append", "extend")
            and isinstance(llamada.func.value, ast.Name)
            and len(llamada.args) == 1
        ):
            self._anotar(llamada.func.value.id, llamada.args[0], abre_unidad=False)
            return
        self.visit(llamada)

    def generic_visit(self, nodo: ast.AST) -> None:
        if isinstance(nodo, ast.expr) and _texto(nodo, self.ambito) is not None:
            self.sueltas.append((self.ambito, nodo))
            if isinstance(nodo, ast.Call):
                # `"...".format(x)` y `", ".join(x)`: los argumentos pueden traer SQL propio
                for argumento in nodo.args:
                    self.visit(argumento)
            return
        super().generic_visit(nodo)


def hallazgos_en(codigo: str, archivo: str = "<ejemplo>") -> list[Hallazgo]:
    """Las sentencias de un archivo Python que nombran una tabla raíz sin atarla a una cuenta."""
    recorrido = _Recorrido()
    recorrido.visit(ast.parse(codigo))
    candidatas: list[tuple[_Ambito, int, str]] = [
        (ambito, nodo.lineno, _texto(nodo, ambito) or "") for ambito, nodo in recorrido.sueltas
    ]
    for ambito in recorrido.ambitos:
        for nombre, unidades in ambito.variables.items():
            for unidad in unidades:
                textos = [_texto(valor, ambito, frozenset({nombre})) for valor in unidad]
                if any(texto is not None for texto in textos):
                    candidatas.append((ambito, unidad[0].lineno, " ".join(texto or "" for texto in textos)))
    return sorted(
        (
            Hallazgo(archivo, ambito.nombre, linea, falta, sql)
            for ambito, linea, sql in candidatas
            for falta in dict.fromkeys(faltas_de(sql))
        ),
        key=lambda h: (h.archivo, h.linea, h.falta),
    )


def hallazgos_del_codigo() -> list[Hallazgo]:
    return [
        hallazgo
        for archivo in sorted(RAIZ_DEL_CODIGO.rglob("*.py"))
        for hallazgo in hallazgos_en(archivo.read_text(encoding="utf-8"), archivo.relative_to(RAIZ_DEL_CODIGO).as_posix())
    ]


# --- Excepciones: cada sentencia (archivo, función, texto) que toca una tabla raíz sin cuenta, con su porqué ---
# La clave lleva el texto exacto: otra sentencia sin filtro en la misma función no queda tapada.

MIGRACIONES = "aulento/db/migrations.py"

EXCEPCIONES: dict[tuple[str, str, str], str] = {
    (
        # La ruta se arma por partes: el repo público no puede nombrar el paquete de la nube
        "aulento" + "_cloud/prueba/servicio.py",
        "borrar_cuenta",
        f"DELETE FROM {ABRE}tabla{CIERRA} WHERE {ABRE}columna{CIERRA} = ?;",
    ): (
        "Borrar una cuenta (062 R2, antes la purga de pruebas de la 052): borra todas las filas de UNA cuenta. La "
        "tabla y la columna salen de `PRAGMA foreign_key_list` y de las columnas `user_id`/`usuario_id`, y el valor es "
        "siempre el id de esa cuenta: el filtro por dueño es la propia columna, que el analizador no puede ver."
    ),
    (
        MIGRACIONES,
        "_reconstruir_con_dueno",
        f"INSERT INTO {ABRE}tabla{CIERRA}_nueva ({ABRE}columnas{CIERRA}) SELECT {ABRE}columnas{CIERRA} FROM {ABRE}tabla{CIERRA};",
    ): (
        "Migración 3 (R1): copia todas las filas de `plataformas`, `rutas_aprendizaje` y `fsrs_items` a la tabla "
        "reconstruida con `user_id`. Corre una vez, antes de que nadie lea, y tiene que llevarse las filas de todos."
    ),
    (
        MIGRACIONES,
        "_migracion_datos_por_usuario",
        f"UPDATE {ABRE}tabla{CIERRA} SET user_id = ? WHERE user_id IS NULL;",
    ): (
        "Migración 3 (R2): si al migrar ya hay cuentas, las filas sin dueño de las ocho tablas raíz pasan al "
        "administrador activo más antiguo. Solo alcanza filas sin dueño: no toca las de ninguna cuenta."
    ),
    (
        MIGRACIONES,
        "_migracion_libros_autor_y_avances",
        "UPDATE libros_lectura SET pagina_actual = total_paginas WHERE total_paginas IS NOT NULL AND pagina_actual > total_paginas;",
    ): (
        "Migración 12 (decisión 3): repara filas históricas de libros_lectura con pagina_actual > total_paginas "
        "ajustándolas al total de páginas antes de que se use el esquema. Es una corrección global de esquema de una sola vez."
    ),
    (
        "aulento/auth/repositorio.py",
        "RepositorioAuth.reclamar_datos_sin_dueno",
        f"UPDATE {ABRE}tabla{CIERRA} SET user_id = ? WHERE user_id IS NULL;",
    ): (
        "Herencia de R2: la primera cuenta que se crea, o la que pasa a ser el único administrador activo, recibe "
        "las filas sin dueño de las tablas raíz. Solo alcanza filas sin dueño, y `auth/servicio.py` la llama "
        "únicamente dentro de la transacción de esas dos altas."
    ),
    (
        "aulento/auth/repositorio.py",
        "RepositorioAuth.reclamar_datos_sin_dueno",
        "UPDATE mcp_audit_logs SET user_id = ? WHERE user_id IS NULL AND tool_name <> ?;",
    ): (
        "La misma herencia de R2 sobre la auditoría MCP, que va aparte para dejar afuera los rechazos de "
        "autenticación (R10): esas filas no las originó ninguna cuenta y quedan sin dueño para siempre."
    ),
    (
        "aulento/cli/app.py",
        "cmd_db_status",
        f"SELECT count(*) FROM {ABRE}tabla{CIERRA};",
    ): (
        "`db status` cuenta las filas de `TABLAS_DEL_ESTADO` de todas las cuentas juntas: es el total del sistema "
        "para quien administra la instalación desde la terminal. Muestra cantidades, nunca el contenido de una fila."
    ),
}


# --- Los tests ---


def test_r6_ninguna_sentencia_toca_una_tabla_raiz_sin_la_cuenta():
    sin_excepcion = [h for h in hallazgos_del_codigo() if h.sentencia not in EXCEPCIONES]

    assert sin_excepcion == [], "SQL sobre una tabla raíz sin `user_id`:\n  " + "\n  ".join(map(str, sin_excepcion))


def test_r6_cada_excepcion_sigue_haciendo_falta_y_dice_por_que():
    """Una excepción que ya no tapa ninguna sentencia se borra: si queda, taparía la próxima que aparezca ahí."""
    sentencias = {h.sentencia for h in hallazgos_del_codigo()}
    # La de la nube vale donde está su código: el repo público del core no lo trae (051, R8)
    presentes = {excepcion for excepcion in EXCEPCIONES if (RAIZ_DEL_CODIGO / excepcion[0]).is_file()}

    assert presentes - sentencias == set(), "excepciones que ya no corresponden a ninguna sentencia"
    assert all(len(motivo.strip()) > 80 for motivo in EXCEPCIONES.values())
    assert len(set(EXCEPCIONES.values())) == len(EXCEPCIONES), "cada excepción lleva su propio motivo"


def test_las_tablas_de_secretos_y_ajustes_se_tocan_solo_con_la_cuenta_y_sin_excepciones():
    """034: todo el SQL sobre `secretos_usuario` y `ajustes_usuario` vive en un módulo y pasa el recorrido sin excepción."""
    assert set(TABLAS_POR_CUENTA) == {"secretos_usuario", "ajustes_usuario"} <= set(TABLAS_VIGILADAS)

    nombra = re.compile(rf"\b(?:FROM|JOIN|INTO|UPDATE)\s+({'|'.join(TABLAS_POR_CUENTA)})\b", re.IGNORECASE)
    donde_se_tocan: dict[str, set[str]] = {}
    for archivo in sorted(RAIZ_DEL_CODIGO.rglob("*.py")):
        for tabla in nombra.findall(archivo.read_text(encoding="utf-8")):
            donde_se_tocan.setdefault(archivo.relative_to(RAIZ_DEL_CODIGO).as_posix(), set()).add(tabla.lower())

    # Ningún otro módulo arma SQL sobre los almacenes: pasan todos por `AlmacenDeSecretos` y `AjustesDeCuenta`.
    # Excepción controlada: la nube en `cuentas/demo.py` borra los ajustes de la demo al resembrar (066 R4),
    # filtrando exclusivamente por el `user_id` de esa cuenta.
    esperado: dict[str, set[str]] = {"aulento/core/secretos.py": set(TABLAS_POR_CUENTA)}
    ruta_demo = "aulento" + "_cloud/cuentas/demo.py"
    if (RAIZ_DEL_CODIGO / ruta_demo).is_file():
        esperado[ruta_demo] = {"ajustes_usuario"}
        codigo_demo = (RAIZ_DEL_CODIGO / ruta_demo).read_text(encoding="utf-8")
        assert "DELETE FROM ajustes_usuario WHERE user_id = ?" in codigo_demo

    assert donde_se_tocan == esperado
    assert [h for h in hallazgos_del_codigo() if h.archivo == "aulento/core/secretos.py"] == []
    if (RAIZ_DEL_CODIGO / ruta_demo).is_file():
        assert [h for h in hallazgos_del_codigo() if h.archivo == ruta_demo] == []
    # Y ninguna excepción las alcanza: ni por nombre ni desde el módulo que las lee
    assert [clave for clave in EXCEPCIONES if clave[0].endswith("core/secretos.py")] == []
    assert [clave for clave in EXCEPCIONES if any(tabla in clave[2] for tabla in TABLAS_POR_CUENTA)] == []
    # Las excepciones que ponen la tabla por una variable recorren listas que no las incluyen
    from aulento.auth.repositorio import TABLAS_CON_DUENO
    from aulento.cli.app import TABLAS_DEL_ESTADO

    assert not set(TABLAS_POR_CUENTA) & (set(TABLAS_CON_DUENO) | {tabla for _, tabla in TABLAS_DEL_ESTADO})


def test_el_recorrido_encuentra_el_sql_del_codigo():
    """Si el recorrido dejara de reconocer el SQL, los dos tests de arriba pasarían sin mirar nada."""
    con_tabla_raiz = set()
    for archivo in RAIZ_DEL_CODIGO.rglob("*.py"):
        recorrido = _Recorrido()
        recorrido.visit(ast.parse(archivo.read_text(encoding="utf-8")))
        textos = [_texto(nodo, ambito) or "" for ambito, nodo in recorrido.sueltas]
        textos += [
            " ".join(_texto(valor, ambito, frozenset({nombre})) or "" for valor in unidad)
            for ambito in recorrido.ambitos
            for nombre, unidades in ambito.variables.items()
            for unidad in unidades
        ]
        if any(MENCION.search(texto) and COMPARACION.search(texto) for texto in textos):
            con_tabla_raiz.add(archivo.relative_to(RAIZ_DEL_CODIGO).as_posix())

    assert {
        "aulento/db/repository.py",
        "aulento/db/fsrs_repository.py",
        "aulento/db/focus_repository.py",
        "aulento/db/roadmap_repository.py",
        "aulento/db/vector_repository.py",
        "aulento/core/activity_tracker.py",
        "aulento/core/secretos.py",
        "aulento/fsrs/stats.py",
    } <= con_tabla_raiz


CON_CUENTA = {
    "lectura": 'conn.execute("SELECT * FROM libros_lectura WHERE id = ? AND user_id = ?", (i, u))',
    "alta": 'conn.execute("INSERT INTO fsrs_items (user_id, categoria) VALUES (?, ?)", (u, c))',
    "alta o actualización": (
        'conn.execute("INSERT INTO plataformas (user_id, nombre) VALUES (?, ?) '
        'ON CONFLICT(user_id, nombre) DO UPDATE SET url_acceso = excluded.url_acceso", (u, n))'
    ),
    "actualización": 'conn.execute("UPDATE bloques_horarios SET descripcion = ? WHERE id = ? AND user_id = ?", p)',
    "borrado": 'conn.execute("DELETE FROM sesiones_estudio WHERE user_id = ? AND id = ?", p)',
    "dependiente resuelta con JOIN": (
        'conn.execute("SELECT c.* FROM cursos_externos c JOIN plataformas p ON p.id = c.plataforma_id '
        'WHERE p.user_id = ? AND c.id = ?", p)'
    ),
    "dependiente resuelta con EXISTS": (
        'conn.execute("DELETE FROM roadmap_modules WHERE id = ? AND EXISTS '
        '(SELECT 1 FROM rutas_aprendizaje r WHERE r.id = roadmap_modules.roadmap_id AND r.user_id = ?)", p)'
    ),
    "subconsulta atada a la de afuera": (
        'conn.execute("SELECT r.id, (SELECT COUNT(*) FROM fsrs_items f WHERE f.user_id = r.user_id) '
        'FROM rutas_aprendizaje r WHERE r.user_id = ?", p)'
    ),
    "UNION con el filtro en cada rama": (
        'conn.execute("SELECT fecha FROM sesiones_estudio WHERE user_id = ? '
        'UNION ALL SELECT fecha_actualizacion FROM libros_lectura WHERE user_id = ?", p)'
    ),
    "condiciones agregadas con +=": (
        "def listar(conn, u, estado):\n"
        '    query = "SELECT * FROM libros_lectura WHERE user_id = ?"\n'
        "    if estado:\n"
        '        query += " AND estado = ?"\n'
        "    return conn.execute(query, (u, estado))"
    ),
    "filtro que llega por +=": (
        "def listar(conn, u):\n"
        '    query = "SELECT * FROM libros_lectura"\n'
        '    query += " WHERE user_id = ?"\n'
        "    return conn.execute(query, (u,))"
    ),
    "f-string con un fragmento del módulo": (
        'ORIGEN = "fsrs_review_logs l JOIN fsrs_items i ON i.id = l.item_id"\n'
        "def contar(conn, u):\n"
        '    return conn.execute(f"SELECT COUNT(*) FROM {ORIGEN} WHERE i.user_id = ?", (u,))'
    ),
    "lista de condiciones unida": (
        "def listar(conn, u):\n"
        '    condiciones = ["user_id = ?"]\n'
        '    condiciones.append("estado = ?")\n'
        '    return conn.execute("SELECT * FROM fsrs_items WHERE " + " AND ".join(condiciones), (u,))'
    ),
    "fragmento de vectores con su dueño": (
        'cur.execute("INSERT INTO knowledge_embeddings (user_id, source_type) VALUES (%s, %s)", p)\n'
        'cur.execute("SELECT COUNT(*) FROM knowledge_embeddings WHERE user_id = %s AND source_type = %s;", p)'
    ),
    "secreto y ajuste de la cuenta": (
        'conn.execute("SELECT valor_cifrado FROM secretos_usuario WHERE user_id = ? AND nombre = ?", p)\n'
        'conn.execute("INSERT INTO ajustes_usuario (user_id, clave, valor) VALUES (?, ?, ?) "\n'
        '             "ON CONFLICT(user_id, clave) DO UPDATE SET valor = excluded.valor", p)'
    ),
    "tabla dinámica con filtro": 'conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE user_id = ?", (u,))',
    "tabla que no es raíz": 'conn.execute("SELECT * FROM usuarios WHERE id = ?", (i,))',
    "tabla con nombre parecido": 'conn.execute("SELECT * FROM plataformas_nueva")',
    "DDL": 'conn.execute("CREATE INDEX IF NOT EXISTS idx_fsrs_user ON fsrs_items(user_id)")',
    "prosa": 'print("Importá tus plataformas desde el menú. Update plataformas pendiente.".lower())',
    "fragmento que se mira donde se usa": 'ORIGEN = "fsrs_review_logs l JOIN fsrs_items i ON i.id = l.item_id"',
    "docstring": 'def f():\n    """SELECT * FROM plataformas: así NO se escribe."""',
}

SIN_CUENTA = {
    "lectura": 'conn.execute("SELECT * FROM libros_lectura WHERE id = ?", (i,))',
    "lectura en minúsculas": 'conn.execute("select * from libros_lectura where id = ?", (i,))',
    "total": 'conn.execute("SELECT COUNT(*) FROM fsrs_items")',
    "alta": 'conn.execute("INSERT INTO fsrs_items (categoria, item_pregunta) VALUES (?, ?)", p)',
    "alta sin lista de columnas": 'conn.execute("INSERT INTO plataformas VALUES (?, ?, ?)", p)',
    "actualización": 'conn.execute("UPDATE bloques_horarios SET descripcion = ? WHERE id = ?", p)',
    "actualización que solo escribe el dueño": 'conn.execute("UPDATE plataformas SET user_id = ? WHERE id = ?", p)',
    "actualización sin WHERE": 'conn.execute("UPDATE rutas_aprendizaje SET estado = ?", p)',
    "borrado": 'conn.execute("DELETE FROM sesiones_estudio WHERE id = ?", p)',
    "dueño nulo no es una cuenta": 'conn.execute("SELECT * FROM api_usage_logs WHERE user_id IS NULL")',
    "JOIN sin filtro": (
        'conn.execute("SELECT c.* FROM cursos_externos c JOIN plataformas p ON p.id = c.plataforma_id WHERE c.id = ?", p)'
    ),
    "subconsulta sin filtro dentro de una consulta filtrada": (
        'conn.execute("SELECT r.id, (SELECT COUNT(*) FROM fsrs_items) FROM rutas_aprendizaje r WHERE r.user_id = ?", p)'
    ),
    "UNION con una rama sin filtro": (
        'conn.execute("SELECT fecha FROM sesiones_estudio WHERE user_id = ? '
        'UNION ALL SELECT fecha_actualizacion FROM libros_lectura", p)'
    ),
    "secreto por nombre, de cualquier cuenta": (
        'conn.execute("SELECT valor_cifrado FROM secretos_usuario WHERE nombre = ?", p)'
    ),
    "ajuste por clave, de cualquier cuenta": 'conn.execute("DELETE FROM ajustes_usuario WHERE clave = ?", p)',
    "fragmentos de vectores de todos": 'cur.execute("DELETE FROM knowledge_embeddings WHERE source_id = %s;", p)',
    "f-string": 'conn.execute(f"SELECT {columnas} FROM mcp_audit_logs ORDER BY id DESC LIMIT {limite}")',
    "concatenación": 'conn.execute("SELECT * FROM " + "rutas_aprendizaje" + " WHERE id = ?", p)',
    "concatenación con una variable": (
        'def leer(conn, i):\n    sql = "SELECT * FROM plataformas"\n    return conn.execute(sql + " WHERE id = ?", (i,))'
    ),
    "condiciones agregadas con += sin el filtro": (
        "def listar(conn, estado):\n"
        '    query = "SELECT * FROM libros_lectura WHERE 1=1"\n'
        "    if estado:\n"
        '        query += " AND estado = ?"\n'
        "    return conn.execute(query, (estado,))"
    ),
    "lista de condiciones sin el filtro": (
        "def listar(conn):\n"
        '    condiciones = ["estado = ?"]\n'
        '    return conn.execute("SELECT * FROM fsrs_items WHERE " + " AND ".join(condiciones))'
    ),
    "tabla dinámica": 'conn.execute(f"SELECT COUNT(*) FROM {tabla};")',
    "tabla dinámica en una actualización": 'conn.execute(f"UPDATE {tabla} SET user_id = ? WHERE user_id IS NULL;", p)',
    "operador %": 'conn.execute("SELECT COUNT(*) FROM %s" % tabla)',
    "sentencia dentro de una comprensión": (
        'def totales(conn):\n    filas = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone() for t in TABLAS]\n    return filas'
    ),
    "str.format": 'conn.execute("DELETE FROM {} WHERE id = ?".format("fsrs_items"), p)',
    "segunda sentencia de un script": (
        'conn.executescript("DELETE FROM fsrs_items WHERE user_id = 1; DELETE FROM libros_lectura;")'
    ),
    "sentencia guardada en una constante": 'CONSULTA = """\n    SELECT *\n    FROM plataformas\n    ORDER BY nombre\n"""',
    "sentencia devuelta por una función": 'def consulta():\n    return "SELECT id FROM bloques_horarios"',
}


@pytest.mark.parametrize("codigo", CON_CUENTA.values(), ids=CON_CUENTA.keys())
def test_el_analizador_deja_pasar_el_sql_atado_a_la_cuenta(codigo):
    assert hallazgos_en(codigo) == []


@pytest.mark.parametrize("codigo", SIN_CUENTA.values(), ids=SIN_CUENTA.keys())
def test_el_analizador_marca_el_sql_sin_cuenta(codigo):
    assert hallazgos_en(codigo) != []


def test_el_analizador_dice_donde_esta_la_sentencia():
    codigo = "class Repo:\n    def listar(self):\n        return self.conn.execute('SELECT * FROM plataformas')\n"

    (hallazgo,) = hallazgos_en(codigo, "aulento/db/ejemplo.py")

    assert hallazgo.lugar == ("aulento/db/ejemplo.py", "Repo.listar")
    assert (hallazgo.linea, hallazgo.falta) == (3, "plataformas: el FROM no compara `user_id` en su consulta")


@pytest.mark.parametrize("tabla", TABLAS_VIGILADAS)
def test_el_recorrido_muerde_una_sentencia_sin_filtro_agregada_a_un_repositorio_real(tabla):
    """Lo mismo que agregar a mano una sentencia sin filtro a `db/repository.py`: el recorrido la tiene que marcar."""
    archivo = RAIZ_DEL_CODIGO / "aulento" / "db" / "repository.py"
    original = archivo.read_text(encoding="utf-8")
    colada = f'\n\ndef _colada(conn):\n    return conn.execute("SELECT * FROM {tabla} ORDER BY id;").fetchall()\n'

    antes = hallazgos_en(original, "aulento/db/repository.py")
    despues = hallazgos_en(original + colada, "aulento/db/repository.py")

    (colado,) = [h for h in despues if h not in antes]
    assert colado.lugar == ("aulento/db/repository.py", "_colada")
    assert colado.sentencia not in EXCEPCIONES
