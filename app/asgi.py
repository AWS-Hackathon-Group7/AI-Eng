"""Lambda entry point that serves the whole FastAPI app over a Function URL.

Mangum adapts the ASGI app (app.main:app) to the Lambda/Function URL event
format, so every route — including the auto-generated Swagger docs at /docs and
the OpenAPI schema at /openapi.json — is reachable at the function's public URL.
This is the frontend-testing surface; the per-feature handlers in app.handlers
remain the contract entry points the Backend invokes.
"""

from __future__ import annotations

from mangum import Mangum

from app.main import app

handler = Mangum(app)
