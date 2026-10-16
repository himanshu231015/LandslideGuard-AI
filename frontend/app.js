
const form = document.querySelector("#incident-form");
const report = document.querySelector("#report");
const statusBox = document.querySelector("#status");
const results = document.querySelector("#results");
const analyzeButton = document.querySelector("#analyze");

// Format the Bedrock explanation as readable plain text.
// Never render model-generated content as HTML.
function formatExplanation(text) {
  return String(text ?? "")
    .replace(/\r\n/g, "\n")
    // Move Markdown headings onto separate lines.
    .replace(/#{1,6}\s*/g, "\n\n")
    // Separate numbered sections such as "1. What was reported".
    .replace(/(\S)\s+(\d+\.\s+)/g, "$1\n\n$2")
    // Put dash-style bullet items on separate lines.
    .replace(/\s+-\s+(?=[A-Z*])/g, "\n- ")
    // Remove Markdown bold markers.
    .replace(/\*\*(.*?)\*\*/g, "$1")
    // Clean up whitespace and excess blank lines.
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// Load an ambiguous sample incident.
document.querySelector("#sample").addEventListener("click", () => {
  report.value =
    "Heavy rain has been reported near a mountain road. There are no confirmed injuries, and the extent of the blockage is unknown.";
});

// Analyze the incident using the FastAPI backend.
form.addEventListener("submit", async (event) => {
  event.preventDefault();

  results.classList.add("hidden");
  analyzeButton.disabled = true;
  statusBox.textContent =
    "Calling Decider 2B and Amazon Bedrock...";

  try {
    const response = await fetch("/api/incidents/analyze", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        report: report.value.trim()
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Analysis failed");
    }

    const decision = data.decision;

    // Decision details.
    document.querySelector("#category").textContent =
      decision.category;

    document.querySelector("#confidence").textContent =
      `${(decision.confidence * 100).toFixed(1)}%`;

    document.querySelector("#latency").textContent =
      `${decision.latency_ms} ms`;

    document.querySelector("#review").textContent =
      decision.needs_review ? "Required" : "Not flagged";

    // Safety information.
    document.querySelector("#safety").textContent =
      decision.safety_note ||
      (decision.safety_override
        ? "A safety override was triggered."
        : "No deterministic safety override was triggered.");

    // Bedrock explanation.
    document.querySelector("#explanation").textContent =
      formatExplanation(data.explanation);

    document.querySelector("#bedrock-status").textContent =
      `Bedrock status: ${data.bedrock_status}`;

    document.querySelector("#notice").textContent =
      data.prototype_notice;

    results.classList.remove("hidden");
    statusBox.textContent =
      "Analysis complete. Verify the result.";
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
  } finally {
    analyzeButton.disabled = false;
  }
});
