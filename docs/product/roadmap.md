# Roadmap y backlog

Alcance: [ADR-0012 · Empezar por el hogar](../adr/0012-empezar-por-el-hogar.md). Referencia visual: [prototipo](prototypes/index.html).

Un ticket está terminado cuando cumple sus criterios de aceptación, tiene tests y `make check` está en verde. Los criterios marcados con 🧪 deben quedar como tests automáticos.

## Resumen

| Fase | Objetivo | Tickets | Estado |
| --- | --- | --- | --- |
| 0 · Base | Repositorio, CI, entorno y `Money` | OF-001 … OF-003 | ✅ Hecha |
| 1 · Datos | Meter los movimientos reales de Revolut (conjunta) y Bankinter (personales) | OF-101 … OF-108 | ✅ Hecha |
| 2 · Categorías | Que cada gasto tenga su categoría casi sin esfuerzo | OF-201 … OF-203 | ✅ Hecha |
| 3 · Gráficos | Este mes, ¿En qué gastamos? y Evolución | OF-301 … OF-305 | ✅ Hecha |
| 4 · Ahorro | Presupuestos, objetivos, ideas y simulador | OF-401 … OF-405 | ✅ Hecha |
| 5 · Uso real | Instalado en casa, con copias de seguridad | OF-501 … OF-504 | ✅ OF-501 a OF-503 (CI en verde, también `compose-e2e`) · OF-504 preparado: falta la etiqueta `v0.1.0` tras el mes de uso real |
| 6 · Datos fiables | Que cualquier extracto real se importe sin errores ni entradas infladas | OF-601 … OF-608 | 🚧 En curso · OF-601 ✅ · OF-602 ✅ (salvo traspasos internos) · OF-603 ✅ · OF-604 ✅ · OF-605 ✅ · OF-606 ✅ · OF-607 ✅ |
| 7 · Corregir sin miedo | Editar, deshacer y ajustar desde la web, con historial | OF-701 … OF-706 | Pendiente |
| 8 · Uso diario | Móvil, PWA, accesibilidad y mes en curso honesto (v0.2) | OF-801 … OF-806 | Pendiente |
| 9 · Operación | Copias cifradas, dependencias y actualizaciones (v0.2) | OF-901 … OF-907 | Pendiente |
| 10 – 17 | Del libro contable completo a la 1.0 | OF-1001 … OF-1705 | Ver [Después de v0.2](#después-de-v02) |

**Hito v0.1:** fases 6 y 7 terminadas y al menos un mes de uso real con vuestros datos. La auditoría del 1 de noviembre de 2026 encontró fallos que, con datos reales, dejan importaciones que no se pueden confirmar o totales inflados que no se pueden corregir; por eso la fase 6 va antes del mes de uso real.

## Cómo retomar

Estado a 1 de noviembre de 2026. Código en [github.com/rldona/OpenFinance](https://github.com/rldona/OpenFinance) (público, rama `main`). CI en verde en todos sus jobs: `backend`, `frontend`, `licenses` y `compose-e2e` en los modos `direct` y `https`.

### Lo que falta para v0.1, en orden

0. **Terminar la fase 6** (OF-608 y los traspasos internos de OF-602). Sin ella, el mes de uso real produciría datos que hoy no se pueden corregir. La fase 7 se puede hacer durante ese mes.
1. **Instalar en casa** siguiendo [Instalar en casa](../deployment/home.md), en modo HTTPS con dominio propio, en un equipo x86-64:
   1. Configurar el DNS del dominio y abrir los puertos 80 y 443 del router hacia el equipo.
   2. En `.env`: `COMPOSE_FILE=compose.yaml:compose.https.yaml`, `OPENFINANCE_DOMAIN` y una contraseña de PostgreSQL aleatoria.
   3. `docker compose up -d --wait` y después `make bootstrap` para crear el hogar, las dos personas y sus cuentas.
   4. **Antes de importar nada**, guardar el final de la tarjeta con la que cada persona recarga la conjunta: `openfinance member-patterns add <email> '*NNNN'`. Revolut muestra las recargas como «Recarga de \*NNNN», sin nombre. Sin ese patrón entran como ingreso y **no se pueden reclasificar después**.
   5. Comprobar un extracto sin tocar la base de datos: `openfinance statement-check --bank revolut|bankinter FICHERO`. Solo muestra recuentos.
   6. Importar desde la pantalla **Importar**: Revolut en la conjunta y el Bankinter de cada persona en su cuenta personal.
   7. Programar `make backup` con cron y probar una vez `make restore FILE=…`.
   8. Abrirlo desde un móvil real: pestañas, Importar, descarga de la exportación y que el teclado no tape los campos.
2. **Un mes de uso real** con vuestros datos.
3. **Release:** seguir [release.md](../development/release.md). Hay que subir las versiones a 0.1.0, crear la etiqueta anotada `v0.1.0` y publicar la release en GitHub.

### Pendientes menores (no bloquean v0.1)

- Revolut (ver [bancos.md](bancos.md)): confirmar si las horas están en hora local o en UTC, el signo de la comisión y cómo aparecen las huchas en el Excel en español. El extracto de octubre no tiene comisiones ni huchas, así que se confirmará con los próximos.
- No se puede cambiar el tipo ni la persona de un movimiento ya importado. Si hace falta, merece su propio ticket.
- «Cerrar todas las sesiones» desde la web, cuando exista el cambio de contraseña. Hoy solo existe en la CLI: `openfinance sessions revoke-all`.

### Notas de entorno

- **Extractos reales:** van en `/Extractos`, que está en `.gitignore`. Nunca se copian a tests, fixtures ni documentación. Los tests usan archivos sintéticos.
- **Sin Docker ni PostgreSQL en el portátil de desarrollo:** los tests de base de datos corren en local con SQLite, y Compose solo se prueba en CI. Playwright sí funciona en local con la API sobre SQLite y Vite (ver [getting-started](../development/getting-started.md)).
- **Identidad de git:** commits con `Raúl López Doña <1206870+rldona@users.noreply.github.com>` (ya configurado en este repositorio) y firmados con DCO (`git commit -s`).
- **npm:** el `~/.npmrc` del equipo apunta a un registro corporativo. Si se regenera el lock, hay que hacerlo con `npm install --registry=https://registry.npmjs.org/`. CI falla si `package-lock.json` contiene URLs de otro registro.
- **Vercel:** nunca se lanzan despliegues de preview. Todo pasa por GitHub Actions.

---

## Fase 0 · Base ✅

| ID | Ticket | Estado |
| --- | --- | --- |
| OF-001 | Monorepo: `services/api` (FastAPI) y `apps/web` (React) con capas y `import-linter` | ✅ |
| OF-002 | Entorno: Docker Compose, `.env.example`, `Makefile` | ✅ (Compose revisado en OF-502 y probado de extremo a extremo en CI: job `compose-e2e`) |
| OF-003 | CI: lint, tipos, tests, build y migraciones sobre PostgreSQL | ✅ |

---

## Fase 1 · Datos

### OF-101 · Hogar y personas ✅
Un hogar (`Workspace`) con dos personas que inician sesión con email y contraseña.
- ✅ `make bootstrap` (o `openfinance bootstrap`) crea el hogar, las dos personas y sus cuentas; no hay registro público.
- ✅ Sesión en servidor con cookie `HttpOnly` y `SameSite=Lax` (`Secure` configurable); en la base de datos solo se guarda el hash del token. Contraseñas con Argon2id, mínimo 10 caracteres.
- ✅ Las dos personas tienen acceso completo a lo común; no hay roles.
- ✅ 🧪 Sin sesión, la API responde 401; con sesión, solo devuelve datos de su hogar. Una contraseña errónea y un email desconocido dan la misma respuesta; la sesión caduca y el cierre de sesión la invalida.
- ✅ Revisión de seguridad aplicada:
  - Limitador de intentos de login: 5 por email y 20 por IP cada 15 minutos, y también en nginx.
  - Como mucho 2 verificaciones de Argon2 a la vez.
  - La cookie es `Secure` en producción.
  - Al iniciar sesión se sustituye la sesión anterior y se purgan las caducadas.
  - Los errores 422 no devuelven lo enviado.
  - Se rechaza CORS `*` y `/docs` queda oculto en producción.
  - Claves foráneas compuestas que impiden mezclar hogares en movimientos y titulares.
- Pendiente: pantalla de login en la web (OF-106); «cerrar todas las sesiones» cuando exista el cambio de contraseña; exigir JSON y comprobar `Origin` en los futuros endpoints de escritura.

### OF-102 · Cuentas ✅
Cuenta conjunta de Revolut, huchas y cuentas personales de Bankinter, con entidad, moneda y saldo inicial ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)).
- ✅ Una cuenta personal tiene titular y solo la ve esa persona.
- ✅ 🧪 Saldo actual = saldo inicial + suma de movimientos, calculado con `Money`.
- ✅ `GET /api/v1/accounts`: primero la conjunta, después las huchas y al final las personales.

### OF-103 · Movimientos ✅
Modelo y API de movimientos.
- ✅ Campos: cuenta, fecha y hora, fecha valor, concepto original, importe (`Money`, comisión incluida), tipo, categoría (opcional), persona (en aportaciones), tipo según el banco, procedencia y huella de deduplicación (única por cuenta).
- ✅ Tipos: `contribution`, `expense` (un importe positivo es una devolución), `income`, `savings_transfer` e `internal_transfer`.
- ✅ `GET /api/v1/transactions?month=2026-10&q=…&uncategorized=true&account_id=…`.
- ✅ 🧪 Los traspasos y las transferencias internas no cuentan como gasto; las aportaciones cuentan como entrada; las devoluciones restan gasto; una aportación que sale de una cuenta personal no es entrada ni gasto del hogar.
- ✅ 🧪 Aislamiento: ni los movimientos de otro hogar ni los de la cuenta personal de tu pareja aparecen; pedirlos por id da 404.
- Nota: la categoría es por ahora un texto libre (`super`, `vivienda`…); OF-201 la convertirá en entidad.

### OF-104 · Lector del extracto de Revolut ✅
Lectura del extracto de la cuenta conjunta de Revolut. Formato y decisiones en [bancos.md](bancos.md) y [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md).
- ✅ Lector `parse_revolut` que detecta el formato: CSV con cabeceras en inglés o Excel (.xlsx) en español, validado con un extracto real. Solo filas completadas y del producto de la cuenta, comisión incluida en el importe.
- ✅ Los importes nunca pasan por `float`: del CSV se leen como texto y del Excel desde su representación decimal.
- ✅ Cabeceras con la codificación rota (`DescripciÃ³n`) reparadas; horas de Excel redondeadas al segundo; pendientes sin fecha de fin ni saldo descartados con su motivo.
- ✅ Propone el tipo: aportación por persona (nombre o patrón guardado), traspaso a hucha, ingreso, gasto o devolución (también un pago con tarjeta positivo).
- ✅ Huella estable para deduplicar, sin fusionar filas idénticas del mismo archivo. 🧪 El mismo extracto en CSV y en Excel da las mismas huellas; 🧪 las huellas ya guardadas no cambian.
- ✅ Comprobación del saldo fila a fila en el orden del archivo (fecha de finalización); el saldo final del banco es el de la última fila.
- ✅ Patrones de cada persona guardados en el hogar (`member_patterns`) y gestionados con `openfinance member-patterns` (ADR-0015).
- ✅ Lectura segura de Excel: límites de tamaño, ratio de compresión, filas y columnas; sin fórmulas ni enlaces; XML con `defusedxml`.
- ✅ `openfinance statement-check` para comprobar un extracto sin base de datos mostrando solo recuentos.
- Pendiente (ver [bancos.md](bancos.md)): hora local o UTC, signo de la comisión y texto de las huchas en el Excel en español.

### OF-105 · Importación idempotente ✅
Vista previa → confirmación, sin duplicados.
- ✅ `POST /api/v1/imports` (multipart: `account_id`, `file`): lee el extracto y devuelve la vista previa sin guardar movimientos. Indica nuevos, ya importados, filas descartadas con su motivo, descuadres internos del extracto y si el saldo final coincidirá con el del banco.
- ✅ `POST /api/v1/imports/{id}/commit`: guarda solo los nuevos, con procedencia (`import:<archivo>` e `import_id`). Repetirlo devuelve el mismo resultado sin volver a guardar.
- ✅ Deduplicación por huella, única por cuenta en la base de datos, y comprobación previa de las huellas existentes.
- ✅ Aportaciones reconocidas por el nombre de cada persona en el concepto; «To pocket» → hucha. Se ajustará con los extractos reales.
- ✅ Límites: 5 MB por archivo y vista previa válida 24 h. El contenido del archivo se borra al confirmar.
- ✅ 🧪 Importar dos veces el mismo archivo no crea movimientos nuevos; confirmar dos veces tampoco.
- ✅ 🧪 Dos cafés iguales el mismo día en el mismo archivo **no** se consideran duplicados.
- ✅ 🧪 Un extracto que solapa con uno anterior solo añade lo nuevo.
- ✅ 🧪 No se puede importar en la cuenta personal de la pareja ni en otro hogar; nadie de otro hogar puede confirmar una vista previa ajena.
- ✅ Las escrituras de la API exigen la cabecera `X-Requested-With: OpenFinance` (protección CSRF).

### OF-106 · Pantallas Movimientos e Importar ✅
Versión real de las pantallas del prototipo.
- ✅ Pantalla de inicio de sesión y cabecera con hogar, pestañas, miembros y «Salir».
- ✅ **Movimientos**: por mes (o todos), búsqueda, filtro por cuenta y «solo sin categoría». Cada fila indica su tipo: aportación de quién, a la hucha, devolución, ingreso o sin categoría.
- ✅ **Importar** en 3 pasos: elegir cuenta y extracto; revisar nuevos, ya importados, descartados y si el saldo cuadra con el banco; confirmar.
- ✅ Cliente de API tipado con tipos generados desde OpenAPI (`make openapi`); CI falla si el contrato o los tipos no están al día (ADR-0009).
- ✅ Importes formateados desde el decimal exacto, sin `float`, también en el navegador.
- ✅ Probadas en navegadores reales con Playwright (OF-503), junto con las pestañas de gráficos (fase 3).

### OF-107 · Lector de Bankinter (cuentas personales) ✅
- ✅ Lector `parse_bankinter` del Excel de movimientos, validado con un extracto real: salta el preámbulo y los filtros, descarta los pendientes con su motivo e invierte el orden (el banco lista del más reciente al más antiguo) para que cuadre el saldo.
- ✅ El número de cuenta del preámbulo no se lee ni aparece en errores ni en filas descartadas. Los `.xls` antiguos y los CSV se rechazan con un mensaje claro.
- ✅ 🧪 Sin hora en el extracto, la huella incluye el saldo: dos movimientos iguales el mismo día no se fusionan y un extracto solapado no duplica.
- ✅ 🧪 Las salidas «Revolut\*\*NNNN\*» y las que coinciden con un patrón de salida del titular son **aportación** del titular; no cuentan como gasto ni en los totales del hogar.
- ✅ 🧪 En la cuenta personal no se usan los nombres: un Bizum de la pareja es ingreso. Transferencias y Bizum según el signo.
- ✅ 🧪 Solo el titular puede previsualizar, confirmar y ver los movimientos importados; ni la pareja ni otro hogar.
- La vista personal «mi gasto» pasa a OF-108.
- Depende de: OF-105.

### OF-108 · Vista «mi gasto» de cada persona ✅
Vista de las cuentas personales de cada persona, visible solo para ella (ADR-0013).
- ✅ `GET /api/v1/insights/month` y `/insights/category` aceptan `view=household|mine` (por defecto `household`). `mine` usa solo las cuentas personales de quien pregunta: gastado, ingresos, aportado a la conjunta (`contributed`) y gasto por categoría con su media; al elegir una categoría, sus 12 meses y comercios.
- ✅ `GET /api/v1/transactions?mine_only=true` lista los movimientos de esas cuentas (incompatible con `shared_only`).
- ✅ Web: selector «Hogar / Mío» en «Este mes» y «¿En qué gastamos?», compartido entre las dos pantallas. En «Mío», lo aportado a la conjunta se muestra aparte («no cuenta como gasto tuyo») y no aparecen los presupuestos, que son del hogar.
- ✅ 🧪 Tests negativos: la pareja no ve los agregados ni los movimientos de la cuenta personal del otro, ni pidiendo una categoría; otro hogar tampoco. La vista personal no altera los totales del hogar.
- Decidido: basta la vista del mes. «Evolución» (12 meses de todo) sigue siendo solo del hogar; si hace falta una evolución personal, merece su propio ticket.
- Depende de: OF-107.

---

## Fase 2 · Categorías

### OF-201 · Categorías ✅
- ✅ Categorías por hogar con nombre, icono, color y orden; cada hogar nace con las 13 del prototipo (identificadas por `slug`).
- ✅ Crear, renombrar, cambiar icono o color y ocultar (`GET/POST /api/v1/categories`, `PATCH /api/v1/categories/{id}`). No se borran.
- ✅ Nombres únicos por hogar sin distinguir mayúsculas ni tildes.
- ✅ 🧪 Ocultar una categoría no borra la de sus movimientos; una categoría oculta no se puede asignar a movimientos nuevos.
- ✅ Migración 0004 de los datos existentes: el texto libre pasa a categoría (las desconocidas se crean como propias) y se calcula el comercio de cada movimiento.

### OF-202 · Reglas por comercio ✅
- ✅ Comercio normalizado (`merchant_key`): quita prefijos del banco («COMPRA TARJETA 4821», «PAGO CON TARJETA», «RECIBO DE»…), números de tarjeta o terminal y sufijos societarios. Ejemplo: «MERCADONA 0087» → `MERCADONA`.
- ✅ Al corregir la categoría de un gasto se guarda la regla «comercio → categoría» y se aplica a los gastos **sin categoría** de ese comercio; nunca pisa una elegida a mano. Al quitar la categoría, se olvida la regla.
- ✅ Prudencia antes que cobertura:
  - Una regla aplica si sus palabras son el principio del comercio (`MERCADONA` → `MERCADONA VALENCIA`), nunca al revés.
  - Las reglas de una sola palabra corta (`BAR`, `GAS`) o de intermediarios (`PAYPAL`, `AMAZON`…) solo aplican al comercio exacto y no se propagan.
- ✅ Privacidad (ADR-0013): una regla aprendida en una cuenta personal es solo de su titular y solo afecta a sus cuentas personales. Las del hogar afectan a las cuentas que ve quien corrige.
- ✅ Las reglas se aplican en la vista previa de importación y al confirmar.
- ✅ 🧪 Corregir «MERCADONA 1234» clasifica también «MERCADONA 0087» y «COMPRA TARJETA … MERCADONA VALENCIA».

### OF-203 · Corrección en la tabla ✅
- ✅ `PATCH /api/v1/transactions/{id}` (`category_id`, `learn`) devuelve la regla aprendida y cuántos movimientos más se han clasificado.
- ✅ Web: selector de categoría en cada gasto, aviso «N gastos sin categoría» con acceso directo al filtro y contador en la pestaña (`GET /api/v1/transactions/uncategorized-count`).
- ✅ Mensaje «Regla guardada: «Mercadona» → Supermercado · 2 más clasificados».
- ✅ Pantalla **Categorías** (`#categorias`) para crear, renombrar, cambiar icono o color y ocultar.
- ✅ La vista previa de importación muestra la categoría propuesta por regla.

---

## Fase 3 · Gráficos

### OF-301 · API de agregados (`insights`) ✅
El Core calcula y el frontend solo pinta. Los totales del hogar usan solo la conjunta y las huchas (ADR-0013).
- ✅ `GET /api/v1/insights/month`: gastado, entradas (aportaciones por persona), ahorro y %, gasto por categoría con su media, gasto acumulado por día, mes anterior y media de los meses anteriores con datos.
- ✅ Mes en curso: la curva llega hasta hoy (en la zona horaria del hogar, `OPENFINANCE_TIMEZONE`) y se compara con el mismo tramo del mes anterior.
- ✅ `GET /api/v1/insights/category`: 12 meses de una categoría (o «sin categoría»), su media y los comercios principales de los últimos 3 meses.
- ✅ `GET /api/v1/insights/trends`: 12 meses de gasto, entradas, ahorro y gasto por categoría; totales, medias, % de ahorro y mejor y peor mes.
- ✅ `GET /api/v1/transactions?category_id=…&shared_only=true` para listar los movimientos de un gráfico.
- ✅ 🧪 Las sumas por categoría cuadran con el gasto del mes; los traspasos a ahorro quedan fuera del gasto; las cuentas personales nunca cuentan; los meses sin datos no entran en las medias.

### OF-302 · Componentes de gráficos ✅
- ✅ Decidido en [ADR-0014](../adr/0014-graficos-svg-propios.md), con medidas: SVG propio (≈ 4 KB) frente a Chart.js (+62 KB gzip) y Recharts (+122 KB gzip).
- ✅ Donut, barras (con referencia, mes resaltado y negativos), barras apiladas, líneas con área y anillo de progreso en `apps/web/src/components/charts/`.
- ✅ Accesibles (`role="img"` con resumen y una tabla de datos oculta para lectores de pantalla) y escalables con `viewBox`.

### OF-303 · Pantalla «Este mes» ✅
- ✅ Pantalla de inicio: gastado (frente al mes anterior y a la media), ahorrado y %, dónde más se va, donut con las 5 categorías principales, ritmo de gasto frente al mes anterior y lo que más ha cambiado frente a la media.
- Los presupuestos se añadirán con OF-401.

### OF-304 · Pantalla «¿En qué gastamos?» ✅
- ✅ Donut y ranking de categorías; al elegir una (o «sin categoría»): 12 meses frente a la media, comercios principales y movimientos del mes.

### OF-305 · Pantalla «Evolución» ✅
- ✅ Barras apiladas de 12 meses (6 categorías principales + resto), ahorro de cada mes con su media, ahorrado en el periodo y mejor y peor mes.

### Demostración
- ✅ `make demo` crea un hogar ficticio con 12 meses de datos para ver los gráficos sin datos reales. Es todo o nada y se niega en producción salvo con `--force`, porque la contraseña es pública.

---

## Fase 4 · Ahorro

### OF-401 · Presupuestos ✅
- ✅ Límite mensual por categoría (`GET /api/v1/budgets?month=`, `PUT/DELETE /api/v1/budgets/{category_id}`), con aviso al 85 % («cerca») y al pasarse («pasado»).
- ✅ 🧪 El porcentaje usa solo gastos de esa categoría y ese mes, de la conjunta y las huchas. Se redondea hacia abajo y el estado se decide con los importes exactos.
- ✅ «Este mes» muestra las barras de presupuesto. La línea de presupuesto total en el ritmo de gasto solo aparece si todo lo gastado tiene presupuesto.
- ✅ Pantalla **Presupuestos** (`#presupuestos`) con vuestra media de cada categoría y un botón para usarla, redondeada hacia arriba a decenas.

### OF-402 · Objetivos de ahorro ✅
- ✅ Nombre, icono, meta, ahorrado (a mano o el saldo de una hucha vinculada), aportación mensual y fecha límite opcional (`/api/v1/goals`).
- ✅ Proyección: progreso, meses que faltan, fecha estimada y, con fecha límite, lo que haría falta apartar al mes y si se llega a tiempo.
- ✅ Solo se pueden vincular huchas del propio hogar (nunca cuentas personales ni de otro hogar).

### OF-403 · Cargos recurrentes ✅
- ✅ Detecta cuotas: mismo comercio en al menos 3 meses (≥ 75 % del periodo), sin más de 2 cargos al mes, importe que se repite (±1 %) y activas en los últimos 45 días. Una cuota cobrada en dos veces cuenta como una.
- ✅ Importe y subidas de precio calculados con meses completos (el mes en curso solo confirma que sigue activa).
- ✅ 🧪 Detecta la subida de Netflix del conjunto de datos de prueba.

### OF-404 · Ideas de ahorro ✅
- ✅ Ideas deterministas, sin IA, cada una con su respaldo (movimientos y periodo) y la estimación en la que se basa:
  - cuotas que han subido de precio;
  - suscripciones;
  - restaurantes (−25 %), supermercado (−10 %) y suministros (−10 %).
- ✅ Medias solo con meses completos: se excluye el mes en curso y el primer mes importado si empieza a mitad de mes. Sin meses completos no se proyecta nada.

### OF-405 · Simulador de recortes ✅
- ✅ Deslizadores por categoría que calculan el ahorro extra al mes y al año (céntimos exactos con BigInt) y cuántos meses antes se alcanza el primer objetivo pendiente.

---

## Fase 5 · Uso real

### OF-501 · Exportación y copia de seguridad ✅
- ✅ `GET /api/v1/export?format=json|csv`: lo que ve quien la pide (nunca la cuenta personal de la otra persona, sesiones, hashes ni huellas), con `format_version` 1, importes exactos como texto y CSV protegidos frente a fórmulas. Botón **Exportar** en la cabecera.
- ✅ 🧪 Tests negativos de visibilidad: cuenta personal, reglas y patrones de salida de la pareja, y otro hogar.
- ✅ `make backup` y `make restore FILE=…` ([ADR-0016](../adr/0016-exposicion-y-copias.md)); restaurar aplica migraciones y cierra todas las sesiones (`openfinance sessions revoke-all`).
- ✅ 🧪 Restaurar una copia en una instalación limpia deja los mismos saldos (CI, `compose-e2e`).

### OF-502 · Instalación en casa ✅
- ✅ Docker Compose probado de principio a fin en CI en dos modos: `direct` (red local por http) y `caddy` (HTTPS con dominio propio). Ni PostgreSQL ni la API publican puertos.
- ✅ La IP real llega a la API sin que el cliente pueda falsificarla (nginx sobrescribe `X-Forwarded-For`); aviso en el log si la cookie `Secure` llega por http.
- ✅ Guía: [Instalar en casa](../deployment/home.md) (móvil en la red local, HTTPS, copias programadas y actualización).

### OF-503 · Móvil ✅ (falta probarlo en un móvil real)
- ✅ Las 6 pantallas, el acceso, Categorías y Presupuestos se usan en un móvil: pestañas en una fila desplazable, tablas en filas compactas, objetivos táctiles de al menos 40 px y campos de 16 px para que iOS no amplíe la página.
- ✅ Gráficos legibles en pantalla estrecha: se dibujan al ancho real (el texto no encoge con el `viewBox`) y escriben menos etiquetas cuando no caben. Siguen alimentándose de los agregados del Core.
- ✅ 🧪 Playwright (`apps/web/e2e`, `make e2e`) en Chrome a 360 px, Safari (WebKit) a 390 px y escritorio: sin scroll horizontal, gráficos dentro de la pantalla con etiquetas de al menos 11 px y sin solapes, pestañas alcanzables, Importar en 3 pasos con un extracto sintético y descarga de la exportación. En CI contra Docker Compose (`compose-e2e`, modo `direct`).

### OF-504 · Release v0.1 — preparado (falta la etiqueta tras el mes de uso real)
- ✅ Licencias de las dependencias auditadas ([docs/legal/dependencias.md](../legal/dependencias.md)): todas compatibles con AGPL-3.0; psycopg es LGPL-3.0-only y no plantea problemas. `make licenses` las lista y el job `licenses` de CI falla si una dependencia de producción sale de la lista permitida.
- ✅ `LICENSE` con el texto literal de la AGPL-3.0 y [ADR-0008](../adr/0008-licencia-agpl.md) aceptado: AGPL-3.0-or-later, contribuciones con DCO (`git commit -s`, [CONTRIBUTING.md](../../CONTRIBUTING.md)), sin CLA y sin cabeceras SPDX por fichero.
- ✅ [CHANGELOG.md](../../CHANGELOG.md) (Keep a Changelog) con las fases 0 a 5 y lo pendiente.
- ✅ Checklist de release: [docs/development/release.md](../development/release.md).
- Pendiente: subir las versiones a 0.1.0 y crear la etiqueta anotada `v0.1.0` con su release en GitHub, **después de un mes de uso real**. Decidido así a propósito.

---

## Fase 6 · Datos fiables

Que cualquier extracto real de Revolut o Bankinter se importe sin errores y sin inflar las entradas. Sale de la auditoría del 1 de noviembre de 2026 y **va antes del mes de uso real**.

### OF-601 · Filas de importe cero o vacío ✅
Una verificación de tarjeta a 0,00 € pasaba la vista previa, pero al confirmar el dominio la rechazaba y la API respondía 500: el extracto no se podía importar nunca.
- ✅ Los lectores de Revolut y Bankinter descartan las filas de importe cero («importe cero: no mueve dinero») y las de importe vacío («fila no válida: falta el importe»), con su motivo en la vista previa. El saldo sigue cuadrando.
- ✅ Si al confirmar el dominio rechaza una fila, la API responde 422 y no guarda nada: el lote no queda reclamado y se puede volver a confirmar.
- ✅ 🧪 Un extracto con una verificación de tarjeta a 0,00 se previsualiza y se confirma; 🧪 un error del dominio al confirmar da 422 y deja la importación intacta.

### OF-602 · Clasificación: huchas en los dos sentidos, nombres por palabra completa y traspasos internos ✅ (salvo traspasos internos)
- ✅ Patrones de hucha «To pocket» y «From pocket». Sacar de la hucha es `savings_transfer` positivo: no cuenta como ingreso, resta de lo traspasado al ahorro y en Movimientos se lee «De la hucha». Los textos en español siguen pendientes de un extracto real ([bancos.md](bancos.md)).
- ✅ Todos los patrones (nombres, patrones por persona, huchas) se buscan por palabra completa tras normalizar: «MARIANA» no es aportación de Ana y «\*1234» no reconoce «\*12345». Solo se exige frontera en el extremo que es letra o cifra, así que «REVOLUT\*\*» sigue reconociendo «Revolut\*\*9876\*».
- ⏳ `internal_patterns` con las recargas de la conjunta hacia las cuentas personales: **pendiente de ver el texto en un extracto real**. Inventarlo clasificaría mal movimientos reales que luego no se pueden reclasificar (hasta OF-701).
- ✅ 🧪 «From pocket EUR Viaje» no cuenta como entrada; ✅ 🧪 «Transferencia de MARIANA LOPEZ» no es aportación de Ana; ✅ 🧪 las huellas ya guardadas no cambian (la de la muestra queda fijada en el test y no depende de las reglas).

### OF-603 · Búsqueda con «#» y ErrorBoundary global ✅
- ✅ La clave de la consulta de Movimientos es `JSON.stringify([consulta, versión])`, sin partirla por «#». Antes, buscar «#1» lanzaba un `SyntaxError` y la lista se quedaba congelada.
- ✅ Un `ErrorBoundary` por pestaña en `App.tsx` muestra «Algo ha fallado · Recargar» en lugar de congelar la pantalla; la cabecera y las otras pestañas siguen funcionando.
- ✅ 🧪 Buscar «#1», «%», comillas o apóstrofos envía la búsqueda tal cual y la lista sigue funcionando; ✅ 🧪 una respuesta que rompe la pantalla muestra el aviso con «Recargar».

### OF-604 · Importes ambiguos: rechazar en vez de adivinar ✅
- ✅ `to_decimal` recibe el separador decimal del banco y el otro solo puede agrupar miles de tres en tres. El CSV de Revolut declara «.»; los Excel de Revolut y Bankinter traen números, y si una celda llega como texto solo se acepta lo inequívoco («12,30», «1.234,56»), porque su formato de texto no se ha visto en un extracto real.
- ✅ Lo que no sigue el formato («12,30» en el CSV inglés, «1,23,456», «1.5.») es una fila no válida con su motivo.
- ✅ 🧪 «1,234» en el CSV inglés se lee como 1234 y el saldo cuadra; ✅ 🧪 sin formato declarado, «1,234» y «1.234» se rechazan como «importe ambiguo», nunca se leen como 1,234.

### OF-605 · `useLoad` común con estados de carga, error y reintento ✅
- ✅ `useLoad` en `src/lib/useLoad.ts`, con `reload`: al recargar se siguen viendo los datos hasta que llegan los nuevos, y un error se quita al reintentar. Lo usan Este mes, ¿En qué gastamos? (y su panel), Evolución, Ahorrar y Presupuestos; Movimientos mantiene su carga propia (filas atenuadas mientras llega la nueva consulta) con el mismo «Reintentar».
- ✅ Componentes `<Loading/>` y `<ErrorState onRetry/>` en `src/components/LoadState.tsx`. `<UncategorizedNotice/>` no se ha extraído: el aviso solo aparece en Este mes.
- ✅ 🧪 Si fallan los movimientos de una categoría se ve el error con «Reintentar» y al reintentar se cargan; ✅ 🧪 Presupuestos se recupera al reintentar (antes el error se quedaba para siempre).

### OF-606 · CLI de mantenimiento: contraseña, cuentas y personas ✅
- ✅ `openfinance users set-password <email>`: la contraseña se pide sin eco (nunca como argumento), y se cierran solo las sesiones de esa persona.
- ✅ `openfinance accounts add <email> <nombre> [--kind savings|joint|personal] [--bank …] [--opening-balance …]`: añade una cuenta al hogar de esa persona; con `personal`, es su titular. El nombre no se puede repetir en el hogar.
- ✅ 🧪 Tras cambiar la contraseña, la sesión anterior da 401, la de la otra persona sigue abierta y la contraseña vieja ya no entra; ✅ 🧪 una cuenta personal nueva solo la ve su titular y no se puede dar a alguien de otro hogar.
- Guía: [Instalar en casa](../deployment/home.md).

### OF-607 · Purgar el contenido de importaciones caducadas ✅
- ✅ El archivo de una vista previa sin confirmar de más de 24 h se borra al arrancar la API, en cada inicio de sesión y en cada vista previa. `make backup` ejecuta `openfinance imports purge` antes de volcar. Si al arrancar la base de datos no responde, la API arranca igual y lo deja en el registro.
- ✅ 🧪 Una vista previa de más de 24 h no conserva su contenido tras el siguiente login (de cualquier persona del hogar); ✅ 🧪 una reciente sí; ✅ 🧪 el arranque y `imports purge` también la borran.

### OF-608 · El mes en curso en el Core
- `insights/trends` excluye el mes en curso de las medias y del mejor y peor mes (hoy Evolución y Este mes dan medias distintas).
- `insights/month` devuelve los cambios frente a la media calculados en el Core y prorrateados hasta el mismo día del mes (hoy los calcula el frontend contra meses completos).
- 🧪 Evolución y Este mes dan la misma media; 🧪 el día 1 ninguna categoría aparece muy por debajo de su media.

---

## Fase 7 · Corregir sin miedo

Que cualquier error de datos se arregle desde la web, quede trazado y se pueda deshacer. Se hace durante el mes de uso real; al terminarla se etiqueta `v0.1.0`.

| ID | Ticket | Tamaño |
| --- | --- | --- |
| OF-701 | Editar tipo, persona y nota de un movimiento, con historial de correcciones (`transaction_corrections`) | L |
| OF-702 | Reglas visibles: aviso con «Deshacer», pantalla Reglas (`GET/DELETE /api/v1/rules`), los Bizum no aprenden reglas | M |
| OF-703 | Historial de importaciones y deshacer una importación (anulación trazada, nunca borrado silencioso) | M |
| OF-704 | Ajustes: cambio de contraseña, cerrar sesiones, tarjetas de recarga desde la web (revisa ADR-0015) | M |
| OF-705 | Clasificar varios a la vez y movimientos de efectivo | M |
| OF-706 | Registro de cambios con deshacer y rehacer: base de reglas, fusiones, importaciones y asistente | L |

Cada ticket lleva sus tests negativos de privacidad (la pareja y otro hogar).

---

## Fase 8 · Uso diario (v0.2)

| ID | Ticket |
| --- | --- |
| OF-801 | Navegación adaptable (barra inferior en el móvil, carril en la tablet, barra lateral en el escritorio) y estado en la URL |
| OF-802 | «Este mes» honesto: previsión de cierre y cargos pendientes; las cuotas fijas no disparan «cerca» |
| OF-803 | Movimientos con paginación por cursor, total del filtro y actualización por fila |
| OF-804 | Accesibilidad (foco, `document.title`, errores junto al campo, contraste) y tests de pantalla con axe |
| OF-805 | Modo oscuro e instalable en el móvil (PWA) |
| OF-806 | Simulador con todas las categorías e ideas descartables |

## Fase 9 · Operación (v0.2)

| ID | Ticket |
| --- | --- |
| OF-901 | Copias cifradas con `age`, rotación y receta para guardarlas fuera del equipo |
| OF-902 | Imágenes por digest, actions por SHA, Renovate, `pip-audit`, `npm audit` y Trivy |
| OF-903 | nginx con `gzip`, `Cache-Control` y cabeceras; Compose endurecido y rotación de logs |
| OF-904 | Logging configurado, identificador de petición y `/ready` con base de datos |
| OF-905 | Saldos con `SUM` en SQL, un solo flush al confirmar y `repositories.py` partido por contexto |
| OF-906 | Limitador de login acotado y atómico; Argon2 fuera del threadpool común |
| OF-907 | Imágenes publicadas y firmadas; aviso de versión nueva |

---

## Después de v0.2

Inspirado en Wallet, Spendee, Fintonic y Actual Budget. Cada fase empieza con su ADR y se detalla en tickets al empezarla. Esfuerzo estimado para una persona a tiempo completo.

| Fase | Versión | Qué consigue | Tickets | Esfuerzo |
| --- | --- | --- | --- | --- |
| 10 · Libro contable completo | v0.3 | ADR-0017 (nuevo alcance), comercios con renombrar y fusionar, dividir movimientos, traspasos enlazados, conciliación, efectivo, tarjeta, préstamo e inversión, varias monedas (ADR-0018), etiquetas, notas y adjuntos | OF-1001 … OF-1008 | 8 semanas |
| 11 · Reglas e importación universal | v0.4 | Motor de reglas con condiciones, acciones y fases (ADR-0019), vista previa y aplicar a lo existente, OFX, QIF y CAMT.053, CSV de cualquier banco con perfiles | OF-1101 … OF-1105 | 5 semanas |
| 12 · Planificar | v0.5 | Pagos programados (ADR-0020), previsión de saldo, presupuestos con límites o sobres y arrastre (ADR-0021), plantillas, «hoy podéis gastar», objetivos v2 | OF-1201 … OF-1206 | 7 semanas |
| 13 · Alertas | v0.6 | Avisos deterministas (comisiones, duplicados, recibos que suben…), notificaciones Web Push o ntfy (ADR-0022), resumen semanal | OF-1301 … OF-1303 | 4 semanas |
| 14 · Conexión con el banco | v0.7 | Agregador PSD2 con cuenta propia (ADR-0023), sincronización por la misma tubería que la importación, consentimientos y conciliación automática | OF-1401 … OF-1404 | 6 semanas |
| 15 · Informes y patrimonio | v0.8 | Patrimonio neto, flujo de caja, informes a medida y exportación v2 | OF-1501 … OF-1504 | 4 semanas |
| 16 · Hogar ampliado | v0.9 | Más personas con roles mínimos (ADR-0002), reparto de gastos (ADR-0011), viajes y eventos | OF-1601 … OF-1603 | 5 semanas |
| 17 · Plataforma 1.0 | v1.0 | API con tokens, servidor MCP de lectura, asistente con aprobación (ADR-0004, ADR-0005), auditoría externa de seguridad | OF-1701 … OF-1705 | 6 semanas |

Fuera de alcance a propósito: nota financiera, préstamos, seguros y cuentas remuneradas (son negocio de intermediación) y cifrado de extremo a extremo (impediría calcular los agregados en el servidor; se cubre con disco y copias cifradas).
