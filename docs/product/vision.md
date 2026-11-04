# Product vision

**OpenFinance is the money manager for our home.** A couple with a shared account wants to know, at a glance and with clear charts:

1. **How much do we spend?** This month, compared with last month and with our average.
2. **Where does it go?** By category and by merchant, and how each one evolves.
3. **How can we save better?** Goals, concrete ideas calculated from our own data, and a simulator.

It is open source, runs at home or on your own server, and the data never leaves there ([ADR-0007](../adr/0007-local-first-self-hosted.md)).

## v0.1 screens

The screen names below are the app's Spanish UI labels, with an English gloss.

| Screen | What it answers |
| --- | --- |
| **Este mes** (This month) | Spent and saved, top category, category donut, day-by-day spending pace compared with last month and the budget, changes versus the average, and budgets. |
| **¿En qué gastamos?** (Where do we spend?) | Donut and ranking of categories. Clicking one shows its 12 months against the average, its top merchants and its transactions. |
| **Evolución** (Trends) | 12-month stacked bars by category, savings for each month, best and worst month. |
| **Ahorrar** (Save) | Goals with an estimated date, savings ideas with euros per year, and a cut simulator that moves the goal's date. |
| **Movimientos** (Transactions) | Month-by-month list with search; the category is changed in the table itself and a rule is learned. |
| **Importar** (Import) | Bank CSV → review with proposed categories and duplicates → done. |

Clickable prototype: [prototypes/index.html](prototypes/index.html).

## Money rules

- Exact amounts (`Decimal`/cents), never `float`.
- Each person's **contributions** to the shared account are inflows.
- A **transfer to the savings account is savings**, not spending.
- **Monthly savings** = what comes in − what is spent.
- Importing the same file twice does not duplicate transactions.

## Out of v0.1, to grow later

In approximate order of priority:

1. More household accounts (savings, cards) and balance reconciliation.
2. Automatic bank connection (Open Banking).
3. AI assistant that explains the charts and proposes changes with approval ([ADR-0004](../adr/0004-separacion-core-manager.md), [ADR-0005](../adr/0005-aprobacion-humana.md)).
4. Shared profiles and expense splitting between people ([ADR-0011](../adr/0011-perfiles-compartidos-reparto.md)).
5. Modules and extensions ([ADR-0006](../adr/0006-modulos-oficiales-primero.md)).

The reasoning is in [ADR-0012](../adr/0012-empezar-por-el-hogar.md).

## Phases

Details with tickets and acceptance criteria in the [roadmap](roadmap.md).

0. **Foundation** (done): repository, CI, Docker Compose and `Money`.
1. **Data**: household, two users, account, transactions and CSV import with deduplication.
2. **Categories**: categories, learned rules and in-table correction.
3. **Charts**: Este mes, ¿En qué gastamos? and Evolución.
4. **Savings**: budgets, goals, ideas and simulator.
5. **Real use**: backups, home installation and the first months with real data.
