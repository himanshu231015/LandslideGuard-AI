import httpx
import pytest

from src.decisions.policy import (
    OPTIONS,
    apply_safety_overrides,
    classify_incident,
)


def test_classify_incident_parses_decider_response():
    def handler(request):
        payload = __import__("json").loads(request.content)

        assert payload["questions"]["response_category"]["type"] == "choice"
        assert "criteria" in payload["questions"]["response_category"]

        return httpx.Response(
            200,
            json={
                "model": "test-decider",
                "answers": {
                    "response_category": {
                        "type": "choice",
                        "choice": "INVESTIGATE",
                        "confidence": 0.91,
                    }
                },
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    decision = classify_incident(
        "Rain has been reported near a mountain road.",
        client=client,
    )
    client.close()

    assert decision["category"] == "INVESTIGATE"
    assert decision["confidence"] == pytest.approx(0.91)
    assert decision["needs_review"] is False
    assert decision["source"] == "strands-decider-2b"
    assert decision["latency_ms"] >= 0


def test_invalid_decider_category_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "answers": {
                    "response_category": {
                        "type": "choice",
                        "choice": "INVENTED_CATEGORY",
                        "confidence": 0.99,
                    }
                }
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(ValueError):
            classify_incident("A sufficiently long test report.", client=client)
    finally:
        client.close()


def test_low_confidence_requires_review():
    decision = {
        "category": "INVESTIGATE",
        "confidence": 0.50,
        "needs_review": True,
    }

    result = apply_safety_overrides(
        "The road condition is unclear.", decision
    )

    assert result["needs_review"] is True
    assert result["safety_override"] is False


def test_immediate_danger_triggers_override():
    decision = {
        "category": "MONITOR",
        "confidence": 0.99,
        "needs_review": False,
    }

    result = apply_safety_overrides(
        "Rocks are falling and vehicles are stranded.", decision
    )

    assert result["category"] == "EMERGENCY_ESCALATION"
    assert result["safety_override"] is True
    assert result["needs_review"] is True
    assert result["safety_note"]


def test_categories_are_fixed():
    assert OPTIONS == [
        "MONITOR",
        "INVESTIGATE",
        "RESTRICT_ACCESS",
        "EMERGENCY_ESCALATION",
    ]
