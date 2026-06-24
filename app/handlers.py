"""AWS Lambda entry points for the QueueSmart AI features.

Each handler is a thin adapter: the invocation `event` IS the frozen contract
JSON (Backend invokes these functions directly), which we validate into the
request model, run through the HTTP-free pure function, and return as a plain
dict. The same functions back the FastAPI routes in app.main for local testing.

  §3.1 prevetting       -> app.handlers.prevetting
  §3.2 smart_alert      -> app.handlers.smart_alert
  §3.3 routing          -> app.handlers.routing
  §3.4 manager_advice   -> app.handlers.manager_advice
  §3.5 doc_analysis     -> app.handlers.doc_analysis

Credentials come from the Lambda execution role; configuration (bucket, model
ids, KB id, calculator) comes from environment variables — see template.yaml.
"""

from __future__ import annotations

from .config import get_settings
from .doc_analysis import DocAnalysisRequest, analyze_document
from .manager_advice import ManagerAdviceRequest, advise
from .prevetting import PrevetRequest, prevet
from .routing import RoutingRequest, route
from .smart_alert import SmartAlertRequest
from .smart_alert import smart_alert as _smart_alert


def prevetting(event: dict, context=None) -> dict:
    return prevet(PrevetRequest(**event), get_settings()).model_dump()


def smart_alert(event: dict, context=None) -> dict:
    return _smart_alert(SmartAlertRequest(**event), get_settings()).model_dump()


def routing(event: dict, context=None) -> dict:
    return route(RoutingRequest(**event), get_settings()).model_dump()


def manager_advice(event: dict, context=None) -> dict:
    return advise(ManagerAdviceRequest(**event), get_settings()).model_dump()


def doc_analysis(event: dict, context=None) -> dict:
    req = DocAnalysisRequest(**event)
    return analyze_document(req.s3Key, req.expectedDocType, get_settings()).model_dump()
