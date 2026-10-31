# Visión de producto

**OpenFinance es el gestor económico de nuestra casa.** Una pareja con una cuenta común quiere saber, de un vistazo y con gráficos claros:

1. **¿Cuánto gastamos?** Este mes, frente al anterior y frente a nuestra media.
2. **¿En qué se va?** Por categoría y por comercio, y cómo evoluciona cada una.
3. **¿Cómo ahorramos mejor?** Objetivos, ideas concretas calculadas con nuestros datos y un simulador.

Es open source, se ejecuta en casa o en un servidor propio y los datos no salen de ahí ([ADR-0007](../adr/0007-local-first-self-hosted.md)).

## Pantallas de v0.1

| Pantalla | Qué responde |
| --- | --- |
| **Este mes** | Gastado y ahorrado, categoría principal, donut de categorías, ritmo de gasto día a día frente al mes anterior y al presupuesto, cambios frente a la media y presupuestos. |
| **¿En qué gastamos?** | Donut y ranking de categorías. Al pulsar una se ven sus 12 meses frente a la media, sus comercios principales y sus movimientos. |
| **Evolución** | Barras apiladas de 12 meses por categoría, ahorro de cada mes, mejor y peor mes. |
| **Ahorrar** | Objetivos con fecha estimada, ideas de ahorro con euros al año y un simulador de recortes que mueve la fecha del objetivo. |
| **Movimientos** | Lista por mes con búsqueda; la categoría se cambia en la propia tabla y se aprende una regla. |
| **Importar** | CSV del banco → revisión con categorías propuestas y duplicados → listo. |

Prototipo navegable: [prototypes/index.html](prototypes/index.html).

## Reglas del dinero

- Importes exactos (`Decimal`/céntimos), nunca `float`.
- Las **aportaciones** de cada persona a la cuenta común son entradas.
- El **traspaso a la cuenta de ahorro es ahorro**, no gasto.
- **Ahorro del mes** = lo que entra − lo que se gasta.
- Importar dos veces el mismo archivo no duplica movimientos.

## Fuera de v0.1, para crecer después

Por orden aproximado de prioridad:

1. Más cuentas del hogar (ahorro, tarjetas) y conciliación de saldos.
2. Conexión automática con el banco (Open Banking).
3. Asistente con IA que explique los gráficos y proponga cambios con aprobación ([ADR-0004](../adr/0004-separacion-core-manager.md), [ADR-0005](../adr/0005-aprobacion-humana.md)).
4. Perfiles compartidos y reparto de gastos entre personas ([ADR-0011](../adr/0011-perfiles-compartidos-reparto.md)).
5. Módulos y extensiones ([ADR-0006](../adr/0006-modulos-oficiales-primero.md)).

El razonamiento está en [ADR-0012](../adr/0012-empezar-por-el-hogar.md).

## Fases

Detalle con tickets y criterios de aceptación en el [roadmap](roadmap.md).

0. **Base** (hecha): repositorio, CI, Docker Compose y `Money`.
1. **Datos**: hogar, dos usuarios, cuenta, movimientos e importación CSV con deduplicación.
2. **Categorías**: categorías, reglas aprendidas y corrección en la tabla.
3. **Gráficos**: Este mes, ¿En qué gastamos? y Evolución.
4. **Ahorro**: presupuestos, objetivos, ideas y simulador.
5. **Uso real**: copias de seguridad, instalación en casa y primeros meses con datos reales.
