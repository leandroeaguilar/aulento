"""Genera src/aulento/web/static/css/paleta.css: la paleta de Tailwind como variables CSS.

Cada color de la paleta por defecto de Tailwind v3.4.17 queda como --au-<familia>-<tono> con un
triplete RGB ("15 23 42"). tailwind.config.js apunta las utilidades a esas variables
(rgb(var(--au-slate-900) / <alpha-value>)), así que bg-slate-900, text-sky-400/50, etc. siguen
funcionando igual, pero ahora se pueden cambiar con el tema.

- Tema oscuro (el de siempre): los valores originales de Tailwind. Cero cambio visual.
- Tema claro: cada escala se invierte (50 <-> 950, 100 <-> 900 ...). Los grises (slate, gray)
  tienen un mapa propio para que el fondo de la página sea gris claro y las tarjetas blancas.
- "sistema": sigue a prefers-color-scheme.

Uso:
    python scripts/generar_paleta.py              # reescribe paleta.css
    python scripts/generar_paleta.py --comprobar  # falla si paleta.css no está al día
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "src" / "aulento" / "web" / "static" / "css" / "paleta.css"

TONOS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)

# Paleta por defecto de Tailwind v3.4.17 (tailwindcss/lib/public/colors.js, licencia MIT).
PALETA: dict[str, dict[int, str]] = {
    "slate": {50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1", 400: "#94a3b8", 500: "#64748b", 600: "#475569", 700: "#334155", 800: "#1e293b", 900: "#0f172a", 950: "#020617"},
    "gray": {50: "#f9fafb", 100: "#f3f4f6", 200: "#e5e7eb", 300: "#d1d5db", 400: "#9ca3af", 500: "#6b7280", 600: "#4b5563", 700: "#374151", 800: "#1f2937", 900: "#111827", 950: "#030712"},
    "red": {50: "#fef2f2", 100: "#fee2e2", 200: "#fecaca", 300: "#fca5a5", 400: "#f87171", 500: "#ef4444", 600: "#dc2626", 700: "#b91c1c", 800: "#991b1b", 900: "#7f1d1d", 950: "#450a0a"},
    "orange": {50: "#fff7ed", 100: "#ffedd5", 200: "#fed7aa", 300: "#fdba74", 400: "#fb923c", 500: "#f97316", 600: "#ea580c", 700: "#c2410c", 800: "#9a3412", 900: "#7c2d12", 950: "#431407"},
    "amber": {50: "#fffbeb", 100: "#fef3c7", 200: "#fde68a", 300: "#fcd34d", 400: "#fbbf24", 500: "#f59e0b", 600: "#d97706", 700: "#b45309", 800: "#92400e", 900: "#78350f", 950: "#451a03"},
    "yellow": {50: "#fefce8", 100: "#fef9c3", 200: "#fef08a", 300: "#fde047", 400: "#facc15", 500: "#eab308", 600: "#ca8a04", 700: "#a16207", 800: "#854d0e", 900: "#713f12", 950: "#422006"},
    "lime": {50: "#f7fee7", 100: "#ecfccb", 200: "#d9f99d", 300: "#bef264", 400: "#a3e635", 500: "#84cc16", 600: "#65a30d", 700: "#4d7c0f", 800: "#3f6212", 900: "#365314", 950: "#1a2e05"},
    "green": {50: "#f0fdf4", 100: "#dcfce7", 200: "#bbf7d0", 300: "#86efac", 400: "#4ade80", 500: "#22c55e", 600: "#16a34a", 700: "#15803d", 800: "#166534", 900: "#14532d", 950: "#052e16"},
    "emerald": {50: "#ecfdf5", 100: "#d1fae5", 200: "#a7f3d0", 300: "#6ee7b7", 400: "#34d399", 500: "#10b981", 600: "#059669", 700: "#047857", 800: "#065f46", 900: "#064e3b", 950: "#022c22"},
    "teal": {50: "#f0fdfa", 100: "#ccfbf1", 200: "#99f6e4", 300: "#5eead4", 400: "#2dd4bf", 500: "#14b8a6", 600: "#0d9488", 700: "#0f766e", 800: "#115e59", 900: "#134e4a", 950: "#042f2e"},
    "cyan": {50: "#ecfeff", 100: "#cffafe", 200: "#a5f3fc", 300: "#67e8f9", 400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2", 700: "#0e7490", 800: "#155e75", 900: "#164e63", 950: "#083344"},
    "sky": {50: "#f0f9ff", 100: "#e0f2fe", 200: "#bae6fd", 300: "#7dd3fc", 400: "#38bdf8", 500: "#0ea5e9", 600: "#0284c7", 700: "#0369a1", 800: "#075985", 900: "#0c4a6e", 950: "#082f49"},
    "blue": {50: "#eff6ff", 100: "#dbeafe", 200: "#bfdbfe", 300: "#93c5fd", 400: "#60a5fa", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8", 800: "#1e40af", 900: "#1e3a8a", 950: "#172554"},
    "indigo": {50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc", 400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca", 800: "#3730a3", 900: "#312e81", 950: "#1e1b4b"},
    "violet": {50: "#f5f3ff", 100: "#ede9fe", 200: "#ddd6fe", 300: "#c4b5fd", 400: "#a78bfa", 500: "#8b5cf6", 600: "#7c3aed", 700: "#6d28d9", 800: "#5b21b6", 900: "#4c1d95", 950: "#2e1065"},
    "purple": {50: "#faf5ff", 100: "#f3e8ff", 200: "#e9d5ff", 300: "#d8b4fe", 400: "#c084fc", 500: "#a855f7", 600: "#9333ea", 700: "#7e22ce", 800: "#6b21a8", 900: "#581c87", 950: "#3b0764"},
    "fuchsia": {50: "#fdf4ff", 100: "#fae8ff", 200: "#f5d0fe", 300: "#f0abfc", 400: "#e879f9", 500: "#d946ef", 600: "#c026d3", 700: "#a21caf", 800: "#86198f", 900: "#701a75", 950: "#4a044e"},
    "pink": {50: "#fdf2f8", 100: "#fce7f3", 200: "#fbcfe8", 300: "#f9a8d4", 400: "#f472b6", 500: "#ec4899", 600: "#db2777", 700: "#be185d", 800: "#9d174d", 900: "#831843", 950: "#500724"},
    "rose": {50: "#fff1f2", 100: "#ffe4e6", 200: "#fecdd3", 300: "#fda4af", 400: "#fb7185", 500: "#f43f5e", 600: "#e11d48", 700: "#be123c", 800: "#9f1239", 900: "#881337", 950: "#4c0519"},
}

BLANCO = "#ffffff"
NEGRO = "#000000"

# Tema claro para los grises: el fondo de página (950) pasa a gris claro y las tarjetas (900) a blanco.
CLARO_GRISES: dict[int, int | str] = {
    950: 100, 900: "blanco", 800: 200, 700: 300, 600: 400, 500: 500,
    400: 600, 300: 700, 200: 800, 100: 900, 50: 950,
}
FAMILIAS_GRISES = ("slate", "gray")
# En el tema claro, el "blanco" de text-white (títulos sobre fondo oscuro) pasa a ser texto oscuro.
CLARO_BLANCO = ("slate", 900)


def triplete(hexa: str) -> str:
    hexa = hexa.lstrip("#")
    return " ".join(str(int(hexa[i : i + 2], 16)) for i in (0, 2, 4))


def valores_oscuros() -> dict[str, str]:
    valores = {"blanco": triplete(BLANCO), "negro": triplete(NEGRO)}
    for familia, tonos in PALETA.items():
        for tono in TONOS:
            valores[f"{familia}-{tono}"] = triplete(tonos[tono])
    return valores


def valores_claros() -> dict[str, str]:
    familia_b, tono_b = CLARO_BLANCO
    valores = {"blanco": triplete(PALETA[familia_b][tono_b]), "negro": triplete(NEGRO)}
    for familia, tonos in PALETA.items():
        for tono in TONOS:
            if familia in FAMILIAS_GRISES:
                destino = CLARO_GRISES[tono]
                hexa = BLANCO if destino == "blanco" else tonos[destino]
            else:
                hexa = tonos[1000 - tono]  # 50 <-> 950, 100 <-> 900 ... 500 queda igual
            valores[f"{familia}-{tono}"] = triplete(hexa)
    return valores


def _bloque(selector: str, esquema: str, valores: dict[str, str], sangria: str = "") -> list[str]:
    lineas = [f"{sangria}{selector} {{", f"{sangria}  color-scheme: {esquema};"]
    lineas += [f"{sangria}  --au-{nombre}: {valor};" for nombre, valor in valores.items()]
    lineas.append(f"{sangria}}}")
    return lineas


def generar() -> str:
    claros = valores_claros()
    lineas = [
        "/* Generado por scripts/generar_paleta.py: no editar a mano. */",
        "/* Paleta de Tailwind v3.4.17 como tripletes RGB. Uso: rgb(var(--au-slate-900)) o rgb(var(--au-slate-900) / 0.5). */",
        "/* Tema: <html data-tema=\"oscuro|claro|sistema\">. Sin atributo = oscuro. */",
        "",
        *_bloque(":root", "dark", valores_oscuros()),
        "",
        *_bloque(':root[data-tema="claro"]', "light", claros),
        "",
        "@media (prefers-color-scheme: light) {",
        *_bloque(':root[data-tema="sistema"]', "light", claros, sangria="  "),
        "}",
        "",
    ]
    return "\n".join(lineas)


def main(argv: list[str]) -> int:
    contenido = generar()
    if "--comprobar" in argv:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != contenido:
            print(f"{SALIDA.relative_to(RAIZ)} no está al día: correr python scripts/generar_paleta.py")
            return 1
        return 0
    SALIDA.write_text(contenido, encoding="utf-8", newline="\n")
    print(f"escrito {SALIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
