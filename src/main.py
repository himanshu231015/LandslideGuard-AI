import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.realtime import get_realtime_bundle
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.bedrock import explain_incident
from src.decisions.policy import (
    DeciderUnavailable,
    classify_incident,
    apply_safety_overrides,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="LandslideGuard AI",
    description="Prototype hazard triage with Strands Decider 2B and Bedrock",
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(FRONTEND)),
    name="static",
)


class IncidentRequest(BaseModel):
    report: str = Field(min_length=10, max_length=5000)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "LandslideGuard AI",
        "decider_url": os.getenv(
            "DECIDER_URL", "http://127.0.0.1:8099"
        ),
        "bedrock_region": os.getenv("AWS_REGION", "us-east-1"),
    }


@app.post("/api/incidents/analyze")
def analyze_incident(request: IncidentRequest):
    try:
        decision = classify_incident(request.report)
    except DeciderUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid Decider response: {exc}",
        ) from exc

    decision = apply_safety_overrides(request.report, decision)

    try:
        explanation = explain_incident(
            report=request.report,
            category=decision["category"],
            confidence=decision["confidence"],
            safety_note=decision.get("safety_note"),
        )
        bedrock_status = "success"
    except RuntimeError:
        # The decision remains visible if Bedrock is unavailable.
        # The response must not imply that generation succeeded.
        explanation = (
            "Bedrock explanation unavailable. Review the reported "
            "facts and decision manually. Do not treat this prototype "
            "as a substitute for emergency services."
        )
        bedrock_status = "unavailable"

    return {
        "incident_report": request.report,
        "decision": decision,
        "explanation": explanation,
        "bedrock_status": bedrock_status,
        "prototype_notice": (
            "Decision support only. Verify conditions with "
            "authorized responders before acting."
        ),
    }
@app.get("/api/realtime")
def realtime(place: str = "Kedarnath, Uttarakhand, India"):
    return get_realtime_bundle(place)