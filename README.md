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
deploy/docker/     Imágenes de contenedor y configuración de nginx
deploy/caddy/      HTTPS con dominio propio (opcional)
deploy/scripts/    Copias de seguridad, restauración y licencias
docs/              Producto, arquitectura, ADRs y guías
compose.yaml       Instalación self-hosted (compose.https.yaml añade HTTPS)
```

## Empezar

```bash
make setup     # instala dependencias (uv + npm)
make api       # API en http://localhost:8000  (docs en /docs)
make web       # Web en http://localhost:5173
make check     # lint, tipos, tests y build
```

Guía completa: [docs/development/getting-started.md](docs/development/getting-started.md).

Para instalarlo en casa (Docker Compose, acceso desde el móvil, HTTPS y copias de seguridad): [docs/deployment/home.md](docs/deployment/home.md).

## Documentación

- [Visión de producto](docs/product/vision.md)
- [Roadmap y backlog](docs/product/roadmap.md)
- [Prototipos](docs/product/prototypes/index.html)
- [Arquitectura](docs/architecture/overview.md)
- [Instalar en casa](docs/deployment/home.md)
- [Decisiones de arquitectura (ADRs)](docs/adr/README.md)
- [Cambios (CHANGELOG)](CHANGELOG.md)
- [Preparar una release](docs/development/release.md)

## Licencia

[AGPL-3.0-or-later](LICENSE) ([ADR-0008](docs/adr/0008-licencia-agpl.md)). Puedes usarlo, modificarlo y ofrecerlo como servicio; si lo modificas y lo ofreces por red, debes publicar tus cambios bajo la misma licencia.

- Licencias de las dependencias: [docs/legal/dependencias.md](docs/legal/dependencias.md) (`make licenses`).
- Contribuciones con DCO (`git commit -s`), sin CLA: [CONTRIBUTING.md](CONTRIBUTING.md).
