"""Exporta el esquema OpenAPI para generar el cliente de la web (ADR-0009).

Uso: ``uv run python -m openfinance.api.export_openapi > ../../apps/web/openapi.json``
"""

import json
import sys

from openfinance.infrastructure.config import Settings
from openfinance.main import create_app


def main() -> None:
    schema = create_app(Settings(environment="development")).openapi()
    json.dump(schema, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
