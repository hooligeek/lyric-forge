"""Two-mode inference: the surrounding agent, or a direct API call.

Mode `agent` is the primary case and needs no credentials. forge renders the
prompt, the agent in the user's editor does the thinking, and the result is
written back with provenance. That is what has been happening in this project all
along; this module only makes the write-back explicit.

Mode `api` is for someone not working inside an agentic editor. forge calls a
provider itself with the user's own key.

Both render the same template from the same library, which is the point — if each
mode carried its own copy of the wording, the same brief would produce different
songs depending on where it ran.

Credentials come from environment variables only, never from a file in the repo
and never from a command-line argument. A key in a file gets committed eventually
and a key in argv shows up in shell history and process listings. The config names
the variable to read; it never holds the value.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config as config_mod

CONFIG_LOCAL = config_mod.REPO_ROOT / "inference.local.yaml"
CONFIG_EXAMPLE = config_mod.REPO_ROOT / "inference.example.yaml"

TIMEOUT_S = 300


class InferenceError(RuntimeError):
    pass


@dataclass
class Provider:
    name: str
    model: str
    api_key_env: str
    max_tokens: int = 8192
    temperature: float | None = None
    base_url: str | None = None

    def key(self) -> str:
        value = os.environ.get(self.api_key_env, "").strip()
        if not value:
            raise InferenceError(
                f"{self.api_key_env} is not set. Export it for this shell:\n"
                f"  export {self.api_key_env}=...\n"
                f"Credentials are read from the environment only — never from a "
                f"file in the repo, and never from a command-line argument."
            )
        # Reject control characters here, and NEVER echo the value while doing it.
        #
        # `.strip()` removes trailing whitespace, but an interior CR or LF
        # survives — and http.client then raises
        # `ValueError: Invalid header value b'sk-...\\nX-Injected: yes'`, with the
        # credential verbatim in the message. That exception is not an HTTPError
        # or a URLError, so it escaped `call()` as an unhandled traceback.
        bad = {c for c in value if ord(c) < 0x20 or ord(c) == 0x7F}
        if bad:
            raise InferenceError(
                f"{self.api_key_env} contains {len(bad)} control character(s) "
                f"(likely a newline from a copy-paste). The value is not shown. "
                f"Re-export it as a single line."
            )
        return value


DEFAULTS = {
    # Anthropic is the default and the model is the current flagship. Creative
    # generation is the workload this tool exists for, so it defaults to quality
    # rather than to the cheapest option; override in inference.local.yaml.
    "anthropic": Provider(
        name="anthropic",
        model="claude-opus-5",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1/messages",
        max_tokens=8192,
    ),
    "openai": Provider(
        name="openai",
        model="gpt-5",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1/chat/completions",
        max_tokens=8192,
    ),
    "google": Provider(
        name="google",
        model="gemini-2.5-pro",
        api_key_env="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/models",
        max_tokens=8192,
    ),
}


def load_provider(name: str | None = None, model: str | None = None) -> Provider:
    """CLI argument, then inference.local.yaml, then the built-in default."""
    settings: dict = {}
    if CONFIG_LOCAL.exists():
        settings = yaml.safe_load(CONFIG_LOCAL.read_text(encoding="utf-8")) or {}

    chosen = name or settings.get("provider") or "anthropic"
    if chosen not in DEFAULTS:
        raise InferenceError(
            f"unknown provider '{chosen}'. Known: {', '.join(DEFAULTS)}"
        )
    base = DEFAULTS[chosen]
    overrides = (settings.get("providers") or {}).get(chosen) or {}

    return Provider(
        name=chosen,
        model=model or overrides.get("model") or base.model,
        api_key_env=overrides.get("api_key_env") or base.api_key_env,
        max_tokens=int(overrides.get("max_tokens") or base.max_tokens),
        temperature=overrides.get("temperature", base.temperature),
        base_url=overrides.get("base_url") or base.base_url,
    )


@dataclass
class Request:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]

    def redacted(self) -> dict[str, Any]:
        """For display. Never show the key, not even truncated — a prefix is
        still a leak into logs and terminal scrollback."""
        safe = {
            k: ("<redacted>" if k.lower() in ("x-api-key", "authorization") else v)
            for k, v in self.headers.items()
        }
        url = self.url
        if "key=" in url:
            url = url.split("key=")[0] + "key=<redacted>"
        body = dict(self.body)
        # The prompt itself can be enormous; show its size rather than repeat it.
        for field_name in ("messages", "contents"):
            if field_name in body:
                body[field_name] = f"<{len(json.dumps(body[field_name]))} bytes of prompt>"
        return {"url": url, "headers": safe, "body": body}


def build_request(provider: Provider, prompt_text: str) -> Request:
    if provider.name == "anthropic":
        body: dict[str, Any] = {
            "model": provider.model,
            "max_tokens": provider.max_tokens,
            "messages": [{"role": "user", "content": prompt_text}],
        }
        if provider.temperature is not None:
            body["temperature"] = provider.temperature
        return Request(
            url=provider.base_url or DEFAULTS["anthropic"].base_url,
            headers={
                "x-api-key": provider.key(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            body=body,
        )

    if provider.name == "openai":
        body = {
            "model": provider.model,
            "max_completion_tokens": provider.max_tokens,
            "messages": [{"role": "user", "content": prompt_text}],
        }
        if provider.temperature is not None:
            body["temperature"] = provider.temperature
        return Request(
            url=provider.base_url or DEFAULTS["openai"].base_url,
            headers={
                "Authorization": f"Bearer {provider.key()}",
                "Content-Type": "application/json",
            },
            body=body,
        )

    if provider.name == "google":
        base = provider.base_url or DEFAULTS["google"].base_url
        body = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"maxOutputTokens": provider.max_tokens},
        }
        if provider.temperature is not None:
            body["generationConfig"]["temperature"] = provider.temperature
        return Request(
            url=f"{base}/{provider.model}:generateContent?key={provider.key()}",
            headers={"Content-Type": "application/json"},
            body=body,
        )

    raise InferenceError(f"no request builder for provider '{provider.name}'")


def extract_text(provider: Provider, payload: dict) -> str:
    try:
        if provider.name == "anthropic":
            return "".join(
                block.get("text", "")
                for block in payload.get("content", [])
                if block.get("type") == "text"
            )
        if provider.name == "openai":
            return payload["choices"][0]["message"]["content"]
        if provider.name == "google":
            parts = payload["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise InferenceError(
            f"could not read a completion out of the {provider.name} response: {exc}. "
            f"Response keys: {list(payload)}"
        ) from exc
    raise InferenceError(f"no response parser for '{provider.name}'")


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "usage": self.usage,
            "chars": len(self.text),
        }


def call(provider: Provider, prompt_text: str) -> Completion:
    req = build_request(provider, prompt_text)
    data = json.dumps(req.body).encode("utf-8")
    request = urllib.request.Request(req.url, data=data, headers=req.headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise InferenceError(
            f"{provider.name} returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise InferenceError(f"could not reach {provider.name}: {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001 — deliberate, see below
        # Catch-all, and `from None` so the original traceback is discarded.
        #
        # Anything raised between here and the wire has had the credential in
        # scope: http.client puts the header value into its own ValueError, and
        # any such exception propagating would print the key. A narrow except
        # clause here is a credential-disclosure bug, not tidy error handling.
        # The type name is safe to report; the message is not.
        raise InferenceError(
            f"{provider.name} request failed with {type(exc).__name__}. "
            f"The message is withheld because exceptions raised while building "
            f"the request can contain the credential."
        ) from None

    usage = payload.get("usage") or payload.get("usageMetadata") or {}
    return Completion(
        text=extract_text(provider, payload),
        provider=provider.name,
        model=provider.model,
        usage=usage if isinstance(usage, dict) else {},
    )


# ---------------------------------------------------------------------------
# where output lands
# ---------------------------------------------------------------------------
def default_output(cfg, prompt_outputs: str, band: str | None, track: str | None) -> Path | None:
    """A conventional destination per output type, so neither the operator nor an
    agent has to invent one and put it somewhere the rest of the tool cannot find."""
    if prompt_outputs == "lyric-body" and band and track:
        return cfg.bands[band].dir / "drafts" / f"{track}.md"
    if prompt_outputs == "lyric-sheet" and band and track:
        return cfg.bands[band].dir / "lyrics" / f"{track}.md"
    if prompt_outputs == "findings" and band and track:
        return cfg.bands[band].dir / "reviews" / f"{track}-judgement.md"
    if prompt_outputs == "band-kit" and band:
        return cfg.bands[band].dir / "derived-kit.md"
    return None


def record_provenance(
    cfg,
    band: str,
    track: str,
    rendered,
    mode: str,
    model: str | None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Which prompt, which version, which model, which mode.

    Provenance is recorded either way — it is known at render time. The stage is
    only stamped once the artefact actually exists on disk. In agent mode the
    output is written by the agent *after* this command returns, so stamping
    `draft` unconditionally would claim a draft that is not there yet.
    """
    from . import ledger as ledger_mod
    from . import lifecycle as lc_mod

    rows = ledger_mod.load_band_tracks(cfg.bands[band])
    row = next((t for t in rows if t.get("slug") == track), None)
    if row is None:
        raise InferenceError(f"no track '{track}' in {band}")

    prov = row.setdefault("provenance", {})
    prov["prompt_template"] = rendered.prompt_id
    prov["prompt_version"] = rendered.version
    prov["model"] = f"{mode}:{model}" if model else f"{mode}:surrounding-agent"

    stamped = False
    if output_path is not None and output_path.exists():
        prov["draft"] = output_path.relative_to(config_mod.REPO_ROOT).as_posix()
        lc_mod.stamp(
            row, "draft", by=f"forge infer --mode {mode}",
            note=f"{rendered.ref} via {model or 'surrounding agent'}",
        )
        stamped = True

    ledger_mod.save_band_tracks(cfg.bands[band], rows)
    return {
        "track_id": row.get("id"),
        "prompt": rendered.ref,
        "model": prov["model"],
        "stage_stamped": stamped,
        "draft": prov.get("draft"),
    }
