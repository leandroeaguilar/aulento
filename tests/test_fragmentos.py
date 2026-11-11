"""Pruebas del fragmentador por estructura Markdown (R1, R3)."""

from aulento.core.fragmentos import fragmentar


def test_fragmentar_texto_vacio():
    assert fragmentar("") == []
    assert fragmentar("   \n\n  ") == []


def test_fragmentar_respeta_titulos_y_ruta_de_encabezados():
    md = """# Introducción
Este es el inicio del tema.

## Fundamentos
Detalle de fundamentos teóricos.

### Concepto Específico
Explicación detallada del concepto.

## Conclusión
Resumen final.
"""
    fragmentos = fragmentar(md, titulo="Mi Nota de Estudio")
    assert len(fragmentos) == 4

    assert fragmentos[0].encabezado == "Mi Nota de Estudio › Introducción"
    assert "Este es el inicio" in fragmentos[0].texto

    assert fragmentos[1].encabezado == "Mi Nota de Estudio › Introducción › Fundamentos"
    assert "Detalle de fundamentos" in fragmentos[1].texto

    assert fragmentos[2].encabezado == "Mi Nota de Estudio › Introducción › Fundamentos › Concepto Específico"
    assert "Explicación detallada" in fragmentos[2].texto

    assert fragmentos[3].encabezado == "Mi Nota de Estudio › Introducción › Conclusión"
    assert "Resumen final" in fragmentos[3].texto


def test_fragmentar_no_corta_palabras():
    texto_largo = "palabra " * 300  # ~2400 caracteres
    frags = fragmentar(texto_largo, titulo="Nota", tamano=500, solapamiento=50)

    for f in frags:
        # Cada fragmento debe comenzar y terminar con palabras completas
        assert not f.texto.startswith(" ")
        assert not f.texto.endswith(" ")
        partes = f.texto.split()
        for p in partes:
            assert p == "palabra"


def test_fragmentar_codigo_no_se_parte_a_mitad_de_linea():
    lineas_codigo = [f"    linea_de_codigo_{i} = procesar_datos_paso_{i}()" for i in range(50)]
    md_codigo = "# Módulo de Código\n\n```python\n" + "\n".join(lineas_codigo) + "\n```\n"

    frags = fragmentar(md_codigo, titulo="Script", tamano=400, solapamiento=50)
    for f in frags:
        for linea in f.texto.splitlines():
            linea_s = linea.strip()
            if linea_s and not linea_s.startswith("```") and not linea_s.startswith("#"):
                assert linea_s.startswith("linea_de_codigo_")
                assert linea_s.endswith("()")


def test_fragmentar_solapamiento_menor_al_veinte_por_ciento():
    tamano = 1000
    # Pedir un solapamiento excesivo (> 20%) debe ser acotado estrictamente a < 20%
    md = ("Este es un párrafo de prueba con suficiente longitud. " * 40 + "\n\n") * 5
    frags = fragmentar(md, titulo="Prueba", tamano=tamano, solapamiento=500)

    # El solapamiento entre fragmentos consecutivos de la misma sección debe ser < 200 caracteres
    for i in range(len(frags) - 1):
        f1, f2 = frags[i], frags[i + 1]
        if f1.encabezado == f2.encabezado:
            # Calcular solapamiento en caracteres entre fin de f1 e inicio de f2
            solapamiento_medido = max(0, f1.fin - f2.inicio)
            assert solapamiento_medido < (tamano * 0.20), f"Solapamiento {solapamiento_medido} >= 20%"


def test_fragmentar_ignora_titulos_dentro_de_bloques_de_codigo():
    md = """# Título Real

```python
# Esto es un comentario en Python, no un encabezado
def funcion():
    pass
```

Texto posterior.
"""
    frags = fragmentar(md, titulo="Nota")
    assert len(frags) == 1
    assert frags[0].encabezado == "Nota › Título Real"
    assert "comentario en Python" in frags[0].texto


def test_fragmentar_offsets_fieles_al_documento_original():
    """Punto 3: para todo fragmento, texto_original[f.inicio:f.fin] contiene el texto del fragmento."""
    oraciones = [
        f"Esta es la oracion numero {i} con detalles explicativos sobre el tema en cuestion."
        for i in range(25)
    ]
    parrafo_largo = " ".join(oraciones)
    md = f"# Seccion Principal\n\n{parrafo_largo}\n"

    frags = fragmentar(md, titulo="Nota", tamano=300, solapamiento=50)
    assert len(frags) > 1
    for f in frags:
        sub_original = md[f.inicio:f.fin]
        assert sub_original.strip().startswith(f.texto.split()[0]), f"Inicio desfasado: '{sub_original[:30]}' vs '{f.texto[:30]}'"
        assert sub_original.strip().endswith(f.texto.split()[-1]), f"Fin desfasado: '{sub_original[-30:]}' vs '{f.texto[-30:]}'"


def test_fragmentar_bloque_codigo_completo_no_traba_en_codigo():
    """Punto 4: bloque de código completo y después párrafos largos de texto -> los de texto respetan el tamaño."""
    codigo = "```python\ndef foo():\n    return 42\n```\n\n"
    texto_largo = "Este es un parrafo largo de texto normal que debe ser dividido si supera el tamano. " * 15
    md = f"# Titulo\n\n{codigo}{texto_largo}\n"

    frags = fragmentar(md, titulo="Nota", tamano=400, solapamiento=50)
    # Si en_codigo quedó trabado en True, el texto_largo no se divide por oraciones y el fragmento supera 400
    for f in frags:
        assert len(f.texto) <= 500

