# ADR-0007: Local-first and self-hosted with optional external services

- Status: Accepted
- Date: 2026-10-31

## Context

Deployment is "hybrid": the user decides where their data lives and which external services they use.

## Decision

- **Local mode:** application and database on the user's machine (Docker Compose).
- **Self-hosted mode:** the same artifact on the user's own server, with authenticated web access.
- **Optional external services:** LLM providers, bank connectors, etc., always through explicit adapters and disabled by default.
- A single application for both modes; no product forks.

## Consequences

- We must document which data leaves the installation with each external service enabled.
- Secrets outside the code and the prompts; backup and restore documented and tested before v0.1.
- Future support for local models through the same provider adapter.
