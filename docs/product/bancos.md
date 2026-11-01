# Bancos del hogar

| Cuenta | Banco | En v0.1 | Cómo entra |
| --- | --- | --- | --- |
| Cuenta conjunta (gastos de casa) | **Revolut** | ✅ Sí | Extracto en Excel (.xlsx) o CSV |
| Huchas de la cuenta conjunta | **Revolut** | Como traspaso a ahorro | Se detectan en el mismo extracto |
| Cuentas personales de cada uno | **Bankinter** | ✅ Sí, privadas para su titular ([ADR-0013](../adr/0013-cuentas-personales-privadas.md)) | Movimientos en Excel (.xlsx) |

Decisiones: [ADR-0015](../adr/0015-patrones-por-persona-y-xlsx.md). Los extractos reales se validaron con `openfinance statement-check` (solo recuentos); ninguno se ha copiado al repositorio.

## Revolut · cuenta conjunta

**Cómo descargarlo:** app de Revolut → cuenta → *Extracto* → formato *Excel* → periodo.

Hay dos formatos y se detectan solos:

- **Excel (.xlsx)**, el que da la app en español. Validado con un extracto real.
- **CSV**, con cabeceras en inglés (formato público, el de la configuración de importación de Firefly III para Revolut).

> ⚠️ Usad siempre el mismo formato para la misma cuenta. Los conceptos cambian entre el CSV en inglés y el Excel en español («Payment from…» frente a «Transferencia de…») y la huella depende del concepto: mezclar formatos podría duplicar movimientos.

| Excel (español) | CSV (inglés) | Uso en OpenFinance |
| --- | --- | --- |
| `Tipo` | `Type` | Procedencia. Vistos: «Pago con tarjeta», «Transferir», «Recargas». `CARD_REFUND`/`REFUND`, o un pago con tarjeta con importe positivo, son devoluciones: gasto con importe positivo |
| `Producto` | `Product` | Solo se importa `Actual` / `Current`. Las filas de huchas (`Savings`) se omiten porque el traspaso ya aparece en la cuenta |
| `Fecha de inicio` | `Started Date` | Fecha y hora del movimiento. En Excel es una fecha de Excel con fracciones de segundo: se redondea al segundo |
| `Fecha de finalización` | `Completed Date` | Fecha valor. Vacía en los pendientes |
| `Descripción` | `Description` | Concepto: comercio, «Transferencia de …», «Recarga de \*NNNN», «To pocket …» |
| `Importe` | `Amount` | Importe con signo. En Excel es un número con 2 decimales como máximo; se convierte a `Decimal` sin operar con `float` |
| `Comisión` | `Fee` | Comisión aparte: el efecto en la cuenta es `Importe − Comisión` |
| `Divisa` | `Currency` | Moneda del movimiento |
| `State` | `State` | Solo `COMPLETADO` / `COMPLETED`. Los pendientes se importarán cuando se completen; revertidos, rechazados y fallidos se descartan |
| `Saldo` | `Balance` | Saldo tras el movimiento: se usa para comprobar que no faltan filas. Vacío en los pendientes |

Notas del Excel real:

- Algunas cabeceras llegan con la codificación rota (`DescripciÃ³n`, `ComisiÃ³n`); en el Excel se reparan (cabeceras y conceptos). Se aceptan también bien escritas. El CSV se lee tal cual, sin reparar, para no cambiar sus huellas.
- Las filas pendientes son más cortas: no traen fecha de finalización ni saldo.
- El archivo va ordenado por **fecha de finalización**, y en ese orden cuadra el saldo. No se reordena por fecha de inicio.
- Algunos conceptos traen `?` en lugar de caracteres que Revolut no ha sabido exportar. No se pueden recuperar y se guardan tal cual.

**Duplicados:** Revolut no da un identificador por movimiento. La huella combina cuenta, fecha y hora al segundo, importe, concepto normalizado y orden de aparición de filas idénticas en el archivo. El mismo extracto en CSV y en Excel con los mismos conceptos da las mismas huellas.

**Clasificación automática:**

- Entradas con el nombre de una persona (nombre completo o primer nombre, sin tildes; p. ej. «Transferencia de RAUL …») → **aportación** de esa persona.
- Entradas que coinciden con un patrón de entrada guardado para una persona (p. ej. «Recarga de \*1234», con los últimos dígitos de su tarjeta) → **aportación** de esa persona. Ver «Patrones por persona».
- «To pocket …» → **traspaso a ahorro**.
- Otras entradas (Bizum recibidos, intereses) → **ingreso**.
- El resto → **gasto**, pendiente de categoría.

### Por confirmar

- [x] Cabeceras exactas: en español en el Excel (ver tabla), en inglés en el CSV.
- [x] Valor de `Producto` en la cuenta conjunta: `Actual`.
- [x] Texto de las aportaciones: «Transferencia de NOMBRE APELLIDOS» y «Recarga de \*NNNN».
- [ ] Si la hora está en hora local o en UTC: decide en qué día cae un pago de madrugada.
- [ ] Signo de `Comisión` y si `Saldo` ya la descuenta: en la muestra todas las comisiones son 0.
- [ ] Texto exacto de los movimientos a huchas en el Excel en español (hoy se reconoce «To pocket»).

## Bankinter · cuentas personales

Cada persona tiene la suya; **solo la ve su titular** (ADR-0013).

**Cómo descargarlo:** web de Bankinter → cuenta → *Movimientos* → descargar en Excel (.xlsx). Los `.xls` antiguos no se admiten: hay que exportar en `.xlsx`.

Estructura de la hoja `Movimientos` (validada con un extracto real):

1. Primera fila: «MOVIMIENTOS DE LA CUENTA …» con el número de cuenta. **No se lee** y nunca aparece en mensajes ni en filas descartadas.
2. «MOVIMIENTOS PENDIENTES …» y, debajo, su propia cabecera `Fecha, Descripción, Importe, Divisa` con los pendientes. Se descartan con el motivo «pendiente: se importará cuando se contabilice».
3. «MOVIMIENTOS» y los filtros aplicados en la web (`Concepto`, `Fecha`, `Tipo de movimiento`, `Importe`). Se ignoran.
4. La cabecera real y los movimientos:

| Columna | Uso en OpenFinance |
| --- | --- |
| `Fecha contable` | Fecha del movimiento, texto `dd/mm/aaaa`. Bankinter no da hora: se guarda a las 00:00 |
| `Fecha valor` | Fecha valor, `dd/mm/aaaa` |
| `Descripción` | Concepto |
| `Importe` | Importe con signo (número entero o decimal) |
| `Saldo` | Saldo tras el movimiento |
| `Divisa` | Moneda |

- Los movimientos van **del más reciente al más antiguo**; se invierten y en ese orden cuadra el saldo.
- **Duplicados:** como no hay hora, la huella añade el saldo tras el movimiento. Así dos movimientos iguales el mismo día no se fusionan y un extracto que solapa con otro solo añade lo nuevo.

**Clasificación automática:**

- Salidas «Revolut\*\*NNNN\*» (la recarga de la conjunta) → **aportación** del titular: una salida que no es gasto ni cuenta en los totales del hogar. Esta regla es solo de Bankinter.
- Salidas que coinciden con un patrón de salida guardado para el titular → **aportación** del titular.
- Transferencias y Bizum: entrada → **ingreso**; salida → **gasto**. En la cuenta personal no se usan los nombres: un Bizum de la pareja es un ingreso.

## Patrones por persona

Las aportaciones que no llevan el nombre se reconocen con patrones guardados por persona (ADR-0015). Se gestionan desde el servidor; escribe el patrón **entre comillas simples** para que la shell no toque `*` ni los espacios:

```bash
cd services/api
uv run openfinance member-patterns add raul@example.org '*1234'              # entrada en la conjunta
uv run openfinance member-patterns add raul@example.org 'TRASPASO CASA' --outflow  # salida de su Bankinter
uv run openfinance member-patterns list raul@example.org
uv run openfinance member-patterns remove raul@example.org '*1234'
```

- Un patrón necesita al menos 3 letras o cifras (`*1234` sí, `***` no) y como mucho 60 caracteres.
- `REVOLUT**` como patrón de salida ya viene incluido en las cuentas personales de Bankinter. En una cuenta personal de otra entidad hay que guardarlo si significa lo mismo.

## Comprobar un extracto sin guardarlo

```bash
cd services/api
uv run openfinance statement-check --bank revolut   ruta/al/extracto.xlsx
uv run openfinance statement-check --bank bankinter ruta/a/movimientos.xlsx
```

Solo muestra recuentos (filas, importables, descartadas por motivo, descuadres de saldo, tipos propuestos y aportaciones con o sin persona). No muestra conceptos, importes, números de cuenta ni el nombre del archivo, y no necesita base de datos.
