# ADR-0014: Gráficos SVG propios en React

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

La fase 3 (OF-302 a OF-305) necesita estos gráficos: donut, barras con línea de referencia y mes resaltado, barras apiladas, líneas con área y anillo de progreso (fase 4). Son pocos y sencillos, con volúmenes pequeños: 12 meses y unas 15 categorías. Deben:

- verse bien en el móvil (OF-503);
- ser accesibles;
- poder probarse con los mismos tests que el resto de la web (Vitest + jsdom);
- no tratar importes como `float`.

El prototipo (`docs/product/prototypes/charts.js`) ya los dibuja con SVG a mano en unas 150 líneas.

### Medidas

Se construyó el mismo conjunto (donut, barras con referencia y líneas) con cada opción, con `esbuild --minify` y gzip -9 en producción. La tabla muestra cuánto añade cada una sobre la base de React 19 (69,1 KB gzip):

| Opción | Versión | Añade (gzip) | Tecnología |
| --- | --- | --- | --- |
| SVG propio | — | ≈ 0,2 KB por gráfico (≈ 4 KB todos) | SVG en React |
| Chart.js | 4.6.1 | 61,7 KB | `<canvas>` |
| Recharts | 3.10.1 | 121,6 KB | SVG (con dependencias de d3) |

La web completa ocupa hoy ≈ 74 KB gzip; Recharts casi la triplicaría.

### Otros criterios

| Criterio | SVG propio | Chart.js | Recharts |
| --- | --- | --- | --- |
| Accesibilidad | `role="img"`, `aria-label`, `<title>` y tabla equivalente para lectores de pantalla | Canvas: un mapa de bits sin estructura; hay que duplicar los datos aparte | SVG accesible, pero con sus propias capas a configurar |
| Tests en jsdom | Se puede inspeccionar el DOM de cada barra | jsdom no implementa canvas: hace falta simularlo | Necesita simular `ResizeObserver` y medidas del contenedor |
| Móvil | `viewBox` escalable, sin medir el contenedor | Redimensiona por JS | `ResponsiveContainer` redimensiona por JS |
| Mantenimiento | Código nuestro (≈ 300 líneas), sin dependencias | Dependencia madura, API imperativa | Dependencia grande, cambios de API entre versiones mayores |
| Interacción avanzada (zoom, selección de rangos) | No | Sí, mediante plugins | Parcial |

## Decisión

Portar a componentes React los gráficos SVG del prototipo, en `apps/web/src/components/charts/`:

- **Accesibilidad:** cada gráfico se dibuja dentro de un `<figure>` con `role="img"` y un `aria-label` que resume el dato principal. Además lleva una tabla de datos visualmente oculta (`.sr-only`) para lectores de pantalla y un `<title>` por elemento, que hace de tooltip nativo.
- **Escalado:** se usa `viewBox` y el gráfico ocupa el 100 % del ancho, sin medir el contenedor.
- **Importes:** la API sigue enviando texto decimal exacto. Para dibujar, los importes se convierten a céntimos (`BigInt`) y de ahí a `Number`. Ese `Number` solo se usa para calcular la geometría; las cifras que se muestran siempre salen del texto original con `formatMoney`.
- **Cálculos en el Core:** los totales, medias y agregados se calculan en el backend (OF-301); los componentes solo pintan.

## Consecuencias

- El tamaño de la web prácticamente no cambia (≈ 4 KB) y no se añade ninguna dependencia.
- Los gráficos se prueban con Testing Library como cualquier otro componente.
- Mantenemos nosotros ejes, escalas y etiquetas; los casos raros (valores negativos, meses sin datos) hay que probarlos.
- Se revisará esta decisión si hace falta interacción avanzada (zoom, selección de rangos o series largas de muchos años). La alternativa preferida entonces sería una librería de bajo nivel y por módulos, o Chart.js si se acepta el canvas.
