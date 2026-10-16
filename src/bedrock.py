import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def explain_incident(
    report: str,
    category: str,
    confidence: float,
    safety_note: str | None = None,
) -> str:
    """Generate an explanation using Amazon Bedrock."""
    region = os.getenv("AWS_REGION", "us-east-1")
    model_id = os.getenv(
        "BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0"
    )

    client = boto3.client("bedrock-runtime", region_name=region)

    safety_context = safety_note or "No override was triggered."

    prompt = f"""
You are the reporting assistant for LandslideGuard AI.

This is a prototype decision-support application, not an emergency
authority. Do not claim to have verified real-time weather, road,
or rescue information.

Incident report:
{report}

Structured decision from Strands Decider 2B:
Category: {category}
Confidence: {confidence:.3f}
Safety context: {safety_context}

Produce a concise report with:
1. What was reported.
2. Why the category is relevant, without inventing facts.
3. Conservative next steps for authorized responders.
4. What information is still missing.

Never claim that emergency services have been contacted.
If immediate danger is reported, tell the reader to contact local
emergency services or authorized responders.
"""

    try:
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": 500,
                "temperature": 0.2,
            },
        )
        return "".join(
            block.get("text", "")
            for block in response["output"]["message"]["content"]
            if "text" in block
        ).strip()

    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(
            "Amazon Bedrock could not generate the explanation. "
            "Check AWS credentials, region, model availability, "
            "and IAM permissions."
        ) from exc
