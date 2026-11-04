# ADR-0004: Separation between Core and Manager

- Status: Accepted
- Date: 2026-10-31

## Context

The Manager uses LLMs, which can make mistakes or be manipulated through prompt injection (for example, from the description of an imported bank transaction). The financial rules must stay correct no matter what happens in that layer.

## Decision

- The Core (domain + application) does not depend on any AI provider and works without one.
- The Manager acts only through a **Tool Gateway** with typed tools (`transactions.search`, `budgets.get_status`, `transactions.propose_category`…), each with an argument schema, a required permission and a scope limit.
- The Manager never has database credentials or runs SQL.
- Permissions are evaluated in the gateway with the identity of the user who started the task; the model cannot widen them.
- The figures in responses come from tool results, which are stored with the run (`AgentRun`).

## Consequences

- Each new Manager capability requires defining its tool in the Core first.
- The LLM provider is interchangeable through an adapter.
- External data is passed to the model as marked content, never as instructions.
