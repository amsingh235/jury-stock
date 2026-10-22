"""LLM router: JSON-only completions with retry, schema validation and provider fallback."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx
import yaml
from pydantic import BaseModel, ValidationError

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "llm.yaml"


class LLMError(RuntimeError):
    """Raised when every provider fails to return valid JSON."""


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from the repo's .env into os.environ (existing vars win)."""
    path = path or CONFIG_PATH.parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text``, tolerating code fences and surrounding prose."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


@dataclass
class Provider:
    """One chat-completion backend; ``call(system, user) -> text``."""

    name: str
    model: str
    call: Callable[[str, str], str]


def _groq_call(cfg: dict, p: dict, key: str) -> Callable[[str, str], str]:
    """Build a Groq (OpenAI-compatible) caller in JSON mode."""
    def call(system: str, user: str) -> str:
        """POST one chat completion to Groq and return the message text."""
        r = httpx.post(p["url"], timeout=cfg["timeout_s"], headers={"Authorization": f"Bearer {key}"}, json={
            "model": p["model"], "temperature": cfg["temperature"], "max_tokens": cfg["max_output_tokens"],
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    return call


def _gemini_call(cfg: dict, p: dict, key: str) -> Callable[[str, str], str]:
    """Build a Gemini generateContent caller in JSON mode."""
    def call(system: str, user: str) -> str:
        """POST one generateContent request to Gemini and return the text."""
        r = httpx.post(p["url"].format(model=p["model"]), timeout=cfg["timeout_s"],
                       headers={"x-goog-api-key": key}, json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": cfg["temperature"], "maxOutputTokens": cfg["max_output_tokens"],
                                 "responseMimeType": "application/json"},
        })
        r.raise_for_status()
        return "".join(part.get("text", "") for part in r.json()["candidates"][0]["content"]["parts"])
    return call


BUILDERS = {"groq": _groq_call, "gemini": _gemini_call}


@dataclass
class Router:
    """Try providers in order; validate each reply against a pydantic schema."""

    providers: list[Provider]
    retries: int = 2
    backoff_s: float = 2.0
    log: list[dict] = field(default_factory=list)

    @classmethod
    def from_config(cls) -> "Router":
        """Build a router from config/llm.yaml using whichever API keys are set."""
        load_env()
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        providers = []
        for p in cfg["providers"]:
            key = os.environ.get(p["api_key_env"])
            if key:
                providers.append(Provider(p["name"], p["model"], BUILDERS[p["name"]](cfg, p, key)))
        if not providers:
            raise LLMError("No LLM API keys set: add GROQ_API_KEY and/or GEMINI_API_KEY to .env")
        return cls(providers, retries=cfg["retries_per_provider"])

    def complete(self, system: str, user: str, schema: type[BaseModel]) -> tuple[dict, str]:
        """Return (validated JSON dict, provider name); raise LLMError if all providers fail."""
        errors = []
        for prov in self.providers:
            prompt = user
            for attempt in range(self.retries):
                t0 = time.time()
                try:
                    data = schema.model_validate(extract_json(prov.call(system, prompt))).model_dump()
                    self.log.append({"provider": prov.name, "ok": True, "s": round(time.time() - t0, 2)})
                    return data, prov.name
                except (ValidationError, json.JSONDecodeError) as e:
                    # Feed the validation error back so the model can repair its output.
                    prompt = f"{user}\n\nYour previous reply was invalid: {str(e)[:800]}\nReturn ONLY corrected JSON."
                    errors.append(f"{prov.name}: invalid JSON ({type(e).__name__})")
                except httpx.HTTPStatusError as e:
                    errors.append(f"{prov.name}: HTTP {e.response.status_code}")
                    if e.response.status_code in (400, 401, 403, 404):
                        break  # configuration problem; retrying won't help
                    time.sleep(self.backoff_s * 2 ** attempt)
                except (httpx.HTTPError, KeyError, IndexError) as e:
                    errors.append(f"{prov.name}: {type(e).__name__}: {e}")
                    time.sleep(self.backoff_s * 2 ** attempt)
                self.log.append({"provider": prov.name, "ok": False, "s": round(time.time() - t0, 2)})
        raise LLMError("; ".join(errors))
