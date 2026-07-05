import json
import re
from typing import Any

import ollama

from app.config import Settings

SYSTEM_PROMPT = """You are an information extractor for meeting minutes.
Return ONLY JSON with keys: decisions, actions, accomplishments, risks, issues.
Each item should include:
- title (short), detail (1-3 sentences), owner (string or empty)
- due_date (YYYY-MM-DD or empty) for actions; date for decisions/accomplishments
- severity 1..5 for risk/issue (optional), priority 1..5 for action (optional)
- evidence_span: {"start": int, "end": int} (use -1 if unknown)
- confidence: float in [0,1]
Output compact JSON. No prose.
"""

PLAN_PROMPT = """You are a project program lead. Generate a concise, actionable plan for the next 7 days.
Be specific and pragmatic. Use the inputs below.

PROFILE (preferences/tone):
{profile}

CONTEXT (open/overdue actions, risks/issues, recent decisions/accomplishments):
{context}

Return a short bulleted plan with owners and due dates when possible. Keep it tight (5–8 bullets).
"""


def try_parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"decisions": [], "actions": [], "accomplishments": [], "risks": [], "issues": []}


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = ollama.Client(host=settings.ollama_host)

    def embed(self, text_input: str) -> list[float]:
        resp = self._client.embeddings(model=self.settings.ollama_embed_model, prompt=text_input)
        return resp["embedding"]

    def extract(self, text_input: str) -> dict[str, Any]:
        prompt = f"{SYSTEM_PROMPT}\n\nTEXT:\n{text_input}\n\nJSON:"
        out = self._client.generate(
            model=self.settings.ollama_llm_model,
            prompt=prompt,
            options=self.settings.llm_options,
        )
        return try_parse_json(out["response"])

    def generate_plan(self, profile: str, context: str) -> str:
        plan_prompt = PLAN_PROMPT.format(profile=profile or "standard PM tone", context=context)
        resp = self._client.generate(
            model=self.settings.ollama_llm_model,
            prompt=plan_prompt,
            options=self.settings.llm_options,
        )
        return resp.get("response", "").strip()

    def ping(self) -> bool:
        try:
            self._client.list()
            return True
        except Exception:
            return False
