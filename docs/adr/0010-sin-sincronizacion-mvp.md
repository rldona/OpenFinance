# ADR-0010: No bidirectional sync in the MVP

- Status: Proposed
- Date: 2026-10-31

## Context

Syncing replicas across devices requires solving conflicts, device identities, encryption, revocation and recovery. It is a project in itself.

## Proposed decision

In v0.1 each installation has a single source of truth. Access from other devices is through the server's authenticated web app.

## Consequences

- Conflicts between replicas are not resolved in the MVP.
- Stable identifiers (UUID) and data provenance are kept from the start to ease a future sync.
- Full data export covers portability in the meantime.
