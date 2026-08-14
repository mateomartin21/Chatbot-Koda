"""Regenera app/interfaces/web/iconos.svg a partir de los SVG originales de Phosphor.

Los iconos se vendorizan en el repo en vez de tirar de un CDN (ver ADR-015): una
peticion menos que puede fallar, funciona sin internet y la app no le cuenta a un
tercero quien la esta usando. Este script es lo que hace ese vendorizado
reproducible — para anadir un icono, se pone en ICONOS y se vuelve a ejecutar.

    python scripts/construir_sprite_iconos.py

Necesita red (solo aqui, nunca en tiempo de ejecucion ni en los tests).
"""

import urllib.request
from pathlib import Path

VERSION = "2.1.1"
FUENTE = f"https://unpkg.com/@phosphor-icons/core@{VERSION}/assets/regular"
DESTINO = Path(__file__).resolve().parents[1] / "app" / "interfaces" / "web" / "iconos.svg"

# nombre en Phosphor -> id que usa la app (en espanol, como el resto del dominio)
ICONOS = {
    "dog": "koda",
    "microphone": "micro",
    "stop": "parar",
    "arrow-up": "enviar",
    "calendar-check": "plan",
    "calendar-dots": "calendario",
    "user": "perfil",
    "x": "cerrar",
    "caret-down": "caret",
    "caret-right": "caret-derecha",
    "envelope-simple": "correo",
    "bell-simple": "campana",
    "flag-checkered": "meta",
    "lightning": "rayo",
    "moon-stars": "luna",
    "info": "info",
    "warning": "alerta",
    "path": "ruta",
    "timer": "crono",
    "pulse": "pulso",
    "sneaker-move": "zapatilla",
    "bed": "descanso",
}

CABECERA = f"""<?xml version="1.0" encoding="UTF-8"?>
<!--
  Iconografia de Koda. GENERADO — no editar a mano.
  Se regenera con: python scripts/construir_sprite_iconos.py

  Iconos de Phosphor (https://phosphoricons.com), peso Regular, v{VERSION}.
  Copyright (c) 2023 Phosphor Icons. Licencia MIT.
  Texto completo en app/interfaces/web/LICENCIAS-DE-TERCEROS.md.

  Se sirve como un unico sprite y se usa con <use href="/iconos.svg#i-nombre">: una
  sola peticion cacheada para todos, y heredan el color con currentColor.
-->
<svg xmlns="http://www.w3.org/2000/svg" style="display:none">
"""


def descargar(nombre: str) -> str:
    with urllib.request.urlopen(f"{FUENTE}/{nombre}.svg", timeout=30) as respuesta:
        return respuesta.read().decode("utf-8")


def cuerpo(svg: str) -> str:
    """Se queda con lo de dentro del <svg>: los <path> del icono, sin sus atributos."""
    return svg[svg.index(">", svg.index("<svg")) + 1 : svg.rindex("</svg>")].strip()


def main() -> None:
    partes = [CABECERA]
    for nombre, id_ in ICONOS.items():
        svg = descargar(nombre)
        if "<svg" not in svg:
            raise SystemExit(f"'{nombre}' no existe en Phosphor v{VERSION}")
        partes.append(
            f'  <symbol id="i-{id_}" viewBox="0 0 256 256" fill="currentColor">{cuerpo(svg)}</symbol>\n'
        )
    partes.append("</svg>\n")

    salida = "".join(partes)
    DESTINO.write_text(salida, encoding="utf-8")
    print(f"{DESTINO.name}: {len(ICONOS)} iconos, {len(salida) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
