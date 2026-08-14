# Licencias de terceros — interfaz web

Tipografías e iconos están **vendorizados en el repo**, no cargados desde un CDN.
El porqué está en [ADR-015](../../../docs/adr/ADR-015-direccion-visual-y-presupuesto-de-movimiento.md):
una petición menos que puede fallar, la app funciona sin internet y no le cuenta a
un tercero quién la está usando.

| Recurso | Versión | Licencia | Texto completo |
|---|---|---|---|
| [Archivo](https://fonts.google.com/specimen/Archivo) (variable, subconjunto latin) | v25 | SIL Open Font License 1.1 | [`licencias/OFL-Archivo.txt`](licencias/OFL-Archivo.txt) |
| [DM Mono](https://fonts.google.com/specimen/DM+Mono) (400 y 500, subconjunto latin) | v16 | SIL Open Font License 1.1 | [`licencias/OFL-DM-Mono.txt`](licencias/OFL-DM-Mono.txt) |
| [Phosphor Icons](https://phosphoricons.com) (peso Regular) | v2.1.1 | MIT | [`licencias/MIT-Phosphor.txt`](licencias/MIT-Phosphor.txt) |

## Qué se descarga

| Archivo | Tamaño |
|---|---|
| `fuentes/archivo-variable-latin.woff2` | 88 KB |
| `fuentes/dm-mono-400-latin.woff2` | 14 KB |
| `fuentes/dm-mono-500-latin.woff2` | 15 KB |
| `iconos.svg` (30 iconos en un sprite) | 13 KB |

Los tres archivos de fuente son solo el subconjunto **latin**, no la familia entera.
`iconos.svg` es un único sprite: una petición cacheada para todos los iconos, y
heredan el color del texto con `currentColor`.

## Cómo se regenera el sprite

Los `<symbol>` salen de los SVG originales de Phosphor sin retocarlos a mano. Si
hace falta un icono nuevo, se descarga de
`https://unpkg.com/@phosphor-icons/core@2.1.1/assets/regular/<nombre>.svg` y se
añade al sprite con el mismo `viewBox="0 0 256 256"` y `fill="currentColor"`.
