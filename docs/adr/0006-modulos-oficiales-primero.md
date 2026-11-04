# ADR-0006: Official modules first; public SDK later

- Status: Accepted
- Date: 2026-10-31

## Context

Designing an extension SDK before having real modules tends to produce incomplete contracts that later cannot be changed without breaking third parties.

## Decision

- The first modules (categorization, budgeting) are official and live in `openfinance.modules`.
- They implement a versioned internal contract: identity and version, compatibility with the Core, capabilities, requested permissions, tools and events they publish or consume, configuration, migrations and lifecycle.
- A module has no global access to data: it receives only the declared and approved permissions.
- No third-party code runs in the main process.

## Consequences

- The public SDK will be designed from at least two real official modules.
- Third-party extensions, when they arrive, will be isolated in separate processes or in a runtime with limited capabilities.
