# ADR-0011: Perfiles compartidos y reparto de gastos

- Estado: Proposed
- Fecha: 2026-10-31

## Contexto

Además del perfil de cada persona, se necesitan perfiles comunes, como «Casa», en los que varias personas comparten gastos (wifi, luz, agua, compras…). Se debe cubrir tanto el caso 1 a 1 (una pareja) como el N a N (un piso compartido). Un perfil común puede tener una cuenta conjunta y también gastos que paga una persona de su bolsillo. Algunas personas del grupo pueden no tener usuario en OpenFinance.

## Decisión

### Perfil común = workspace compartido

Se reutiliza `Workspace` (ADR-0002) con `kind = personal | shared`. Un workspace compartido puede usar una plantilla (Casa, Pareja, Viaje, Grupo) que aporta icono y categorías por defecto, sin cambiar el modelo. El reparto de gastos es un módulo oficial (`official.sharing`, ADR-0006) y un nuevo contexto de dominio, `sharing`.

### Entidades

| Entidad | Responsabilidad |
| --- | --- |
| `Participant` | Persona que comparte gastos en el workspace. Puede tener `user_id` o no. |
| `SharedExpense` | Gasto con importe, fecha, categoría, **quién pagó** y **cómo se reparte**. |
| `ExpenseSplit` | Parte de cada participante en un gasto. Se guarda el importe resultante, no solo la regla. |
| `Contribution` | Aportación de un participante a la cuenta común. |
| `Settlement` | Liquidación de una deuda entre dos participantes. |

- **Participantes sin usuario:** se crean por nombre y no tienen acceso a nada. Un owner o editor registra los movimientos en su nombre. Más adelante se pueden vincular a un usuario mediante una invitación sin perder el histórico.
- **Miembros y participantes:** cada miembro con usuario tiene un `Participant`. El rol (`owner`/`editor`/`viewer`) controla lo que puede hacer; el participante, en qué se reparte.

### Quién paga

Un gasto lo paga una de estas dos fuentes:

1. **La cuenta común**: es un `Account` del workspace compartido y se nutre de `Contribution`s.
2. **Uno o varios participantes de su bolsillo.** La suma de lo pagado tiene que ser igual al importe del gasto.

### Cómo se reparte

Métodos: `equal` (partes iguales), `percentage`, `exact` (importes) y `shares` (pesos, por ejemplo 2:1:1). Puede participar un subconjunto del grupo (1 a 1 dentro de un grupo de N).

- Los cálculos se hacen en unidades menores enteras (céntimos). Si sobran céntimos, se asignan con el método del **mayor resto**, con desempate determinista por el orden de los participantes. La suma de las partes es siempre **exactamente** el importe del gasto. Si no cuadra, el Core rechaza el gasto.
- Se guardan el método y el resultado. Cambiar el método recalcula y deja traza en auditoría.

### Dos saldos separados

Para que el dinero de la cuenta común no se mezcle con las deudas entre personas:

- **Participación en el fondo** de cada persona = aportado − su parte de los gastos pagados con la cuenta común. La suma de todas las participaciones es exactamente el saldo de la cuenta común.
- **Saldo entre personas** = pagado de su bolsillo − su parte de esos gastos + liquidaciones enviadas − liquidaciones recibidas. La suma de todos los saldos es exactamente 0.

Las sugerencias de «quién paga a quién» se calculan solo sobre el saldo entre personas: el dinero se queda en la cuenta común salvo que el grupo decida repartirlo. El algoritmo emparejará deudores y acreedores con el mínimo de transferencias.

### Liquidaciones con doble confirmación

Quien paga registra el `Settlement` y queda `pending_confirmation` hasta que el receptor lo confirma, o un owner o editor si el receptor no tiene usuario. Solo entonces modifica los saldos.

### Relación con el perfil personal

Si Ana paga la luz de Casa (90 €, un tercio le corresponde a ella) desde su cuenta personal:

- En su workspace personal, el movimiento de −90 € se enlaza al `SharedExpense` como **«Gasto compartido · Casa»**. Su **gasto real son 30 €**; los 60 € restantes son un importe pendiente de cobro al grupo, no un gasto.
- Una aportación a la cuenta común es un movimiento hacia el perfil compartido, igual que una transferencia: **no cuenta como gasto**. El gasto aparece cuando la cuenta común paga algo, por la parte que le corresponde a cada persona.
- Los demás miembros de Casa ven «pagado por Ana», pero **nunca** la cuenta personal ni el movimiento de origen (ADR-0002).

### Manager

El Manager puede sugerir un reparto o la categoría de un gasto importado de la cuenta común. También puede preparar liquidaciones. Todo pasa por propuesta y aprobación (ADR-0005).

## Consecuencias

- Nuevo contexto `sharing` y módulo oficial `official.sharing`.
- Se necesitan enlaces entre workspaces (movimiento personal ↔ gasto compartido) que solo puede ver el dueño del movimiento de origen. Requieren tests negativos de aislamiento.
- Un participante solo se puede eliminar cuando sus dos saldos están a 0.
- Multimoneda: cada workspace tiene una moneda base. Un gasto en otra moneda guarda el tipo de cambio aplicado de forma explícita. En v0.1 solo se admite la moneda base.
- Pruebas obligatorias: las partes siempre suman el importe del gasto, la suma de los saldos entre personas es 0, la suma de las participaciones es igual al saldo de la cuenta común, y repetir el registro de una liquidación es idempotente.
