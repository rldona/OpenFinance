# OpenFinance

Open source household finance manager: a couple, a shared account and clear charts to see **how much we spend, on what, and how to save better**. It runs at home or on your own server, and your data never leaves it.

> Status: **pre-alpha (v0.1 in development)**. Clickable prototype at [docs/product/prototypes/index.html](docs/product/prototypes/index.html).

## Principles

- **Simple first.** One household, one shared account and CSV import. We grow once the base is in use ([ADR-0012](docs/adr/0012-empezar-por-el-hogar.md)).
- **Exact figures.** Amounts in decimal, never `float`; transfers to savings do not count as spending.
- **Visual.** Each screen answers one question with a chart.
- **Your data, in your home.** Local or self-hosted, with no mandatory external services.

## Structure

```
apps/web/          Web application (React + TypeScript + Vite)
services/api/      OpenFinance Core: domain, use cases, persistence and API (FastAPI)
deploy/docker/     Container images and nginx configuration
deploy/caddy/      HTTPS with your own domain (optional)
deploy/scripts/    Backups, restore and licenses
docs/              Product, architecture, ADRs and guides
compose.yaml       Self-hosted install (compose.https.yaml adds HTTPS)
```

## Getting started

```bash
make setup     # installs dependencies (uv + npm)
make api       # API at http://localhost:8000  (docs at /docs)
make web       # Web at http://localhost:5173
make check     # lint, types, tests and build
```

Full guide: [docs/development/getting-started.md](docs/development/getting-started.md).

To install it at home (Docker Compose, phone access, HTTPS and backups): [docs/deployment/home.md](docs/deployment/home.md).

## Documentation

- [Product vision](docs/product/vision.md)
- [Roadmap and backlog](docs/product/roadmap.md)
- [Prototypes](docs/product/prototypes/index.html)
- [Architecture](docs/architecture/overview.md)
- [Install at home](docs/deployment/home.md)
- [Architecture decisions (ADRs)](docs/adr/README.md)
- [Changes (CHANGELOG)](CHANGELOG.md)
- [Prepare a release](docs/development/release.md)

## License

[AGPL-3.0-or-later](LICENSE) ([ADR-0008](docs/adr/0008-licencia-agpl.md)). You may use it, modify it and offer it as a service; if you modify it and offer it over a network, you must publish your changes under the same license.

- Dependency licenses: [docs/legal/dependencias.md](docs/legal/dependencias.md) (`make licenses`).
- Contributions use the DCO (`git commit -s`), no CLA: [CONTRIBUTING.md](CONTRIBUTING.md).
