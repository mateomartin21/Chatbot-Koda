"""Genera app/interfaces/web/relieve.svg — el fondo de curvas de nivel.

Una foto de banco de un corredor es lo que pone cualquiera y se nota. Las curvas
de nivel son el lenguaje del sujeto: es como se dibuja una ruta con desnivel en
cualquier mapa, en un GPS y en el perfil de una carrera. Ademas pesa 20 KB, no
tiene licencia que respetar y se tine con el color de la app.

Las curvas salen de sumar tres senos con frecuencias no multiplicadas entre si, y
la semilla es fija: el fondo es el mismo en cada ejecucion.

    python scripts/generar_relieve.py
"""

import math
from pathlib import Path

DESTINO = Path(__file__).resolve().parents[1] / "app" / "interfaces" / "web" / "relieve.svg"

ANCHO, ALTO = 1200, 900
CURVAS = 24
PUNTOS = 34  # muestras por curva; mas no se nota y engorda el archivo
SEMILLA = 7


def altura(x: float, indice: int) -> float:
    """Tres ondas de periodos no multiplos: no se repite el patron a simple vista."""
    fase = indice * 0.44 + SEMILLA
    return (
        math.sin(x * 2.7 + fase) * 46
        + math.sin(x * 1.13 - fase * 0.7) * 78
        + math.sin(x * 5.9 + fase * 1.9) * 14
        # Las curvas se aprietan a la derecha y se abren a la izquierda, como en un
        # mapa real donde la pendiente no es uniforme.
        + math.sin(x * 0.6) * 30 * (indice / CURVAS)
    )


def curva(indice: int) -> str:
    base = -120 + indice * ((ALTO + 260) / CURVAS)
    puntos = []
    for j in range(PUNTOS + 1):
        t = j / PUNTOS
        x = t * ANCHO
        y = base + altura(t * math.pi * 2, indice)
        puntos.append((x, y))

    # Curva suave por Catmull-Rom convertido a Bezier: sin esto se ven los vertices.
    partes = [f"M{puntos[0][0]:.0f} {puntos[0][1]:.0f}"]
    for j in range(len(puntos) - 1):
        x0, y0 = puntos[max(j - 1, 0)]
        x1, y1 = puntos[j]
        x2, y2 = puntos[j + 1]
        x3, y3 = puntos[min(j + 2, len(puntos) - 1)]
        c1x, c1y = x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6
        c2x, c2y = x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6
        partes.append(f"C{c1x:.0f} {c1y:.0f} {c2x:.0f} {c2y:.0f} {x2:.0f} {y2:.0f}")
    return "".join(partes)


def main() -> None:
    lineas = []
    for i in range(CURVAS):
        # Una de cada cinco es una curva maestra: mas gruesa, como en los mapas de
        # verdad, donde cada quinta curva lleva la cota escrita.
        maestra = i % 5 == 0
        lineas.append(
            f'  <path d="{curva(i)}" stroke-width="{1.6 if maestra else 0.9}" '
            f'opacity="{0.9 if maestra else 0.55}"/>'
        )

    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!--\n"
        f"  Fondo de curvas de nivel de Koda. GENERADO — no editar a mano.\n"
        f"  Se regenera con: python scripts/generar_relieve.py\n"
        f"-->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ANCHO} {ALTO}" '
        f'fill="none" stroke="#000" stroke-linecap="round">\n' + "\n".join(lineas) + "\n</svg>\n"
    )
    DESTINO.write_text(svg, encoding="utf-8")
    print(f"{DESTINO.name}: {CURVAS} curvas, {len(svg) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
