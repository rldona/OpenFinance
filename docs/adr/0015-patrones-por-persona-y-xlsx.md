# ADR-0015: Patrones de aportación por persona y extractos en Excel

- Estado: Accepted
- Fecha: 2026-11-01

## Contexto

Con los primeros extractos reales (OF-104, OF-107) aparecieron tres cosas que el diseño de OF-105 no cubría:

1. **Revolut se descarga en Excel (.xlsx)** cuando la app está en español, con cabeceras en español (algunas con la codificación rota, `DescripciÃ³n`), fechas de Excel con fracciones de segundo e importes numéricos. El CSV en inglés sigue siendo posible.
2. **Bankinter solo exporta Excel**, con un preámbulo (número de cuenta, movimientos pendientes y filtros), fechas `dd/mm/aaaa` sin hora y los movimientos del más reciente al más antiguo.
3. **No todas las aportaciones llevan el nombre de la persona.** En la conjunta, una recarga desde la tarjeta de una persona aparece como «Recarga de \*NNNN» (los últimos dígitos de la tarjeta). En la cuenta personal de Bankinter, la recarga de Revolut aparece como una salida «Revolut\*\*NNNN\*». Ninguna de las dos se puede deducir del nombre.

## Decisión

### Patrones por persona

- Tabla `member_patterns` (hogar, sentido, patrón → persona). El patrón se guarda normalizado (mayúsculas, sin tildes, espacios simples), con 3 a 60 caracteres y al menos 3 letras o cifras: `*1234` vale, `***` no. La persona tiene que ser miembro del mismo hogar (clave foránea compuesta a `memberships`).
- Sentido **`inflow`**: entradas en la conjunta (y huchas) que son aportación de esa persona, además de su nombre completo y su primer nombre.
- Sentido **`outflow`**: salidas de **su** cuenta personal que son su aportación al hogar. Los patrones guardados valen para cualquier cuenta personal del titular. Además, **solo en las cuentas personales de Bankinter** se incluye siempre `REVOLUT**` (así aparece allí la recarga de la conjunta); en otras entidades ese texto puede significar otra cosa (por ejemplo, un pago con tarjeta de Revolut) y sigue siendo gasto salvo que se guarde como patrón.
- En una cuenta personal **no** se usan los nombres: un Bizum de la pareja es un ingreso, no una aportación. Los patrones de otras personas o de otro hogar nunca se aplican.
- Se gestionan desde el servidor con `openfinance member-patterns add|list|remove <email> '<patrón>' [--outflow]`.
- **Actualización (OF-704):** cada persona gestiona también **los suyos** desde Ajustes (`GET/POST/DELETE /api/v1/me/patterns`). La API nunca lista ni borra los de la pareja. Al importar en la conjunta de Revolut, la vista previa dice quién no tiene tarjeta de recarga guardada y la web pide confirmación antes de importar, porque sus recargas entrarían como ingreso.
- La clasificación sigue en el dominio (`ClassificationRules`, `suggest_kind`); el puerto `StatementParser` no cambia.

### Lectura de Excel

- `openpyxl` (con `defusedxml`) solo en `infrastructure/importers/xlsx.py`; `import-linter` impide usarlo en el dominio y la aplicación.
- Antes de abrir el archivo se comprueba el zip: como mucho 100 partes y 10 MB descomprimidos en total, ninguna parte por encima de 8 MB, `xl/styles.xml` hasta 1 MB y `xl/sharedStrings.xml` hasta 5 MB (openpyxl las carga enteras en memoria), ratio de compresión por parte de 100 como máximo y ninguna parte cifrada. Si `openpyxl` no está usando `defusedxml`, no se lee ningún Excel.
- Se lee la primera hoja en modo solo lectura, sin fórmulas ni enlaces externos, ignorando la dimensión declarada (puede ser falsa), con un máximo de 20 000 filas y 30 columnas. Los `.xls` antiguos se rechazan pidiendo `.xlsx`.
- El CSV se lee en streaming con los mismos límites de filas y columnas; las líneas vacías se saltan sin acumularlas.
- Un importe que no cabe en las columnas (`Numeric(19, 4)`: 10¹⁵ o más) o con un exponente absurdo se descarta como fila no válida.
- Leer el extracto es trabajo síncrono: la API lo ejecuta fuera del bucle de eventos.
- Los números se convierten a `Decimal` desde su representación más corta (`repr`), nunca operando con `float`. Las horas se redondean al segundo.
- La codificación rota (`DescripciÃ³n`) solo se repara en el Excel de Revolut. El CSV se lee tal cual para que sus huellas no cambien.
- Los mensajes de error no incluyen valores de celdas (el preámbulo de Bankinter lleva el número de cuenta).

### Orden, saldo y huellas

- Contrato del lector: las filas salen en el **orden en que el banco las aplica al saldo**, de la más antigua a la más reciente. Revolut: el orden del archivo (fecha de finalización). Bankinter: el inverso del archivo. El saldo final del banco es el de la última fila con saldo (`ParseResult.closing_balance`), no el de la fecha más tardía.
- `fingerprint` acepta un `discriminator` opcional. Vacío, la huella es idéntica a la anterior: las ya guardadas siguen valiendo. Bankinter no da hora, así que usa como discriminador el saldo tras el movimiento: dos cafés iguales el mismo día no se fusionan y un extracto que solapa con otro reconoce los ya importados.

### Clasificación por banco

- Revolut: «Pago con tarjeta» (o `CARD_PAYMENT`) con importe positivo es una devolución: gasto positivo.
- Bankinter: transferencias y Bizum según el signo (entrada = ingreso, salida = gasto), salvo las salidas que coinciden con un patrón `outflow` del titular, que son su aportación.

## Consecuencias

- Las aportaciones por recarga de tarjeta y desde Bankinter se reconocen sin tocar el código, guardando un patrón por persona.
- Una aportación importada desde la cuenta personal no cuenta como gasto ni como entrada del hogar (ADR-0013).
- `openfinance statement-check --bank revolut|bankinter FICHERO` comprueba un extracto sin base de datos y muestra solo recuentos; sirve para validar formatos nuevos sin exponer datos.
- Mezclar el CSV en inglés y el Excel en español de la misma cuenta puede duplicar movimientos: los conceptos no coinciden («Payment from…» frente a «Transferencia de…»), así que las huellas tampoco. Hay que usar siempre el mismo formato.
- La vista «mi gasto» de cada persona sobre su cuenta personal queda para OF-108.
