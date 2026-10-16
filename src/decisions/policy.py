import os
import time
from typing import Any

import httpx

DECIDER_URL = os.getenv(
    "DECIDER_URL", "http://127.0.0.1:8099"
).rstrip("/")

OPTIONS = [
    "MONITOR",
    "INVESTIGATE",
    "RESTRICT_ACCESS",
    "EMERGENCY_ESCALATION",
]

CONFIDENCE_THRESHOLD = float(
    os.getenv("CONFIDENCE_THRESHOLD", "0.80")
)


class DeciderUnavailable(RuntimeError):
    """Raised when the real Decider service cannot be reached."""


def _extract_choice(answer: dict[str, Any]) -> tuple[str, float]:
    """Normalize the choice fields returned by Decider."""
    choice = answer.get("choice")
    confidence = answer.get("confidence")

    if isinstance(choice, dict):
        confidence = confidence or choice.get("confidence")
        choice = choice.get("label") or choice.get("value")

    if isinstance(choice, int) and not isinstance(choice, bool):
        if 0 <= choice < len(OPTIONS):
            choice = OPTIONS[choice]

    if not isinstance(choice, str) or choice not in OPTIONS:
        raise ValueError(
            f"Unexpected Decider choice: {choice!r}"
        )

    if not isinstance(confidence, (int, float)):
        raise ValueError("Decider response has no numeric confidence")

    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("Confidence must be between 0 and 1")

    return choice, confidence


def classify_incident(
    report: str,
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Use the real Decider service to classify a hazard report."""
    payload = {
        "state": report,
        "questions": {
            "response_category": {
                "type": "choice",
                "instructions": (
                    "Choose the most appropriate response category "
                    "for the reported landslide hazard. Base the "
                    "choice on the described observations. "
                    "Do not invent missing facts."
                ),
                "criteria": {
                    "MONITOR": (
                        "No immediate danger is described; continue "
                        "observation and gather updates."
                    ),
                    "INVESTIGATE": (
                        "Information is incomplete or the hazard "
                        "needs assessment before a stronger response."
                    ),
                    "RESTRICT_ACCESS": (
                        "A credible physical hazard affects a road "
                        "or access route and access should be assessed "
                        "by authorized responders."
                    ),
                    "EMERGENCY_ESCALATION": (
                        "Immediate danger, possible injury, trapped "
                        "people, or an active severe hazard is reported."
                    ),
                },
            }
        },
    }

    owned_client = client is None
    session = client or httpx.Client(timeout=30.0)

    started = time.perf_counter()
    try:
        response = session.post(
            f"{DECIDER_URL}/v1/systemone",
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DeciderUnavailable(
            f"Could not obtain a valid Decider response: {exc}"
        ) from exc
    finally:
        if owned_client:
            session.close()

    answers = body.get("answers", {})
    answer = answers.get("response_category")

    if not isinstance(answer, dict):
        raise ValueError(
            f"Missing response_category in Decider response: {body}"
        )

    category, confidence = _extract_choice(answer)

    return {
        "category": category,
        "confidence": confidence,
        "latency_ms": round(
            (time.perf_counter() - started) * 1000, 2
        ),
        "model": body.get("model", "unknown"),
        "needs_review": confidence < CONFIDENCE_THRESHOLD,
        "source": "strands-decider-2b",
    }


def apply_safety_overrides(
    report: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply conservative text-based overrides.

    This is a prototype safety layer, not a validated emergency
    detection system. Production use needs tested policies and
    authoritative data sources.
    """
    text = report.casefold()

    immediate_danger_terms = (
        "people are injured",
        "person is injured",
        "people may be injured",
        "trapped people",
        "people trapped",
        "vehicles are stranded",
        "rocks are falling",
        "active landslide",
        "road has collapsed",
        "building collapsed",
    )

    result = dict(decision)
    result["safety_override"] = False

    if any(term in text for term in immediate_danger_terms):
        result["category"] = "EMERGENCY_ESCALATION"
        result["safety_override"] = True
        result["needs_review"] = True
        result["safety_note"] = (
            "Potential immediate danger was mentioned. "
            "Contact local emergency services or authorized "
            "responders and follow their instructions."
        )
    elif result["needs_review"]:
        result["safety_note"] = (
            "Confidence is below the configured threshold. "
            "Request human review before acting."
        )

    return result
