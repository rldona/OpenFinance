# ADR-0007: Local-first y self-hosted con servicios externos opcionales

- Estado: Accepted
- Fecha: 2026-10-31

## Contexto

El despliegue es «híbrido»: el usuario decide dónde residen sus datos y qué servicios externos usa.

## Decisión

- **Modo local:** aplicación y base de datos en el equipo del usuario (Docker Compose).
- **Modo self-hosted:** el mismo artefacto en un servidor propio, con acceso web autenticado.
- **Servicios externos opcionales:** proveedores de LLM, conectores bancarios, etc., siempre mediante adaptadores explícitos y desactivados por defecto.
- Una sola aplicación para ambos modos; nada de bifurcaciones del producto.

## Consecuencias

- Hay que documentar qué datos salen de la instalación con cada servicio externo activado.
- Secretos fuera del código y de los prompts; copia de seguridad y restauración documentadas y probadas antes de v0.1.
- Soporte futuro de modelos locales mediante el mismo adaptador de proveedores.
