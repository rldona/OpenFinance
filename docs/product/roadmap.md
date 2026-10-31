# Roadmap y backlog

Alcance: [ADR-0012 · Empezar por el hogar](../adr/0012-empezar-por-el-hogar.md). Referencia visual: [prototipo](prototypes/index.html).

Un ticket está terminado cuando cumple sus criterios de aceptación, tiene tests y `make check` está en verde. Los criterios marcados con 🧪 deben quedar como tests automáticos.

## Resumen

| Fase | Objetivo | Tickets | Estado |
| --- | --- | --- | --- |
| 0 · Base | Repositorio, CI, entorno y `Money` | OF-001 … OF-003 | ✅ Hecha |
| 1 · Datos | Meter los movimientos reales de la cuenta conjunta de Revolut | OF-101 … OF-106 | 🚧 En curso (OF-104) |
| 2 · Categorías | Que cada gasto tenga su categoría casi sin esfuerzo | OF-201 … OF-203 | Pendiente |
| 3 · Gráficos | Este mes, ¿En qué gastamos? y Evolución | OF-301 … OF-305 | Pendiente |
| 4 · Ahorro | Presupuestos, objetivos, ideas y simulador | OF-401 … OF-405 | Pendiente |
| 5 · Uso real | Instalado en casa, con copias de seguridad | OF-501 … OF-504 | Pendiente |

**Hito v0.1:** fin de la fase 5, con al menos un mes de uso real con vuestros datos.

---

## Fase 0 · Base ✅

| ID | Ticket | Estado |
| --- | --- | --- |
| OF-001 | Monorepo: `services/api` (FastAPI) y `apps/web` (React) con capas y `import-linter` | ✅ |
| OF-002 | Entorno: Docker Compose, `.env.example`, `Makefile` | ✅ (Compose sin probar: falta Docker en local; se prueba en OF-502) |
| OF-003 | CI: lint, tipos, tests, build y migraciones sobre PostgreSQL | ✅ |

---

## Fase 1 · Datos

### OF-101 · Hogar y personas
Un hogar (`Workspace`) con dos personas que inician sesión con email y contraseña.
- Comando para crear el hogar y las dos cuentas de usuario (`make bootstrap` o CLI), sin pantalla de registro pública.
- Sesión por cookie `HttpOnly`/`SameSite`; contraseñas con hash Argon2.
- Ambas personas tienen acceso completo; no hay roles.
- 🧪 Sin sesión, la API responde 401; con sesión, solo devuelve datos de su hogar.

### OF-102 · Cuentas
Cuenta conjunta de Revolut (obligatoria) y huchas o cuenta de ahorro (opcional), con banco, moneda y saldo inicial.
- 🧪 Saldo actual = saldo inicial + suma de movimientos, calculado con `Money`.

### OF-103 · Movimientos
Modelo y API de movimientos.
- Campos: cuenta, fecha y hora, fecha valor, concepto original, importe (`Money`, comisión incluida), tipo, categoría (opcional), persona (en aportaciones), tipo según el banco y archivo de origen.
- Tipos (`TransactionKind`, ya definido en `domain/imports`): `contribution` (aportación de una persona), `expense` (un importe positivo es una devolución y resta gasto), `income` (otros ingresos), `savings_transfer` (traspaso a hucha o ahorro), `internal_transfer`.
- `GET /api/v1/transactions?month=2026-10&q=…&uncategorized=true`.
- 🧪 Los traspasos y las transferencias internas no cuentan como gasto; las aportaciones cuentan como entrada; las devoluciones restan gasto.
- Depende de: OF-102.

### OF-104 · Lector del CSV de Revolut 🚧
Lectura del extracto de la cuenta conjunta de Revolut. Formato y decisiones en [bancos.md](bancos.md).
- ✅ Lector `parse_revolut_csv` con cabeceras en inglés y supuestas en español, solo `COMPLETED` y producto `Current`, comisión incluida en el importe.
- ✅ Los importes se leen como texto y se convierten a `Decimal`; nunca pasan por `float`.
- ✅ Propone el tipo: aportación por persona, traspaso a hucha, ingreso, gasto o devolución.
- ✅ Huella estable para deduplicar, sin fusionar filas idénticas del mismo archivo.
- ✅ Comprobación del saldo fila a fila para detectar movimientos que faltan.
- ⬜ Validar con un extracto real anonimizado y resolver los puntos «Por confirmar» de [bancos.md](bancos.md).
- ⬜ Guardar en la configuración del hogar los patrones de cada persona y de las huchas.

### OF-105 · Importación idempotente
Vista previa → confirmación, sin duplicados.
- Deduplicación por identificador del banco si existe; si no, por huella de (cuenta, fecha, importe, concepto normalizado, ordinal del día).
- `POST /imports` (vista previa) y `POST /imports/{id}/commit`.
- 🧪 Importar dos veces el mismo archivo no crea movimientos nuevos.
- 🧪 Dos cafés iguales el mismo día en el mismo archivo **no** se consideran duplicados.
- Depende de: OF-103, OF-104.

### OF-106 · Pantallas Movimientos e Importar
Versión real de las pantallas del prototipo.
- Lista por mes con búsqueda y filtro «sin categoría».
- Asistente de importación en 3 pasos: subir, revisar (nuevos y duplicados) y listo.
- Cliente de API tipado a partir de OpenAPI (ADR-0009).
- Depende de: OF-103, OF-105.

---

## Fase 2 · Categorías

### OF-201 · Categorías
Las 13 categorías del prototipo vienen de serie, con icono y color, y se pueden renombrar, crear y ocultar.
- 🧪 Ocultar una categoría no borra sus movimientos.

### OF-202 · Reglas por comercio
- Normalización del comercio a partir del concepto: quita prefijos como «COMPRA TARJETA 4821» y los números de terminal.
- Al corregir la categoría de un movimiento se crea o actualiza una regla «comercio → categoría».
- Las reglas se aplican en la vista previa de importación y a los movimientos sin categoría del mismo comercio.
- 🧪 Corregir «MERCADONA 1234» clasifica también «MERCADONA 0087».
- Depende de: OF-201, OF-105.

### OF-203 · Corrección en la tabla
- Selector de categoría en cada fila, aviso «N movimientos sin categoría» y contador en la pestaña.
- Depende de: OF-202, OF-106.

---

## Fase 3 · Gráficos

### OF-301 · API de agregados (`insights`)
El Core calcula y el frontend solo pinta.
- Gasto y entradas por mes, gasto por categoría y mes, gasto acumulado por día, media de los meses anteriores y comercios principales por categoría.
- 🧪 Las sumas por categoría cuadran con la suma total del mes.
- 🧪 Los traspasos a ahorro quedan excluidos del gasto.
- Depende de: OF-103, OF-201.

### OF-302 · Componentes de gráficos
- Decidir entre el SVG propio del prototipo (`charts.js`) y una librería, y registrarlo en un ADR. Criterios: peso, accesibilidad, uso en móvil y mantenimiento.
- Componentes necesarios: donut, barras con línea de referencia, barras apiladas, líneas con área y anillo de progreso.

### OF-303 · Pantalla «Este mes»
- 3 indicadores principales (gastado, ahorrado, categoría principal), donut, ritmo de gasto frente al mes anterior y al presupuesto, cambios frente a la media y selector de mes.
- Depende de: OF-301, OF-302 (presupuestos con OF-401; hasta entonces se ocultan).

### OF-304 · Pantalla «¿En qué gastamos?»
- Donut con ranking de categorías y, al elegir una, sus 12 meses frente a la media, sus comercios y sus movimientos.
- Depende de: OF-301, OF-302.

### OF-305 · Pantalla «Evolución»
- Barras apiladas de 12 meses, ahorro de cada mes, ahorro acumulado y mejor y peor mes.
- Depende de: OF-301, OF-302.

---

## Fase 4 · Ahorro

### OF-401 · Presupuestos
Límite mensual por categoría, con avisos al 85 % y al 100 %.
- 🧪 El porcentaje consumido usa solo gastos de esa categoría y ese mes.

### OF-402 · Objetivos de ahorro
Nombre, meta, ahorrado y aportación mensual; calcula la fecha estimada.
- Lo ahorrado puede ir ligado al saldo de la cuenta de ahorro o introducirse a mano.

### OF-403 · Cargos recurrentes
- Detección de suscripciones y cuotas (mismo comercio, periodicidad mensual e importe estable) y de sus subidas de precio.
- 🧪 Detecta la subida de Netflix del conjunto de datos de prueba.

### OF-404 · Ideas de ahorro
Ideas deterministas, sin IA, cada una con la cifra que la respalda (movimientos y periodo).
- Primeras ideas: suscripciones, restaurantes, frecuencia de compra en el supermercado y variación de la luz.
- Los porcentajes de mejora son configurables y se muestran como estimación.
- Depende de: OF-301, OF-403.

### OF-405 · Simulador de recortes
- Deslizadores por categoría que calculan el ahorro extra al mes y al año y cuánto se adelanta la fecha del objetivo.
- Depende de: OF-301, OF-402.

---

## Fase 5 · Uso real

### OF-501 · Exportación y copia de seguridad
- Exportación completa en CSV y JSON, y copia de seguridad y restauración de PostgreSQL con un comando.
- 🧪 Restaurar una copia en una instalación limpia deja los mismos saldos.

### OF-502 · Instalación en casa
- Docker Compose probado de principio a fin, con guía para un equipo de casa o una NAS.
- Acceso desde el móvil en la red local; HTTPS si se expone fuera de casa.

### OF-503 · Móvil
- Las 6 pantallas se pueden usar en un móvil, con los gráficos legibles en pantalla estrecha.

### OF-504 · Release v0.1
- Revisión de licencias de las dependencias, fichero `LICENSE` (ADR-0008), `CHANGELOG` y etiqueta `v0.1.0`.

---

## Después de v0.1

Ideas que se retoman cuando v0.1 esté en uso; cada una tiene su ADR aplazado.

| Idea | Referencia |
| --- | --- |
| Más cuentas (tarjetas) y conciliación de saldos | — |
| Cuentas personales de Bankinter (lector de su Excel y un perfil por persona) | [bancos.md](bancos.md) |
| Conexión automática con el banco (Open Banking) | — |
| Asistente con IA que explica los gráficos y propone cambios con aprobación | ADR-0004, ADR-0005 |
| Perfiles compartidos y reparto de gastos | ADR-0011 |
| Módulos y extensiones | ADR-0006 |
