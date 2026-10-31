# OpenFinance

Gestor económico open source para el hogar: una pareja, una cuenta común y gráficos claros para saber **cuánto gastamos, en qué y cómo ahorrar mejor**. Se ejecuta en casa o en un servidor propio y los datos no salen de ahí.

> Estado: **pre-alpha (v0.1 en desarrollo)**. Prototipo navegable en [docs/product/prototypes/index.html](docs/product/prototypes/index.html).

## Principios

- **Simple primero.** Un hogar, una cuenta común e importación de CSV. Se crece cuando la base esté en uso ([ADR-0012](docs/adr/0012-empezar-por-el-hogar.md)).
- **Cifras exactas.** Importes en decimal, nunca `float`; los traspasos a ahorro no cuentan como gasto.
- **Visual.** Cada pantalla responde a una pregunta con un gráfico.
- **Tus datos, en tu casa.** Local o self-hosted, sin servicios externos obligatorios.

## Estructura

```
apps/web/          Aplicación web (React + TypeScript + Vite)
services/api/      OpenFinance Core: dominio, casos de uso, persistencia y API (FastAPI)
deploy/docker/     Imágenes de contenedor
docs/              Producto, arquitectura, ADRs y guías de desarrollo
compose.yaml       Entorno self-hosted con PostgreSQL
```

## Empezar

```bash
make setup     # instala dependencias (uv + npm)
make api       # API en http://localhost:8000  (docs en /docs)
make web       # Web en http://localhost:5173
make check     # lint, tipos, tests y build
```

Guía completa: [docs/development/getting-started.md](docs/development/getting-started.md).

## Documentación

- [Visión de producto](docs/product/vision.md)
- [Roadmap y backlog](docs/product/roadmap.md)
- [Prototipos](docs/product/prototypes/index.html)
- [Arquitectura](docs/architecture/overview.md)
- [Decisiones de arquitectura (ADRs)](docs/adr/README.md)

## Licencia

Candidata: [AGPL-3.0-or-later](docs/adr/0008-licencia-agpl.md), pendiente de revisión de dependencias antes del primer release público.
