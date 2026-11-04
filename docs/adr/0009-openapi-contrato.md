# ADR-0009: OpenAPI as the contract between frontend and backend

- Status: Proposed
- Date: 2026-10-31

## Context

The web app and the API evolve in parallel and other clients (CLI, mobile) may exist.

## Proposed decision

- FastAPI publishes the schema at `/openapi.json`, under the versioned prefix `/api/v1`.
- The schema is exported to the repository and the TypeScript client in `apps/web/src/api` is generated or checked from it in CI.
- Breaking changes require a new API version.

## Consequences

- Contract breakages are detected before integration.
- A client generator has to be chosen (pending; today the client is manual and minimal).
