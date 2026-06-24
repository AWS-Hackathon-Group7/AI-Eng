#!/usr/bin/env python3
"""Write the FastAPI OpenAPI schema to docs/openapi.json.

Hand this file to the frontend: import it into Postman/Insomnia, generate a
typed client, or load it into any Swagger viewer. Re-run after changing routes
or request/response models to keep it current.

Usage:  python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

OUT = ROOT / "docs" / "openapi.json"


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parent.parent)}")


if __name__ == "__main__":
    main()
