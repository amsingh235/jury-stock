"""LLM router: JSON-only completions with retry, schema validation and provider fallback."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
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
    """Parse the first JSON object in ``text``, tolerating code fences, surrounding prose, and a
    premature closing brace (long model replies sometimes close the object before their last fields).
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    candidate = text[start:]
    for _ in range(3):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            rest = candidate[e.pos:].lstrip()
            if e.msg.startswith("Extra data") and rest.startswith(","):
                # "{...}, \"more\": ..." -> drop the early "}" so the trailing fields stay inside.
                close = candidate.rfind("}", 0, e.pos)
                candidate = candidate[:close] + candidate[close + 1:]
                continue
            if e.msg.startswith("Extra data"):
                return json.loads(candidate[:e.pos])  # valid object followed by prose
            end = candidate.rfind("}")
            if end > 0 and end + 1 < len(candidate):
                candidate = candidate[:end + 1]
                continue
            raise
    return json.loads(candidate)


@dataclass
class Provider:
    """One chat-completion backend; ``call(system, user) -> text``."""

    name: str
    model: str
    call: Callable[..., str]


def _groq_call(cfg: dict, p: dict, key: str) -> Callable[..., str]:
    """Build a Groq (OpenAI-compatible) caller in JSON mode."""
    def call(system: str, user: str, image: Path | None = None) -> str:
        """POST one chat completion to Groq and return the message text (text-only: images are skipped)."""
        if image:
            user += "\n\n(The chart image could not be shown to this model; work from the chart engine data.)"
        r = httpx.post(p["url"], timeout=cfg["timeout_s"], headers={"Authorization": f"Bearer {key}"}, json={
            "model": p["model"], "temperature": cfg["temperature"], "max_tokens": cfg["max_output_tokens"],
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    return call


def _gemini_call(cfg: dict, p: dict, key: str) -> Callable[..., str]:
    """Build a Gemini generateContent caller in JSON mode."""
    def call(system: str, user: str, image: Path | None = None) -> str:
        """POST one generateContent request to Gemini (with the chart PNG inline if given) and return the text."""
        parts = [{"text": user}]
        if image:
            parts.append({"inline_data": {"mime_type": "image/png",
                                          "data": base64.b64encode(Path(image).read_bytes()).decode()}})
        r = httpx.post(p["url"].format(model=p["model"]), timeout=cfg["timeout_s"],
                       headers={"x-goog-api-key": key}, json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": cfg["temperature"], "maxOutputTokens": cfg["max_output_tokens"],
                                 "responseMimeType": "application/json"},
        })
        r.raise_for_status()
        return "".join(part.get("text", "") for part in r.json()["candidates"][0]["content"]["parts"])
    return call


def claude_cli_call(model: str = "opus", timeout_s: int = 300) -> Callable[..., str]:
    """Build a caller that runs one headless Claude Code turn on the user's Claude subscription.

    Tools and MCP servers are disabled, so the model can only answer; the user prompt goes
    through stdin to stay clear of Windows command-line length limits.
    """
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("Claude Code CLI not found: install it and run `claude` once to log in")

    def call(system: str, user: str, image: Path | None = None) -> str:
        """Run `claude -p` and return the reply text.

        With ``image``, the only tool enabled is Read, run from the image's folder, so the model
        can open the chart PNG and nothing else.
        """
        tools, cwd = "", None
        if image:
            image = Path(image).resolve()
            tools, cwd = "Read", str(image.parent)
            user += f"\n\nCHART IMAGE: open {image} with the Read tool and study it before answering."
        proc = subprocess.run(
            [exe, "-p", "--model", model, "--output-format", "json", "--tools", tools,
             "--system-prompt", system, "--no-session-persistence", "--strict-mcp-config"],
            input=user, capture_output=True, text=True, encoding="utf-8", timeout=timeout_s, cwd=cwd,
        )
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise LLMError(f"claude CLI exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}")
        if out.get("is_error"):
            raise LLMError(f"claude CLI error: {out.get('subtype')} {str(out.get('result'))[:300]}")
        return out["result"]
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
    def opus(cls) -> "Router":
        """Router that sends every agent call to Opus via the Claude Code CLI (subscription)."""
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["claude_cli"]
        return cls([Provider("claude_cli", cfg["model"], claude_cli_call(cfg["model"], cfg["timeout_s"]))], retries=2)

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

    def complete(self, system: str, user: str, schema: type[BaseModel],
                 image: Path | None = None) -> tuple[dict, str]:
        """Return (validated JSON dict, provider name); raise LLMError if all providers fail.

        ``image`` (a chart PNG) is passed to providers that can see images.
        """
        errors = []
        for prov in self.providers:
            prompt = user
            for attempt in range(self.retries):
                t0 = time.time()
                try:
                    reply = prov.call(system, prompt, image) if image else prov.call(system, prompt)
                    data = schema.model_validate(extract_json(reply)).model_dump()
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
                except (httpx.HTTPError, KeyError, IndexError, LLMError, subprocess.TimeoutExpired) as e:
                    errors.append(f"{prov.name}: {type(e).__name__}: {e}")
                    time.sleep(self.backoff_s * 2 ** attempt)
                self.log.append({"provider": prov.name, "ok": False, "s": round(time.time() - t0, 2)})
        raise LLMError("; ".join(errors))
