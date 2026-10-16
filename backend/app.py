
from pathlib import Path
import json
import sqlite3
import time

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "incidents.db"
MODEL_URL = "http://127.0.0.1:8099"

app = FastAPI(
    title="LandslideGuard AI API",
    description="Demo backend for landslide hazard assessment.",
    version="0.1.0",
)


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report TEXT NOT NULL,
                model_choice TEXT,
                final_category TEXT NOT NULL,
                model_confidence REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)


init_db()


class AssessmentRequest(BaseModel):
    report: str = Field(min_length=5, max_length=4000)


def apply_demo_safety_rule(report: str, model_choice: str) -> tuple[str, str]:
    """Illustrative demo rule, not a validated emergency protocol."""
    text = report.lower()

    urgent_phrases = [
        "rocks are falling",
        "falling rocks",
        "active landslide",
        "people are trapped",
        "person is injured",
        "people are injured",
    ]

    if any(phrase in text for phrase in urgent_phrases):
        return "EMERGENCY_ESCALATION", "demo_urgent_hazard_rule"

    if "road blocked" in text or "road is blocked" in text:
        return "RESTRICT_ACCESS", "demo_blocked_road_rule"

    return model_choice, "model_recommendation"


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MODEL_URL}/health")
            response.raise_for_status()
            model_health = response.json()

        return {
            "api_status": "ok",
            "model_server": model_health,
            "database": str(DB_PATH),
        }
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model server unavailable: {exc}",
        ) from exc


@app.post("/api/assess")
async def assess(request: AssessmentRequest):
    payload = {
        "state": request.report,
        "model": "landslideguard-local",
        "questions": {
            "response_category": {
                "type": "choice",
                "instructions": (
                    "Classify the reported landslide incident "
                    "using the available response categories."
                ),
                "criteria": {
                    "MONITOR": "Routine observation may be sufficient.",
                    "INVESTIGATE": "More information or field assessment is needed.",
                    "RESTRICT_ACCESS": "Restrict access to a hazardous area.",
                    "EMERGENCY_ESCALATION": (
                        "A potentially immediate serious hazard requires "
                        "emergency responders."
                    ),
                },
            }
        },
    }

    started = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{MODEL_URL}/v1/systemone",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not obtain a model assessment. Check that the "
                "Decider server is running on port 8099."
            ),
        ) from exc

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    answers = result.get("answers", {})
    answer = answers.get("response_category", {})
    model_choice = answer.get("choice")

    if not model_choice:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected model response: {json.dumps(result)[:1000]}",
        )

    final_category, rule_applied = apply_demo_safety_rule(
        request.report,
        model_choice,
    )

    probabilities = answer.get("probabilities", {})
    confidence = answer.get("confidence")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO incidents
                (report, model_choice, final_category, model_confidence)
            VALUES (?, ?, ?, ?)
            """,
            (
                request.report,
                model_choice,
                final_category,
                confidence,
            ),
        )
        incident_id = cursor.lastrowid

    return {
        "incident_id": incident_id,
        "model_choice": model_choice,
        "final_category": final_category,
        "rule_applied": rule_applied,
        "probabilities": probabilities,
        "model_confidence": confidence,
        "latency_ms": elapsed_ms,
        "requires_human_review": True,
        "notice": (
            "Demo only. This is not a validated emergency-response system. "
            "For an active hazard, prioritize personal safety and contact "
            "the appropriate emergency authorities."
        ),
    }


@app.get("/api/incidents")
def list_incidents():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, report, model_choice, final_category,
                   model_confidence, created_at
            FROM incidents
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()

    return {"incidents": [dict(row) for row in rows]}
