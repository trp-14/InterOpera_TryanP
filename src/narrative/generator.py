"""Generate narrative commentary from already-computed figures (BUILD_PLAN.md Step 8).

Receives ONLY the computed figures JSON — never the raw CSV or the
guidelines PDF (CLAUDE.md section 9: "Narrative commentary | Yes | receives
only computed figures"). This is the only module in the project allowed to
import the anthropic SDK (CLAUDE.md section 3.2).
"""
from __future__ import annotations

import json
import os

import anthropic

_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = """You are writing a short compliance narrative for a portfolio report.
You are given a JSON list of already-computed compliance figures. Write 2-4 sentences of
prose commentary, focused on any breaches (status "BREACH") or at-limit figures
(status "AT LIMIT") and what should happen next.

Rules:
- Use ONLY the numbers given to you in the JSON, quoted EXACTLY as formatted
  (e.g. "35.0%", "58.3%", "SGD 38,790 / bp") - never compute, round, or restate
  a number differently than it appears.
- Do not invent any figure, date, or amount that is not in the JSON.
- You may name the figure and describe its status/limit/utilization, but state
  no fact not present in the data you were given.
"""


def generate_narrative(figures_json: list[dict], api_key: str | None = None) -> str | None:
    """Returns None when no API key is available — this is what keeps `run`
    fully functional with ANTHROPIC_API_KEY unset (CLAUDE.md section 3.2's
    acceptance test: figures are complete and identical either way, only the
    narrative is empty).
    """
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(figures_json, sort_keys=True)}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
