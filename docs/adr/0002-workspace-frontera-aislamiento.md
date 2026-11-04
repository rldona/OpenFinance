# ADR-0002: Workspace as the isolation boundary

- Status: Accepted
- Date: 2026-10-31

## Context

OpenFinance is multi-user from the start: a person can have their own finances and share others with their family. Data leakage between users is the product's top risk.

## Decision

- `User` is the global identity; `Workspace` is the financial context and the access boundary; `Membership` links both with a role (`owner`, `editor`, `viewer`).
- Every financial entity has a non-null `workspace_id`.
- Authorization is decided on the server by combining membership, role, resource and action. The role is the starting point, not the only rule: `AccountAccess` allows restricting specific accounts.
- A shared account must be shared explicitly.
- The same checks apply to the API, asynchronous tasks, exports and Manager tools.

## Consequences

- All use cases receive an authorization context (actor + workspace).
- Repositories always filter by workspace; negative tests are added that tamper with identifiers across workspaces.
- PostgreSQL Row-Level Security will be considered as defense in depth, not as a replacement.
