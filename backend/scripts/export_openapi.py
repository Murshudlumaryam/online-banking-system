"""
Exports the backend's OpenAPI schema to a JSON file — no running server, no
database connection required (FastAPI generates the schema purely from
route/Pydantic-model introspection). The frontend's `npm run generate:api`
script consumes this file to regenerate its typed API client.

Usage:
    python scripts/export_openapi.py [output_path]

Default output_path: ../frontend/openapi.json (relative to this file).
"""
import json

# Any DATABASE_URL/JWT_SECRET_KEY value works here — settings are only used
# to build middleware/engine objects, never actually connected to, since we
# never handle a real request.
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
os.environ.setdefault("JWT_SECRET_KEY", "schema-export-placeholder")
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402


def main() -> None:
    default_output = Path(__file__).resolve().parent.parent.parent / "frontend" / "openapi.json"
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_output

    app = create_app()
    schema = app.openapi()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2))
    print(f"Exported {len(schema['paths'])} paths to {output_path}")


if __name__ == "__main__":
    main()
