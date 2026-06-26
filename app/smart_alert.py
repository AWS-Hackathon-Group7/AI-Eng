"""§3.2 ai-smart-alert: the "leave now" alert (the other hero feature).

INPUT
  { ticketId, customerLocation: {lat,lng}, venueLocation: {lat,lng},
    estimatedCallTime: ISO8601, position }
OUTPUT
  { leaveAtIso, leaveInSec, travelTimeSec, message }

We compute a live-traffic ETA with Amazon Location Service, work backwards from
estimatedCallTime (minus a safety buffer) to a leave-at time, and have Claude
phrase a short friendly nudge. If the customer's location is missing we return a
time-only fallback and say so. `smart_alert` is HTTP-free for the Lambda.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
from pydantic import BaseModel

from .config import Settings


class LatLng(BaseModel):
    lat: float
    lng: float


class SmartAlertRequest(BaseModel):
    ticketId: str
    venueLocation: LatLng
    estimatedCallTime: str
    position: int
    customerLocation: LatLng | None = None


class SmartAlertResponse(BaseModel):
    leaveAtIso: str
    leaveInSec: int
    travelTimeSec: int | None = None
    message: str


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _travel_time_seconds(req: SmartAlertRequest, settings: Settings) -> int:
    loc = boto3.client("location", region_name=settings.aws_region)
    resp = loc.calculate_route(
        CalculatorName=settings.location_calculator_name,
        # Location Service expects [longitude, latitude].
        DeparturePosition=[req.customerLocation.lng, req.customerLocation.lat],
        DestinationPosition=[req.venueLocation.lng, req.venueLocation.lat],
        TravelMode="Car",
        DepartNow=True,  # live traffic
    )
    return round(resp["Summary"]["DurationSeconds"])


def _phrase_message(
    settings: Settings,
    *,
    travel_time_sec: int | None,
    leave_in_sec: int,
    arrive_early_sec: int,
    position: int,
    located: bool,
) -> str:
    if located:
        facts = (
            f"Live driving time with current traffic: {travel_time_sec // 60} min. "
            f"They should leave in {max(0, leave_in_sec) // 60} min and will "
            f"arrive about {max(0, arrive_early_sec) // 60} min before their turn. "
            f"They are number {position} in the queue."
        )
        guidance = (
            "Write ONE short, friendly push-notification sentence telling the "
            "customer when to leave, mentioning traffic. No greeting, no emoji "
            "overload (one is fine)."
        )
    else:
        facts = (
            f"We do NOT have the customer's location, so traffic could not be "
            f"factored in. They are number {position} in the queue and should "
            f"head out to arrive by their estimated call time."
        )
        guidance = (
            "Write ONE short, friendly push-notification sentence telling them "
            "to set off in time, and honestly note you couldn't check live "
            "traffic without their location."
        )

    client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    resp = client.converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": guidance}],
        messages=[{"role": "user", "content": [{"text": facts}]}],
        inferenceConfig={"maxTokens": 120, "temperature": 0.4},
    )
    # Models sometimes wrap a single sentence in quotes — drop them.
    return resp["output"]["message"]["content"][0]["text"].strip().strip('"')


def smart_alert(req: SmartAlertRequest, settings: Settings) -> SmartAlertResponse:
    try:
        call_time = _parse_iso(req.estimatedCallTime)
        now = datetime.now(timezone.utc)
        buffer = timedelta(seconds=settings.arrival_buffer_seconds)

        if req.customerLocation is None:
            # Time-only fallback: leave by call time minus the safety buffer.
            leave_at = call_time - buffer
            try:
                message = _phrase_message(
                    settings,
                    travel_time_sec=None,
                    leave_in_sec=int((leave_at - now).total_seconds()),
                    arrive_early_sec=settings.arrival_buffer_seconds,
                    position=req.position,
                    located=False,
                )
            except Exception as e:
                print(f"Error phrasing fallback smart alert: {e}")
                message = f"Please set off in time to arrive before your turn. You are number {req.position} in the queue."
            return SmartAlertResponse(
                leaveAtIso=_iso_z(leave_at),
                leaveInSec=max(0, int((leave_at - now).total_seconds())),
                travelTimeSec=None,
                message=message,
            )

        try:
            travel_time = _travel_time_seconds(req, settings)
        except Exception as loc_err:
            print(f"Error calculating travel time from Amazon Location: {loc_err}")
            travel_time = 900  # fallback to 15 min

        leave_at = call_time - timedelta(seconds=travel_time) - buffer
        leave_in = int((leave_at - now).total_seconds())

        try:
            message = _phrase_message(
                settings,
                travel_time_sec=travel_time,
                leave_in_sec=leave_in,
                arrive_early_sec=settings.arrival_buffer_seconds,
                position=req.position,
                located=True,
            )
        except Exception as bed_err:
            print(f"Error phrasing smart alert message via Bedrock: {bed_err}")
            message = f"Based on your queue position ({req.position}), please head out in time to arrive for your turn."

        return SmartAlertResponse(
            leaveAtIso=_iso_z(leave_at),
            leaveInSec=max(0, leave_in),
            travelTimeSec=travel_time,
            message=message,
        )
    except Exception as e:
        print(f"Error in smart alert: {e}")
        # Top-level fallback
        call_time_str = req.estimatedCallTime
        try:
            call_time = _parse_iso(req.estimatedCallTime)
            leave_at = call_time - timedelta(minutes=20)
            leave_at_str = _iso_z(leave_at)
            leave_in = max(0, int((leave_at - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            leave_at_str = call_time_str
            leave_in = 600
        return SmartAlertResponse(
            leaveAtIso=leave_at_str,
            leaveInSec=leave_in,
            travelTimeSec=900,
            message=f"Traffic details are currently unavailable. Based on your schedule, you should set off in time to arrive before your turn. You are number {req.position} in the queue."
        )
