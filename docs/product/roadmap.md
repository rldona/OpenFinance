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
| 6 · Datos fiables | Que cualquier extracto real se importe sin errores ni entradas infladas | OF-601 … OF-608 | ✅ Hecha · falta reconocer los traspasos internos de OF-602 (pendiente de un extracto real) |
| 7 · Corregir sin miedo | Editar, deshacer y ajustar desde la web, con historial | OF-701 … OF-706 | ✅ Hecha (falta probarla en el mes de uso real) |
| 8 · Uso diario | Móvil, PWA, accesibilidad y mes en curso honesto (v0.2) | OF-801 … OF-806 | ✅ Hecha (falta probarla en un móvil real y pasar `make e2e`) |
| 9 · Operación | Copias cifradas, dependencias y actualizaciones (v0.2) | OF-901 … OF-907 | ✅ |
| 10 – 17 | Del libro contable completo a la 1.0 | OF-1001 … OF-1705 | Ver [Después de v0.2](#después-de-v02) |

**Hito v0.1:** fases 6 y 7 terminadas y al menos un mes de uso real con vuestros datos. La auditoría del 1 de noviembre de 2026 encontró fallos que, con datos reales, dejan importaciones que no se pueden confirmar o totales inflados que no se pueden corregir; por eso la fase 6 va antes del mes de uso real.

## Cómo retomar

Estado a 1 de noviembre de 2026. Código en [github.com/rldona/OpenFinance](https://github.com/rldona/OpenFinance) (público, rama `main`). CI en verde en todos sus jobs: `backend`, `frontend`, `licenses` y `compose-e2e` en los modos `direct` y `https`.

### Lo que falta para v0.1, en orden

0. ✅ **Fases 6 y 7 hechas.** Solo falta reconocer los traspasos internos de OF-602, que necesitan ver su texto en un extracto real: se puede cerrar con el primer extracto del paso 1. Lo que salga del mes de uso real se corrige ya desde la web, con historial y deshacer.
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

### OF-608 · El mes en curso en el Core ✅
- ✅ `insights/trends` toma las medias de meses completos: si el periodo llega al mes en curso, de los 12 meses anteriores a él, igual que Este mes. El mes en curso cuenta en los totales, pero no en las medias ni en el mejor o peor mes, y se marca con `is_partial`.
- ✅ `insights/month` devuelve para cada categoría su `reference` (la media o, en el mes en curso, la media de lo gastado hasta el mismo día) y su `change`, y la lista `changes` con las que más cambian (máx. 4, sin importes de menos de 20 €). El frontend ya no lo calcula.
- ✅ 🧪 Evolución y Este mes dan la misma media; ✅ 🧪 el día 1 ninguna categoría aparece por debajo de su media; ✅ 🧪 el mejor y el peor mes no incluyen el mes en curso; ✅ 🧪 un mes pasado mantiene su ventana de 12 meses.

---

## Fase 7 · Corregir sin miedo

Que cualquier error de datos se arregle desde la web, quede trazado y se pueda deshacer. Se hace durante el mes de uso real; al terminarla se etiqueta `v0.1.0`. Cada ticket lleva sus tests negativos de privacidad (la pareja y otro hogar).

**Decisión de diseño ([ADR-0017](../adr/0017-registro-de-cambios.md)):** el registro general de OF-706 se construye primero y OF-701 lo usa desde el principio, en lugar de crear `transaction_corrections` y migrarlo después. Nada se borra: anular un movimiento es `voided = true`, con su entrada en el registro.

### Base del registro de cambios (de OF-706) ✅
- ✅ Tablas `change_operations` (autor, fecha, tipo, resumen, deshecha) y `change_entries` (entidad, campo, antes y después en JSON). Migración `0007_change_log`, que añade también `note` y `voided` a los movimientos.
- ✅ Todas las consultas de movimientos ignoran los anulados: listados, totales, gráficos, saldos, huellas y exportación.
- ✅ `POST /api/v1/changes/{id}/undo` y `/redo`: solo las operaciones propias (las de la pareja dan 404). Deshacer pone el valor anterior solo donde el actual sigue siendo el que dejó la operación; lo que alguien cambió después se respeta y la respuesta dice quién fue.
- ✅ 🧪 Propiedad: para 12 secuencias aleatorias de correcciones de las dos personas, deshacer todas en orden inverso devuelve el estado inicial.

### OF-701 · Editar tipo, persona y nota de un movimiento, con historial ✅
- ✅ `PATCH /api/v1/transactions/{id}` acepta `kind`, `member_id`, `note` y `category_id` (solo cambia lo que se envía), con las invariantes del dominio: persona solo en aportaciones y del mismo hogar, categoría solo en gastos. Un movimiento que deja de ser gasto pierde su categoría, y el cambio queda registrado.
- ✅ El importe, la fecha, el concepto y la huella nunca cambian.
- ✅ `GET /api/v1/transactions/{id}/history`: quién, cuándo y qué («Bizum de E M: Ingreso → Aportación de Elena»).
- ✅ En Movimientos, el concepto abre el detalle: tipo, persona, nota e historial. Cada corrección avisa con «Deshacer» durante 8 s.
- ✅ 🧪 La pareja no puede editar ni ver el historial de una cuenta personal ajena (404), ni otro hogar; ✅ 🧪 corregir un ingreso a aportación cambia las entradas del mes; ✅ 🧪 cada corrección deja una fila de historial con su autor.

### OF-702 · Reglas visibles: confirmar, deshacer y gestionar ✅
- ✅ Al categorizar, el aviso dice cuántos movimientos ha clasificado la regla y lleva «Deshacer» durante 8 s: revierte la categoría, la regla y lo que clasificó (es una sola operación del registro).
- ✅ Los Bizum y las transferencias a o de personas (por concepto o por tipo del banco) no aprenden reglas: su «comercio» es el nombre de alguien.
- ✅ Pantalla Reglas (`#reglas`, enlazada desde Movimientos y Categorías; `GET /api/v1/rules`, `DELETE /api/v1/rules/{household|personal}/{comercio}`): comercio, categoría, cuántos movimientos coinciden y si es personal. Borrar no cambia lo ya clasificado, queda en el registro y se puede deshacer.
- ✅ 🧪 Deshacer devuelve a «sin categoría» solo los movimientos que la regla había clasificado (los corregidos después a mano se respetan); ✅ 🧪 la pareja no ve ni borra las reglas personales del otro, ni otro hogar.

### OF-703 · Historial de importaciones y deshacer una importación ✅
- ✅ En Importar, la lista de importaciones (`GET /api/v1/imports`): archivo, cuenta, quién, cuándo, nuevos, ya importados y descartados, y si está deshecha. Solo de las cuentas que ve cada persona.
- ✅ «Deshacer» con confirmación en la propia pantalla (`POST /api/v1/imports/{id}/undo`): anula sus movimientos, con sus correcciones, en una operación del registro que también se puede deshacer. Solo la última importación confirmada de cada cuenta.
- ✅ Volver a importar un archivo deshecho reactiva los mismos movimientos (mismo identificador y correcciones) en lugar de duplicarlos.
- No se guarda si el saldo cuadró al confirmar: la vista previa lo comprueba, pero el historial no lo enseña todavía.
- ✅ 🧪 Deshacer y volver a importar el mismo archivo da el mismo resultado (mismos nuevos, mismos duplicados, mismos movimientos); ✅ 🧪 no se puede deshacer una importación de la cuenta personal de la pareja (404) ni de otro hogar, ni verla en la lista.

### OF-704 · Ajustes: cuenta propia, sesiones y recargas de la conjunta ✅
- ✅ Pantalla Ajustes (⚙️ en la cabecera, `#ajustes`). Cambiar la contraseña pide la actual (`POST /api/v1/me/password`); una actual incorrecta da 422 y no 401 (un 401 cerraría la sesión en la web) y cuenta para el límite de intentos.
- ✅ «Cerrar sesión en los demás dispositivos» (`POST /api/v1/me/sessions/revoke-others`). Cambiar la contraseña también las cierra; la sesión de este navegador sigue abierta. Se cierran las demás y no todas para no echar a quien lo pulsa: para salir ya está «Salir».
- ✅ «Recargas de la conjunta»: cada persona guarda y quita sus `*NNNN` (`GET/POST/DELETE /api/v1/me/patterns`); [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md) actualizada. Al importar en la conjunta de Revolut, la vista previa dice quién no tiene tarjeta guardada y no deja confirmar sin marcar «Importar igualmente».
- ✅ Entradas a Categorías, Presupuestos y Reglas desde Ajustes.
- ✅ 🧪 Cambiar la contraseña revoca las demás sesiones de esa persona (no las de la pareja) y la nueva entra; ✅ 🧪 una persona no ve ni borra los patrones de la otra, ni otro hogar; ✅ 🧪 intentos repetidos con una contraseña actual incorrecta dan 429.

### OF-705 · Clasificar varios a la vez y movimientos de efectivo ✅
- ✅ En «Solo sin categoría», casillas para elegir varios gastos y «Poner categoría» (`POST /api/v1/transactions/categorize`): sin aprender reglas y como una sola operación, que «Deshacer» revierte entera. Si alguno no se puede ver, no se toca ninguno (404).
- ✅ «+ Añadir a mano» (`POST /api/v1/transactions`): gasto o ingreso con fecha, concepto, importe positivo (el tipo da el signo), cuenta y categoría, con procedencia `manual`. Se propone una cuenta de «otra entidad»; en una cuenta del banco avisa de que su saldo dejará de cuadrar con el extracto. Hasta la fase 10 no hay cuentas de efectivo propias: se crean con `openfinance accounts add … --bank other`.
- ✅ «Borrar» en el detalle de un movimiento manual (`DELETE /api/v1/transactions/{id}`): queda anulado y en el registro, y se puede deshacer. Los importados no se borran (422): se deshace su importación (OF-703).
- ✅ 🧪 Un movimiento manual cuenta en los totales y al borrarlo deja de contar (ni en listados ni en la exportación), con su alta y su baja en el historial; ✅ 🧪 los importados no se borran; ✅ 🧪 la pareja no añade ni borra en la cuenta personal del otro, ni otro hogar.

### OF-706 · Registro de cambios con deshacer y rehacer ✅
- ✅ Sobre la base de arriba: correcciones, reglas, clasificar varios, movimientos manuales e importaciones escriben en el registro, y todo se deshace con la misma regla.
- ✅ Pantalla «Mis cambios» (`#cambios`, desde Ajustes y Movimientos): tus últimas 50 operaciones con «Deshacer» o «Rehacer».
- ✅ Los resúmenes se guardan sin recuentos y se cuentan al leerlos sobre lo que ve quien lee: una regla del hogar que aprende la pareja también clasifica sus cuentas personales, y contarlas en el historial de la conjunta revelaría cuántos movimientos tiene allí.
- ✅ 🧪 Deshacer no expone datos de una cuenta personal ajena: ni identificadores ni recuentos en el historial, y el resultado de deshacer solo dice quién cambió algo después, no qué puso; ✅ 🧪 cada persona solo lista sus operaciones, de la más reciente a la más antigua.

--- | --- | --- |
| OF-701 | Editar tipo, persona y nota de un movimiento, con historial de correcciones (`transaction_corrections`) | L |
| OF-702 | Reglas visibles: aviso con «Deshacer», pantalla Reglas (`GET/DELETE /api/v1/rules`), los Bizum no aprenden reglas | M |
| OF-703 | Historial de importaciones y deshacer una importación (anulación trazada, nunca borrado silencioso) | M |
| OF-704 | Ajustes: cambio de contraseña, cerrar sesiones, tarjetas de recarga desde la web (revisa ADR-0015) | M |
| OF-705 | Clasificar varios a la vez y movimientos de efectivo | M |
| OF-706 | Registro de cambios con deshacer y rehacer: base de reglas, fusiones, importaciones y asistente | L |

Cada ticket lleva sus tests negativos de privacidad (la pareja y otro hogar).

---

## Fase 8 · Uso diario (v0.2) ✅

Que la web se use cada día desde el móvil, el portátil o la tableta, sin sorpresas en los números del mes en curso. Sin ADR nuevo: cambia la presentación y añade lo mínimo en la API.

### OF-801 · Navegación adaptable y estado en la URL ✅
- ✅ Barra inferior en el móvil (< 640 px), carril a la izquierda en la tableta (640–1023 px) y barra lateral con los nombres completos en el escritorio. La cabecera conserva el nombre del hogar, Exportar, Ajustes y Salir. El aviso (toast) sube para no quedar detrás de la barra inferior.
- ✅ El mes, «Hogar / Mío», la categoría elegida y los filtros de Movimientos (`q`, `cuenta`, `sin`, `todos`) viven en el hash de la URL (`#movimientos?mes=2026-09&q=luz`): se comparten con un enlace y sobreviven a recargar. Cambiar de filtro no añade entradas al historial. El menú arrastra el mes y la vista al cambiar de pantalla.
- ✅ 🧪 Los filtros se leen y se escriben en la URL; un mes inválido se ignora; el menú conserva el mes; la pantalla actual lleva `aria-current`.
- Pendiente de comprobar en un móvil real: `make e2e` (el test de objetivos táctiles ahora mide `.nav a`).

### OF-802 · «Este mes» honesto ✅
- ✅ `GET /api/v1/insights/month` añade `forecast` (gasto con el que cerraría el mes en curso) y `pending_charges` (cuotas habituales que aún no han llegado, con su día habitual; las que ya tocaban y no han llegado van como `late` y no se suman). Previsión = lo gastado + cuotas por llegar + ritmo diario del gasto variable (sin las cuotas ya cobradas) × días que quedan. Sin previsión antes del día 7 ni en meses cerrados.
- ✅ Presupuestos: las cuotas fijas (cobradas o por cobrar) no disparan «cerca»; el aviso mira solo el margen que dejan para el gasto variable, y «pasado» sigue siendo siempre. `BudgetOut.fixed` lo enseña («120 € son cuotas fijas»).
- ✅ 🧪 Previsión y pendientes con cuotas pagadas, por llegar y retrasadas; mes cerrado y pocos días sin previsión; la vista «Mío» no lista las cuotas de la pareja y otro hogar no se cuela; las cuotas fijas solas no dicen «cerca» pero el gasto variable sí y pasarse siempre avisa.

### OF-803 · Movimientos con paginación por cursor ✅
- ✅ `GET /api/v1/transactions/page`: 50 por página (hasta 200), cursor opaco (fecha + identificador, estable con empates), y en cada página `count` y `total` de todo el filtro. El listado simple `GET /api/v1/transactions` sigue para los gráficos.
- ✅ En Movimientos, «Cargar más», «Mostrando 50 de 70 movimientos» y «Suma del filtro». Cambiar un filtro vuelve a la primera página. Cambiar una categoría actualiza solo esa fila (se vuelve a pedir la lista solo si la regla ha clasificado más movimientos o la fila deja de cumplir el filtro). Desaparece el tope de 1000 movimientos.
- ✅ 🧪 Recorrer el cursor devuelve cada movimiento una vez y en el mismo orden que el listado; el total no cambia entre páginas ni cuenta los anulados; la cuenta personal de la pareja no entra en páginas ni totales (ni con un cursor ajeno ni pidiendo su `account_id`, 404); otro hogar no ve nada; cursor y límite inválidos dan 422.

### OF-804 · Accesibilidad ✅
- ✅ `document.title` por pantalla («Movimientos · OpenFinance»), enlace «Saltar al contenido», el foco pasa al contenido al cambiar de pantalla y anillo de foco visible.
- ✅ Errores junto al campo (`aria-invalid` + `aria-describedby`, y el foco vuelve al campo): acceso, contraseña actual incorrecta, importe de «Añadir a mano» y presupuestos (se conserva lo escrito).
- ✅ 🧪 axe-core (WCAG 2.1 A/AA) sin violaciones en las once pantallas y en el acceso. El contraste no se puede medir en jsdom: un test calcula la razón de cada par de colores de `index.css` en los tres temas (mínimo 4,5:1). Subió el fondo de las etiquetas verde y naranja, que quedaban en 4,3:1.
- axe-core es MPL-2.0 y solo de desarrollo ([dependencias](../legal/dependencias.md)).

### OF-805 · Modo oscuro e instalable en el móvil ✅
- ✅ Tema oscuro por tokens de color: sigue al sistema y en Ajustes → Apariencia se fuerza «Claro» u «Oscuro» (se recuerda en el navegador; si no deja guardar, vale para la visita).
- ✅ PWA: `manifest.webmanifest`, iconos propios (192, 512, maskable y de iOS; sustituyen el logotipo por defecto de Vite) y un service worker mínimo que guarda solo la carcasa de la app. Nunca toca `/api/` ni `/health`. Se registra solo en producción y con HTTPS.
- ✅ 🧪 Elegir y recordar el tema; manifiesto con iconos existentes; `index.html` enlaza manifiesto, color y icono; el service worker excluye la API.
- Sin acceso a datos sin conexión: sin red se abre la carcasa con el aviso de que no hay conexión.

### OF-806 · Simulador con todas las categorías e ideas descartables ✅
- ✅ El simulador ofrece todas las categorías con gasto (antes seis fijas), de mayor a menor media: se ven seis y «Mostrar las N restantes»; el total cuenta también las plegadas.
- ✅ «Descartar» una idea la esconde para todo el hogar (`PUT/DELETE /api/v1/savings/ideas/{id}/dismissed`, migración `0008_dismissed_ideas`); «Ver N ideas descartadas» y «Recuperar». Solo valen ideas que existen (404 si no).
- ✅ 🧪 Descartar y recuperar es idempotente y se ve igual desde la pareja; ideas inventadas dan 404; otro hogar no se ve afectado; sin sesión no se puede.

## Fase 9 · Operación (v0.2) ✅

| ID | Ticket |
| 

Notas de la implementación (sin probar en un equipo con Docker; lo comprueban los jobs `security`, `scripts` y `compose-e2e` de CI):

- OF-901: `make backup` exige `OPENFINANCE_BACKUP_RECIPIENT`; se prueba con `make scripts-test` (docker y age simulados).
- OF-902: Trivy y `pip-audit` pueden fallar con vulnerabilidades que ya existan en las dependencias: se corrigen o se justifican en `.trivyignore`.
- OF-903: `deploy/scripts/ci/headers.sh` comprueba cabeceras, caché y gzip contra una instalación real.
- OF-905: `repositories.py` ahora es un paquete con un módulo por contexto.
- OF-906: el cambio de contraseña también usa el limitador nuevo, pero su Argon2 sigue en el grupo de hilos común (solo para personas con sesión).
- OF-907: la consulta de versión es opt-in por privacidad; la firma de las imágenes solo se ve en la primera etiqueta publicada.

--- | --- |
| OF-901 | Copias cifradas con `age`, rotación y receta para guardarlas fuera del equipo |
| OF-902 | Imágenes por digest, actions por SHA, Renovate, `pip-audit`, `npm audit` y Trivy |
| OF-903 | nginx con `gzip`, `Cache-Control` y cabeceras; Compose endurecido y rotación de logs |
| OF-904 | Logging configurado, identificador de petición y `/ready` con base de datos |
| OF-905 | Saldos con `SUM` en SQL, un solo flush al confirmar y `repositories.py` partido por contexto |
| OF-906 | Limitador de login acotado y atómico; Argon2 fuera del threadpool común |
| OF-907 | Imágenes publicadas y firmadas; aviso de versión nueva |

---

## Fase 10 · Libro contable completo (v0.3) ✅

Hecha (sin probar en un equipo con Docker: lo comprueba `compose-e2e`). Alcance en [ADR-0018](../adr/0018-libro-contable-completo.md) y [ADR-0019](../adr/0019-varias-monedas.md), ambos aceptados el 1 de noviembre de 2026. Cada ticket lleva su migración, su cambio de OpenAPI (`make openapi`), tests de privacidad negativos y registro de cambios con deshacer.

| ID | Ticket | Criterio de hecho |
| --- | --- | --- |
| OF-1001 ✅ | Comercios: entidad con variantes del banco, renombrar y fusionar | Fusionar dos comercios reclasifica sus movimientos y se deshace; el nombre visible sale en listados e informes |
| OF-1002 ✅ | Etiquetas y notas largas en movimientos | Filtrar por etiqueta; las etiquetas son del hogar y heredan la visibilidad del movimiento |
| OF-1003 ✅ | Dividir un movimiento en partes con categoría | La suma de las partes es el importe original; los informes usan las partes (test de propiedades: dividir no cambia el total) |
| OF-1004 ✅ | Traspasos enlazados entre cuentas propias | Los dos lados se enlazan y ninguno cuenta como gasto ni ingreso; enlazar y desenlazar se deshace |
| OF-1005 ✅ | Tipos de cuenta: efectivo, tarjeta, préstamo e inversión | El saldo de `card` y `loan` resta; no entran en gasto ni presupuestos; migración sin tocar cuentas existentes |
| OF-1006 ✅ | Conciliación: revisado y saldo contra el del banco en una fecha | Un movimiento revisado no cambia con una importación; la diferencia de saldo se muestra |
| OF-1007 ✅ | Adjuntos (ticket, factura) en un movimiento | En disco, con la privacidad del movimiento, en la copia de seguridad y con límite de tamaño y tipo |
| OF-1008 ✅ | Varias monedas con tipos de cambio manuales (ADR-0019) | Sin tasa, el movimiento no se convierte y el informe lo dice; un hogar de una moneda no cambia |

---

## Después de v0.2

Inspirado en Wallet, Spendee, Fintonic y Actual Budget. Cada fase empieza con su ADR y se detalla en tickets al empezarla. Esfuerzo estimado para una persona a tiempo completo.

| Fase | Versión | Qué consigue | Tickets | Esfuerzo |
| --- | --- | --- | --- | --- |
| 10 · Libro contable completo | v0.3 | Hecha: [Fase 10](#fase-10--libro-contable-completo-v03) | OF-1001 … OF-1008 | ✅ |
| 11 · Reglas e importación universal | v0.4 | Motor de reglas con condiciones, acciones y fases (ADR-0020), vista previa y aplicar a lo existente, OFX, QIF y CAMT.053, CSV de cualquier banco con perfiles | OF-1101 … OF-1105 | 5 semanas |
| 12 · Planificar | v0.5 | Pagos programados (ADR-0021), previsión de saldo, presupuestos con límites o sobres y arrastre (ADR-0022), plantillas, «hoy podéis gastar», objetivos v2 | OF-1201 … OF-1206 | 7 semanas |
| 13 · Alertas | v0.6 | Avisos deterministas (comisiones, duplicados, recibos que suben…), notificaciones Web Push o ntfy (ADR-0023), resumen semanal | OF-1301 … OF-1303 | 4 semanas |
| 14 · Conexión con el banco | v0.7 | Agregador PSD2 con cuenta propia (ADR-0024), sincronización por la misma tubería que la importación, consentimientos y conciliación automática | OF-1401 … OF-1404 | 6 semanas |
| 15 · Informes y patrimonio | v0.8 | Patrimonio neto, flujo de caja, informes a medida y exportación v2 | OF-1501 … OF-1504 | 4 semanas |
| 16 · Hogar ampliado | v0.9 | Más personas con roles mínimos (ADR-0002), reparto de gastos (ADR-0011), viajes y eventos | OF-1601 … OF-1603 | 5 semanas |
| 17 · Plataforma 1.0 | v1.0 | API con tokens, servidor MCP de lectura, asistente con aprobación (ADR-0004, ADR-0005), auditoría externa de seguridad | OF-1701 … OF-1705 | 6 semanas |

Fuera de alcance a propósito: nota financiera, préstamos, seguros y cuentas remuneradas (son negocio de intermediación) y cifrado de extremo a extremo (impediría calcular los agregados en el servidor; se cubre con disco y copias cifradas).
