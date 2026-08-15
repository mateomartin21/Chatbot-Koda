"""Recorta a Koda de la hoja de personaje y le quita el fondo.

La hoja original (`arte/koda-hoja.webp`) es una sola imagen con el lobo en varias
poses sobre un fondo gris. Meterla entera en la web seria mandar 1 MB para enseñar
una cara de 40 px, asi que cada pose se recorta, se le quita el fondo y se guarda a
la resolucion que de verdad se usa.

Esto vive en un script y no en un editor de imagenes porque **el recorte tiene que
poder repetirse**: si el arte se reemplaza, se corre esto y salen los mismos
ficheros con los mismos nombres. Un PNG recortado a mano y commiteado sin mas es un
callejon sin salida, y nadie sabria como se hizo.

    python scripts/recortar_mascota.py

El arte original va en el repo (en WebP sin perdida, la mitad que el PNG) porque sin
el este fichero seria documentacion en vez de una herramienta.

No todas las poses de la hoja salen. Las que caen en la esquina oscura — el lobo con
gafas y el de cuerpo entero — tienen un chandal negro pegado a un fondo casi negro,
y sin un contorno claro que los separe no hay umbral que valga: o se come el chandal
o deja el fondo. Se recortan las que si salen limpias y se prescinde del resto, que
es mas honesto que publicar un recorte con agujeros.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "arte"
DESTINO = RAIZ / "app" / "interfaces" / "web" / "koda"
ICONOS = RAIZ / "app" / "interfaces" / "web" / "iconos-app"

# Cuanto se puede alejar un pixel del vecino desde el que crece la region antes de
# considerarlo parte del dibujo. El fondo es un degradado, asi que comparar contra
# un color fijo no sirve: hay que comparar contra el vecino.
#
# Tambien va por recorte. Donde el fondo es oscuro, el lobo tambien lo es y el muro
# de luminancia no separa nada: lo unico que los distingue es el contorno claro, y
# para no treparlo por su antialias hay que exigir saltos pequenos. Donde el fondo es
# claro y uniforme se puede ser generoso y limpiar tambien la sombra.
TOLERANCIA_POR_DEFECTO = 40

# Luminancia a partir de la cual un pixel deja de poder ser fondo. Cada pose viene
# rodeada de un contorno claro, y ese contorno es el muro que para la region: sin
# el, el antialias del borde es una rampa suave que la region sube escalon a escalon
# y acaba comiendose el lobo entero, que es oscuro.
#
# Va por recorte porque las cabezas llevan contorno de pegatina, bien blanco y
# grueso, y las poses de cuerpo entero lo llevan mas fino y grisaceo: con el mismo
# muro para todos, o se cuela dentro del chandal o deja un halo gris alrededor.
MURO_POR_DEFECTO = 168

# La pose corriendo no lleva contorno de pegatina: el chandal negro toca
# directamente la sombra del fondo, que tambien es oscura. Ahi el muro de arriba no
# basta y hace falta un suelo — nada mas oscuro que esto puede ser fondo — porque lo
# que hay que proteger es justo lo negro. Las cabezas no lo necesitan y con suelo 0
# se comportan como antes.
#
# Caja en la hoja (1536x1024), altura final en pixeles CSS x2 (pantallas densas),
# suelo y muro. Las cajas van holgadas a proposito: la region crece desde el borde,
# asi que el borde tiene que ser fondo limpio. Lo que sobre lo quita el recorte.
# nombre: (caja, altura final, suelo, muro, tolerancia)
RECORTES: dict[str, tuple[tuple[int, int, int, int], int, int, int, int]] = {
    # La cara neutra es la que mas se ve: cabecera del chat y tarjeta de entrar.
    "cara": ((382, 0, 648, 282), 256, 0, 168, 40),
    # Ojos cerrados y sonrisa: la bienvenida.
    "cara-contento": ((886, 0, 1136, 272), 256, 0, 168, 40),
    # Con gota de sudor: cuando algo falla.
    "cara-duda": ((1338, 414, 1536, 586), 256, 0, 168, 40),
    # Riendo: cuando acaba de crearte el plan. Tolerancia corta porque aqui el fondo
    # de la hoja es oscuro y el muro de luminancia no separa a un lobo negro de el:
    # lo unico que los distingue es el contorno claro, y para no treparlo por su
    # antialias hay que exigir saltos pequenos.
    "cara-rie": ((1330, 556, 1536, 788), 256, 0, 168, 14),
    # Corriendo. Se usa la pose de la derecha de la hoja y no la de la izquierda:
    # aquella tiene pegado un objeto de la vecina que le sale por detras de la cola,
    # y como esta unido al dibujo, quedarse con la mancha grande no lo quita.
    "corriendo": ((1006, 262, 1364, 676), 520, 44, 128, 40),
}

# El icono de aplicacion ya viene cuadrado y con sus esquinas redondeadas: solo hay
# que sacar los tamaños que piden iOS, Android y el navegador.
TAMANOS_ICONO = (32, 180, 192, 512)


def quitar_fondo(
    imagen: Image.Image,
    suelo: int = 0,
    muro: int = MURO_POR_DEFECTO,
    tolerancia: int = TOLERANCIA_POR_DEFECTO,
) -> Image.Image:
    """Borra el fondo creciendo una region desde los bordes hacia dentro.

    Un `floodfill` normal compara cada pixel contra el del punto de partida, y aqui
    el fondo es un degradado: a mitad de camino ya se ha alejado mas que el dibujo y
    se corta. Creciendo contra el vecino inmediato, el degradado se recorre entero y
    la region solo se para donde hay un salto de color de verdad — que es justo el
    contorno blanco que rodea a cada pose.
    """
    imagen = imagen.convert("RGBA")
    ancho, alto = imagen.size
    pixeles = imagen.load()

    fondo = bytearray(ancho * alto)
    cola: deque[tuple[int, int, tuple[int, int, int]]] = deque()

    def fuera_de_banda(r: int, g: int, b: int) -> bool:
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        return luma >= muro or luma < suelo

    def encolar(x: int, y: int) -> None:
        r, g, b, _ = pixeles[x, y]
        if fondo[y * ancho + x] or fuera_de_banda(r, g, b):
            return
        fondo[y * ancho + x] = 1
        cola.append((x, y, (r, g, b)))

    for x in range(ancho):
        encolar(x, 0)
        encolar(x, alto - 1)
    for y in range(alto):
        encolar(0, y)
        encolar(ancho - 1, y)

    limite = tolerancia * tolerancia * 3
    while cola:
        x, y, (pr, pg, pb) = cola.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            vx, vy = x + dx, y + dy
            if not (0 <= vx < ancho and 0 <= vy < alto) or fondo[vy * ancho + vx]:
                continue
            r, g, b, _ = pixeles[vx, vy]
            if fuera_de_banda(r, g, b):
                continue
            if (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2 <= limite:
                fondo[vy * ancho + vx] = 1
                cola.append((vx, vy, (r, g, b)))

    mascara = Image.frombytes("L", (ancho, alto), bytes(255 - v * 255 for v in fondo))
    # Sin suavizar, el borde queda dentado y se nota sobre el azul del fondo.
    mascara = mascara.filter(ImageFilter.GaussianBlur(0.8))
    imagen.putalpha(mascara)
    return imagen


def dejar_solo_la_pieza_grande(imagen: Image.Image) -> Image.Image:
    """Se queda con la mancha opaca mas grande y borra las demas.

    Las poses estan pegadas unas a otras en la hoja, asi que por holgada que se
    ajuste la caja casi siempre entra una esquirla de la vecina — un trozo de rayo,
    la punta de una oreja. Suelta sobre el fondo de la web se ve como suciedad.

    Afinar la caja a mano lo arregla para esta hoja y se vuelve a romper con la
    siguiente. Quedarse con la pieza grande no: cada recorte es un dibujo, y un
    dibujo es una sola mancha.
    """
    ancho, alto = imagen.size
    alfa = imagen.getchannel("A").tobytes()
    grupo = bytearray(ancho * alto)  # 0 = sin visitar, n = numero de pieza
    piezas: list[int] = [0]

    for inicio in range(ancho * alto):
        if grupo[inicio] or alfa[inicio] <= 32:
            continue
        piezas.append(0)
        numero = len(piezas) - 1
        grupo[inicio] = numero
        cola = deque([inicio])
        while cola:
            actual = cola.popleft()
            piezas[numero] += 1
            x, y = actual % ancho, actual // ancho
            for vx, vy in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if not (0 <= vx < ancho and 0 <= vy < alto):
                    continue
                vecino = vy * ancho + vx
                if grupo[vecino] or alfa[vecino] <= 32:
                    continue
                grupo[vecino] = numero
                cola.append(vecino)

    if len(piezas) <= 2:
        return imagen

    mayor = piezas.index(max(piezas[1:]))
    limpia = bytes(a if grupo[i] == mayor else 0 for i, a in enumerate(alfa))
    imagen.putalpha(Image.frombytes("L", (ancho, alto), limpia))
    return imagen


def recortar_a_lo_que_pinta(imagen: Image.Image) -> Image.Image:
    """Quita el margen transparente para que la altura pedida sea la del dibujo y no
    la del hueco que quedo alrededor."""
    caja = imagen.getbbox()
    return imagen.crop(caja) if caja else imagen


def main() -> int:
    hoja_ruta = ORIGEN / "koda-hoja.webp"
    icono_ruta = ORIGEN / "koda-icono.webp"
    faltan = [str(p.relative_to(RAIZ)) for p in (hoja_ruta, icono_ruta) if not p.exists()]
    if faltan:
        print("Falta el arte original: " + ", ".join(faltan))
        print("Los recortes ya generados estan en el repo; esto solo hace falta para rehacerlos.")
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    ICONOS.mkdir(parents=True, exist_ok=True)

    hoja = Image.open(hoja_ruta).convert("RGBA")
    for nombre, (caja, altura, suelo, muro, tolerancia) in RECORTES.items():
        sin_fondo = quitar_fondo(hoja.crop(caja), suelo, muro, tolerancia)
        pose = recortar_a_lo_que_pinta(dejar_solo_la_pieza_grande(sin_fondo))
        ancho = round(pose.width * altura / pose.height)
        pose = pose.resize((ancho, altura), Image.Resampling.LANCZOS)
        salida = DESTINO / f"{nombre}.webp"
        pose.save(salida, format="WEBP", quality=88, method=6)
        print(f"{salida.relative_to(RAIZ)}  {pose.width}x{pose.height}  {salida.stat().st_size // 1024} KB")

    icono = Image.open(icono_ruta).convert("RGBA")
    for lado in TAMANOS_ICONO:
        salida = ICONOS / f"icono-{lado}.png"
        icono.resize((lado, lado), Image.Resampling.LANCZOS).save(salida, format="PNG", optimize=True)
        print(f"{salida.relative_to(RAIZ)}  {lado}x{lado}  {salida.stat().st_size // 1024} KB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
