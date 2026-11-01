# Changelog

Los cambios relevantes de OpenFinance, para quien lo usa en casa. Formato de [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); las versiones siguen [Versionado Semántico](https://semver.org/lang/es/). El detalle técnico de cada punto está en el [roadmap](docs/product/roadmap.md) con su ticket `OF-xxx`.

## [Unreleased]

Se publicará como **0.1.0**, la primera versión para usar en casa. Pasos en [docs/development/release.md](docs/development/release.md).

### Pendiente antes de 0.1.0

- La fase 7 (corregir sin miedo) del [roadmap](docs/product/roadmap.md). La fase 6 (datos fiables) está hecha salvo reconocer los traspasos de la conjunta a las cuentas personales, que necesitan un extracto real.
- Un mes de uso real con vuestros datos (hito v0.1).
- Instalarlo en casa y probarlo en un móvil real. La instalación de extremo a extremo (`compose-e2e`) ya pasa en verde en CI.
- Pendientes de los extractos reales (ver [bancos.md](docs/product/bancos.md)): hora local o UTC, signo de la comisión y texto de las huchas en el Excel de Revolut en español.

### Added

- **Hogar y acceso** (OF-101): un hogar con dos personas que entran con email y contraseña. El alta se hace una vez en el servidor (`make bootstrap`); no hay registro público.
- **Cuentas** (OF-102, [ADR-0013](docs/adr/0013-cuentas-personales-privadas.md)): la cuenta conjunta de Revolut, sus huchas y las cuentas personales de Bankinter, con su saldo. Cada cuenta personal solo la ve su titular.
- **Movimientos** (OF-103, OF-106): por mes, con búsqueda, filtro por cuenta y «solo sin categoría». Cada fila dice si es aportación de quién, traspaso a la hucha, devolución, ingreso o gasto. Los traspasos al ahorro no cuentan como gasto.
- **Importar extractos** (OF-104, OF-105, OF-107): CSV o Excel de Revolut y Excel de Bankinter, en tres pasos (elegir, revisar, confirmar). La revisión dice qué es nuevo, qué ya estaba, qué se descarta y si el saldo cuadra con el del banco. Importar el mismo extracto dos veces no duplica nada.
- **Categorías** (OF-201 a OF-203): 13 categorías de partida que podéis renombrar, recolorear u ocultar. Al corregir un gasto, OpenFinance aprende el comercio y clasifica los demás gastos sin categoría de ese comercio. Nunca cambia una categoría elegida a mano.
- **Gráficos** (OF-301 a OF-305): las pantallas «Este mes», «¿En qué gastamos?» y «Evolución», con lo gastado y ahorrado, el gasto por categoría frente a vuestra media, el ritmo del mes y 12 meses de historia. `make demo` crea un hogar ficticio para verlos sin datos reales.
- **Mi gasto** (OF-108): en «Este mes» y «¿En qué gastamos?», el selector «Hogar / Mío» enseña el gasto de tus cuentas personales y lo que has aportado a la conjunta. Solo lo ves tú y no cambia los totales del hogar.
- **Ahorro** (OF-401 a OF-405): presupuestos por categoría con aviso al 85 %, objetivos de ahorro con fecha estimada, detección de cuotas y subidas de precio, ideas de ahorro con su respaldo y un simulador de recortes.
- **Mantenimiento** (OF-606): `openfinance users set-password` cambia la contraseña de alguien desde el servidor y cierra sus sesiones; `openfinance accounts add` añade una hucha o una cuenta después del alta. Ver [Instalar en casa](docs/deployment/home.md).
- **Exportación y copias** (OF-501, [ADR-0016](docs/adr/0016-exposicion-y-copias.md)): botón **Exportar** (JSON o CSV) con lo que ve cada persona, y `make backup` / `make restore` para guardar y recuperar toda la base de datos.
- **Instalación en casa** (OF-502): Docker Compose para usarlo en la red local o desde fuera con HTTPS y dominio propio. Guía: [Instalar en casa](docs/deployment/home.md).
- **Móvil** (OF-503): todas las pantallas y los gráficos se usan bien en el móvil.
- **Licencia** (OF-504, [ADR-0008](docs/adr/0008-licencia-agpl.md)): AGPL-3.0-or-later, con dependencias auditadas ([docs/legal/dependencias.md](docs/legal/dependencias.md)) y contribuciones con DCO ([CONTRIBUTING.md](CONTRIBUTING.md)).

- **Corregir movimientos** (OF-701, [ADR-0017](docs/adr/0017-registro-de-cambios.md)): en Movimientos, pulsa el concepto para cambiar el tipo (gasto, ingreso, aportación de quién, hucha, entre cuentas) o añadir una nota. Cada corrección queda en su historial con quién y cuándo, y se puede deshacer desde el aviso. El importe, la fecha y el concepto del banco no se tocan.
- **Varios a la vez y efectivo** (OF-705): en «Solo sin categoría» puedes elegir varios gastos y ponerles la misma categoría de una vez. «+ Añadir a mano» apunta un gasto o un ingreso que no viene del banco (por ejemplo, en efectivo); se puede borrar y deshacer.

### Fixed

- **Importar** (OF-601): un extracto con una fila de 0,00 € (por ejemplo, una verificación de tarjeta) ya se puede confirmar. Esas filas, y las que no traen importe, aparecen como descartadas con su motivo.
- **Clasificación** (OF-602): sacar dinero de una hucha («From pocket») ya no cuenta como ingreso; en Movimientos se lee «De la hucha». Los nombres y patrones se buscan por palabra completa: una transferencia de «Mariana» ya no es una aportación de Ana.
- **Movimientos** (OF-603): buscar un texto con «#» ya no deja la lista congelada. Si una pantalla falla, aparece «Algo ha fallado» con un botón para recargar.
- **Importar** (OF-604): un «1,234» del CSV de Revolut (mil doscientos treinta y cuatro) ya no se lee como 1,234 €. Cada banco tiene su formato de número; lo que no lo sigue, o se puede leer de dos maneras, aparece como fila descartada en vez de guardarse con un importe equivocado.
- **Mes en curso** (OF-608): Evolución y Este mes dan la misma media, porque las dos solo cuentan meses completos. A mitad de mes cada categoría se compara con lo gastado hasta el mismo día de los meses anteriores, así que el día 1 ya no parece que todo esté muy por debajo de la media.
- **Pantallas** (OF-605): si algo no carga, se ve el error con un botón **Reintentar**. Antes el panel de movimientos de una categoría se quedaba en «Cargando…» y Presupuestos no se recuperaba sin recargar la página.

### Security

- Contraseñas con Argon2id, sesiones en el servidor con cookie `HttpOnly` y límite de intentos de inicio de sesión. Las escrituras de la API exigen una cabecera contra CSRF.
- Ni la base de datos ni la API se publican fuera del equipo. La IP que ve la API no se puede falsificar.
- Un extracto subido y no confirmado se borra a las 24 h aunque nadie vuelva a importar: al arrancar, al iniciar sesión y antes de cada `make backup` (OF-607).
- Los extractos se leen con límites de tamaño y sin ejecutar fórmulas. La exportación CSV va protegida frente a fórmulas.
- Los datos de un hogar y las cuentas personales de cada persona están aislados, y hay tests que lo comprueban.
