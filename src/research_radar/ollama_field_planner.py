from __future__ import annotations

import json
import re
from typing import Any

import requests

from src.research_radar.models import ResearchField


class OllamaFieldPlanner:
    """Expand a plain-language research field into focused OpenAlex queries."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:8b",
        timeout_seconds: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.preferred_model = model
        self.timeout_seconds = max(int(timeout_seconds), 1)
        self.session = session or requests.Session()

    def plan(self, field: ResearchField) -> dict[str, list[str]]:
        model = self.resolve_model()
        response = self.session.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "think": False,
                "keep_alive": "30m",
                "options": {"temperature": 0.1},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You plan academic literature searches. Return JSON only. "
                            "All search terms must be English, concise, timeless, and suitable for OpenAlex full-text search. "
                            "Do not include years, Boolean query syntax, explanations, or duplicate phrases."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Research field: {field.name}\n"
                            f"Description: {field.description or 'Not provided'}\n"
                            "Create a focused search plan with 3-6 core_keywords, 2-4 intent_queries, "
                            "and up to 4 optional_keywords. Intent queries should describe papers the researcher wants to find.\n"
                            'Return exactly: {"core_keywords": ["..."], "intent_queries": ["..."], '
                            '"optional_keywords": ["..."]}'
                        ),
                    },
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = str((payload.get("message") or {}).get("content") or "")
        parsed = _parse_json_object(content)
        plan = {
            "core_keywords": _clean_strings(parsed.get("core_keywords"), limit=6),
            "intent_queries": _clean_strings(parsed.get("intent_queries"), limit=4),
            "optional_keywords": _clean_strings(parsed.get("optional_keywords"), limit=4),
        }
        if not plan["core_keywords"] and not plan["intent_queries"]:
            raise ValueError("Ollama returned an empty research field plan")
        plan["model"] = model  # type: ignore[assignment]
        return plan

    def resolve_model(self) -> str:
        response = self.session.get(f"{self.base_url}/api/tags", timeout=min(self.timeout_seconds, 5))
        response.raise_for_status()
        names = [str(item.get("name") or "") for item in response.json().get("models", []) if item.get("name")]
        if not names:
            raise RuntimeError("Ollama is running but no local model is installed")
        if self.preferred_model in names:
            return self.preferred_model
        preferred_base = self.preferred_model.split(":", 1)[0]
        for name in names:
            if name.split(":", 1)[0] == preferred_base:
                return name
        for name in names:
            if "qwen" in name.lower():
                return name
        return names[0]


def needs_field_planning(field: ResearchField) -> bool:
    terms = [*field.core_keywords, *field.intent_queries]
    if not terms:
        return True
    name = _normalized(field.name)
    return bool(name) and all(_normalized(term) == name for term in terms)


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("Ollama did not return a JSON object")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Ollama did not return a JSON object")
    return parsed


def _clean_strings(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(str(item or "").split()).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _normalized(value: str) -> str:
    return " ".join(str(value or "").casefold().split())
