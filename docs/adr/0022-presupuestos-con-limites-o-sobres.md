# ADR-0022: Presupuestos con límites o sobres, arrastre y objetivos v2

- Estado: Accepted
- Fecha: 2026-11-02

## Contexto

Los presupuestos de OF-401 son un límite mensual por categoría que se reinicia cada mes. Dos hogares gestionan el dinero de forma distinta: unos quieren **un tope** y ya (si no lo gastas, se pierde) y otros quieren **sobres** (lo que sobra de «Ocio» este mes se suma al siguiente, y lo que te pasas se resta). Los objetivos de OF-402 solo tienen una aportación mensual fija.

## Decisión

### Dos modos por categoría

- **Límite** (el actual): un importe por mes. Sin arrastre. Es el modo por defecto y **nada cambia** para quien no toque nada: sin migración de datos, los presupuestos existentes son límites.
- **Sobre**: un importe mensual que se **acumula**. El disponible de un mes es `asignado del mes + saldo arrastrado del mes anterior − gastado en el mes`. Un sobre puede quedar en negativo (se ha gastado más de lo que había) y ese déficit se arrastra, o puede reiniciarse a cero a mano.
- El arrastre se calcula **desde el mes en que se creó el sobre** y es una función pura de los gastos: no se guarda el saldo arrastrado, se recalcula, así que corregir un movimiento antiguo corrige todos los meses siguientes y nunca queda desincronizado.
- **Importes por mes**: un presupuesto puede tener un importe distinto en un mes concreto (vacaciones en agosto) sin tocar el resto. Sin excepción, vale el importe base.

### Qué cuenta como gasto del sobre

- Lo mismo que hoy: gastos de la categoría en cuentas del hogar visibles para quien consulta (corrientes y huchas), con las partes de un movimiento dividido (OF-1003) y convertidos a la moneda del hogar (ADR-0019). Las cuentas `card` y `loan` y los traspasos no cuentan. Un recibo programado (ADR-0021) no se descuenta hasta que se cobra.
- Presupuesto y sobres solo cuentan cuentas del hogar o visibles para el actor; una cuenta personal ajena nunca interviene (ADR-0013).

### Avisos

- Se mantiene el aviso al 85 % y al pasarse (OF-401). En un sobre, «pasado» significa disponible negativo. El aviso de una categoría con cuotas fijas sigue la regla actual de `budget_status`.

### Objetivos v2

- Un objetivo puede tener **aportaciones** registradas (fecha, importe, nota; quedan en el registro de cambios), **prioridad** (para ordenar y para repartir la aportación mensual sobrante) y **recordatorio** de su aportación mensual como pago programado (ADR-0021) en lugar de un número suelto.
- La proyección de OF-402 se mantiene; las aportaciones registradas alimentan «ahorrado» cuando el objetivo no está vinculado a una hucha.

## Consecuencias

- Se añaden `mode` y `started_on` a los presupuestos, la tabla `budget_overrides` y la tabla `goal_contributions`; migración sin tocar filas existentes.
- Tests de propiedades: sobres sin gasto acumulan exactamente `n × asignado`; reordenar los gastos entre meses no cambia el total acumulado.
- El front muestra el modo con claridad: «Límite» y «Sobre» se explican en la propia pantalla, y un sobre en negativo no se presenta como un error sino como lo que es.
