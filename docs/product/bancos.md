# Bancos del hogar

| Cuenta | Banco | En v0.1 | Cómo entra |
| --- | --- | --- | --- |
| Cuenta conjunta (gastos de casa) | **Revolut** | ✅ Sí | CSV del extracto |
| Huchas de la cuenta conjunta | **Revolut** | Como traspaso a ahorro | Se detectan en el mismo CSV |
| Cuentas personales de cada uno | **Bankinter** | ❌ No (ADR-0012) | Las aportaciones se ven desde Revolut |

## Revolut · cuenta conjunta

**Cómo descargarlo:** app de Revolut → cuenta conjunta → *Extracto* → formato *Excel* (CSV) → periodo.

Formato (confirmado con la configuración pública de importación de Firefly III para Revolut; pendiente de validar con una muestra nuestra):

| Columna | Uso en OpenFinance |
| --- | --- |
| `Type` | Procedencia. `CARD_REFUND` y `REFUND` son devoluciones: gasto con importe positivo |
| `Product` | Solo se importa `Current`. Las filas `Savings` (huchas) se omiten porque el traspaso ya aparece en `Current` |
| `Started Date` | Fecha y hora del movimiento (`AAAA-MM-DD HH:MM:SS`) |
| `Completed Date` | Fecha valor |
| `Description` | Concepto: comercio, «Payment from …», «To pocket …» |
| `Amount` | Importe con signo, separador decimal `.` |
| `Fee` | Comisión aparte: el efecto en la cuenta es `Amount − Fee` |
| `Currency` | Moneda del movimiento |
| `State` | Solo `COMPLETED`. `PENDING` se importará cuando se complete; `REVERTED` y `DECLINED` se descartan |
| `Balance` | Saldo tras el movimiento: se usa para comprobar que no faltan filas |

**Duplicados:** Revolut no da un identificador por movimiento. La huella combina cuenta, fecha y hora al segundo, importe, concepto normalizado y orden de aparición de filas idénticas en el archivo.

**Clasificación automática** (configurable):

- Entradas con el nombre de cada persona (p. ej. «Payment from Raúl …») → **aportación** de esa persona.
- «To pocket …» → **traspaso a ahorro**.
- Otras entradas (Bizum recibidos, intereses) → **ingreso**.
- El resto → **gasto**, pendiente de categoría.

Implementado en `services/api/openfinance/infrastructure/importers/revolut.py`, con tests sobre una muestra sintética (`tests/fixtures/revolut_joint_synthetic.csv`).

### Por confirmar con un extracto real

- [ ] Cabeceras exactas, en inglés o en español según el idioma de la app.
- [ ] Si la hora está en hora local o en UTC: decide en qué día cae un pago de madrugada.
- [ ] Signo de `Fee` y si `Balance` ya la descuenta.
- [ ] Texto exacto de las aportaciones desde Bankinter y de los movimientos a huchas.
- [ ] Valor de `Product` en una cuenta conjunta.

## Bankinter · cuentas personales

Fuera de v0.1. Si más adelante se quiere ver el gasto personal de cada uno, Bankinter exporta los movimientos desde la web (normalmente en Excel). Habrá que añadir un lector propio y un perfil personal por persona.
