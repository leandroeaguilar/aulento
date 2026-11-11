"""Fragmentador de notas y materiales respetando su estructura Markdown (R1, R3).

Divide el contenido respetando títulos (#..######), párrafos en blanco y oraciones,
sin cortar palabras y preservando bloques de código sin partirlos a mitad de línea.
Cada fragmento lleva su encabezado de contexto jerárquico («Título › Sección › Subsección»).
"""

import re
from dataclasses import dataclass

MAX_SOLAPAMIENTO_PCT = 0.20
RE_ENCABEZADO = re.compile(r"^(#{1,6})\s+(.+)$")
RE_FIN_DE_ORACION = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Fragmento:
    """Fragmento de texto estructurado con su encabezado jerárquico e índices en el documento original."""

    texto: str
    encabezado: str
    inicio: int
    fin: int


def _armar_encabezado(titulo: str, niveles: dict[int, str]) -> str:
    """Compone la ruta jerárquica «Título › Sección › Subsección»."""
    partes = [titulo.strip()] if titulo and titulo.strip() else []
    for nivel in sorted(niveles.keys()):
        texto_nivel = niveles[nivel].strip()
        if texto_nivel:
            partes.append(texto_nivel)
    return " › ".join(partes)


def _dividir_parrafo_largo(parrafo: str, tamano: int, es_codigo: bool) -> list[str]:
    """Divide un párrafo que supera el tamaño en unidades más chicas (líneas o oraciones/palabras)."""
    if es_codigo:
        # En bloques de código cortamos únicamente por líneas completas
        lineas = parrafo.splitlines(keepends=True)
        return [linea for linea in lineas if linea]

    # En texto común, dividimos por oraciones
    oraciones = RE_FIN_DE_ORACION.split(parrafo)
    unidades: list[str] = []
    for oracion in oraciones:
        oracion_limpia = oracion.strip()
        if not oracion_limpia:
            continue
        if len(oracion_limpia) <= tamano:
            unidades.append(oracion_limpia)
        else:
            # Si una oración sigue siendo más larga que el tamaño, dividimos por palabras
            palabras = oracion_limpia.split(" ")
            unidades.extend(p for p in palabras if p)
    return unidades


def fragmentar(
    texto: str,
    titulo: str = "",
    tamano: int = 1200,
    solapamiento: int = 150,
) -> list[Fragmento]:
    """Parte notas y materiales respetando títulos, párrafos y oraciones sin cortar palabras.

    - tamano: tamaño máximo objetivo en caracteres de cada fragmento.
    - solapamiento: solapamiento máximo (debe ser menor al 20% del tamaño).
    """
    if not texto or not texto.strip():
        return []

    # Validar que el solapamiento sea menor al 20% del tamaño objetivo
    max_solapamiento = int(tamano * MAX_SOLAPAMIENTO_PCT)
    if solapamiento >= max_solapamiento:
        solapamiento = max(0, max_solapamiento - 1)

    # 1. Separar secciones por títulos Markdown (#..######) fuera de bloques de código
    lineas = texto.splitlines(keepends=True)
    secciones: list[dict] = []

    niveles_activos: dict[int, str] = {}
    en_bloque_codigo = False
    bloque_delimitador = ""

    sec_inicio = 0
    sec_lineas: list[str] = []
    sec_encabezado = _armar_encabezado(titulo, niveles_activos)
    offset_actual = 0

    for linea in lineas:
        longitud_linea = len(linea)
        linea_strip = linea.strip()

        # Detección de inicio/cierre de bloques de código (``` o ~~~)
        if linea_strip.startswith(("```", "~~~")):
            delimitador = linea_strip[:3]
            if not en_bloque_codigo:
                en_bloque_codigo = True
                bloque_delimitador = delimitador
            elif bloque_delimitador == delimitador:
                en_bloque_codigo = False
                bloque_delimitador = ""

        # Detección de encabezado si no estamos dentro de código
        if not en_bloque_codigo:
            match_encabezado = RE_ENCABEZADO.match(linea_strip)
            if match_encabezado:
                nivel = len(match_encabezado.group(1))
                texto_encabezado = match_encabezado.group(2).strip()

                # Cerrar sección previa si contenía texto
                texto_acumulado = "".join(sec_lineas)
                if texto_acumulado.strip():
                    secciones.append({
                        "texto": texto_acumulado,
                        "encabezado": sec_encabezado,
                        "inicio": sec_inicio,
                        "fin": offset_actual,
                    })

                # Actualizar niveles jerárquicos
                niveles_activos = {k: v for k, v in niveles_activos.items() if k < nivel}
                niveles_activos[nivel] = texto_encabezado
                sec_encabezado = _armar_encabezado(titulo, niveles_activos)
                sec_inicio = offset_actual
                sec_lineas = [linea]
                offset_actual += longitud_linea
                continue

        sec_lineas.append(linea)
        offset_actual += longitud_linea

    # Cerrar la última sección
    texto_acumulado = "".join(sec_lineas)
    if texto_acumulado.strip():
        secciones.append({
            "texto": texto_acumulado,
            "encabezado": sec_encabezado,
            "inicio": sec_inicio,
            "fin": offset_actual,
        })

    # 2. Fragmentar cada sección respetando párrafos, oraciones o líneas de código
    fragmentos: list[Fragmento] = []

    for sec in secciones:
        sec_texto = sec["texto"]
        sec_enc = sec["encabezado"]
        sec_base_offset = sec["inicio"]

        if len(sec_texto) <= tamano:
            # Si toda la sección cabe en un fragmento
            sec_limpio = sec_texto.strip()
            idx_en_sec = sec_texto.find(sec_limpio)
            f_ini = sec_base_offset + max(0, idx_en_sec)
            f_fin = f_ini + len(sec_limpio)
            fragmentos.append(Fragmento(
                texto=sec_limpio,
                encabezado=sec_enc,
                inicio=f_ini,
                fin=f_fin,
            ))
            continue

        # Dividir la sección en párrafos (separados por doble salto de línea)
        partes_crudo = re.split(r"(\n\s*\n)", sec_texto)
        unidades_con_offset: list[tuple[str, int, int]] = []
        parr_offset = 0

        en_bloque_codigo = False
        delimitador_codigo = ""
        for parte in partes_crudo:
            long_parte = len(parte)
            if not parte:
                continue

            era_en_codigo = en_bloque_codigo
            for linea_p in parte.splitlines(keepends=True):
                lp_strip = linea_p.strip()
                if lp_strip.startswith(("```", "~~~")):
                    delim = lp_strip[:3]
                    if not en_bloque_codigo:
                        en_bloque_codigo = True
                        delimitador_codigo = delim
                    elif delimitador_codigo == delim:
                        en_bloque_codigo = False
                        delimitador_codigo = ""

            es_codigo = era_en_codigo or ("```" in parte or "~~~" in parte)

            parte_strip = parte.strip()
            if not parte_strip:
                parr_offset += long_parte
                continue

            if len(parte) <= tamano:
                idx_en_parte = parte.find(parte_strip)
                u_ini = sec_base_offset + parr_offset + max(0, idx_en_parte)
                u_fin = u_ini + len(parte_strip)
                unidades_con_offset.append((parte_strip, u_ini, u_fin))
            else:
                sub_unidades = _dividir_parrafo_largo(parte, tamano, es_codigo)
                pos_busqueda = 0
                for sub in sub_unidades:
                    sub_strip = sub.strip()
                    if not sub_strip:
                        continue
                    idx_en_parte = parte.find(sub_strip, pos_busqueda)
                    if idx_en_parte == -1:
                        idx_en_parte = parte.find(sub_strip)
                    if idx_en_parte != -1:
                        u_ini = sec_base_offset + parr_offset + idx_en_parte
                        u_fin = u_ini + len(sub_strip)
                        unidades_con_offset.append((sub_strip, u_ini, u_fin))
                        pos_busqueda = idx_en_parte + len(sub_strip)

            parr_offset += long_parte

        if not unidades_con_offset:
            continue

        # Empacar unidades respetando tamano y solapamiento
        idx = 0
        n_unidades = len(unidades_con_offset)
        while idx < n_unidades:
            chunk_unidades: list[tuple[str, int, int]] = []
            longitud_chunk = 0
            inicio_chunk = unidades_con_offset[idx][1]
            ultimo_idx_agregado = idx

            for j in range(idx, n_unidades):
                u_texto, u_ini, u_fin = unidades_con_offset[j]
                extra = len(u_texto) + (2 if chunk_unidades else 0)
                if chunk_unidades and (longitud_chunk + extra > tamano):
                    break
                chunk_unidades.append((u_texto, u_ini, u_fin))
                longitud_chunk += extra
                ultimo_idx_agregado = j

            fin_chunk = chunk_unidades[-1][2]
            texto_chunk = texto[inicio_chunk:fin_chunk].strip()
            if not texto_chunk:
                texto_chunk = "\n\n".join(u[0] for u in chunk_unidades)

            fragmentos.append(Fragmento(
                texto=texto_chunk,
                encabezado=sec_enc,
                inicio=inicio_chunk,
                fin=fin_chunk,
            ))

            if ultimo_idx_agregado >= n_unidades - 1:
                break

            # Avanzar calculando el solapamiento hacia atrás
            if solapamiento > 0:
                caracteres_solapados = 0
                siguiente_idx = ultimo_idx_agregado + 1
                for k in range(ultimo_idx_agregado, idx, -1):
                    tam_k = len(unidades_con_offset[k][0])
                    if caracteres_solapados + tam_k <= solapamiento:
                        caracteres_solapados += tam_k
                        siguiente_idx = k
                    else:
                        break
                idx = siguiente_idx
            else:
                idx = ultimo_idx_agregado + 1

    return fragmentos
