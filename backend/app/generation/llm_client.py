"""Client abstrait pour modèle de langage exécuté strictement en local."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

DEFAULT_OLLAMA_URL = os.getenv("LABMIND_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_LLM_MODEL = os.getenv("LABMIND_LLM_MODEL", "qwen2.5:3b")
DEFAULT_LLM_TIMEOUT = float(os.getenv("LABMIND_LLM_TIMEOUT", "120.0"))
DEFAULT_NUM_CTX = int(os.getenv("LABMIND_LLM_NUM_CTX", "4096"))
DEFAULT_NUM_PREDICT = int(os.getenv("LABMIND_LLM_NUM_PREDICT", "900"))
DEFAULT_TEMPERATURE = float(os.getenv("LABMIND_LLM_TEMPERATURE", "0.15"))

_PREFERRED_MODELS: tuple[str, ...] = (
    "qwen2.5:3b",
    "qwen3:4b",
    "qwen2.5:7b",
    "qwen2.5:3b-instruct",
    "qwen2.5:1.5b",
)
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalLLMError(RuntimeError):
    """Erreur technique lors de l'appel au modèle local."""


@runtime_checkable
class LocalLLMClient(Protocol):
    """Interface minimale d'un modèle de langage local."""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Retourne la réponse textuelle brute du modèle."""
        ...


class OllamaLLMClient:
    """Client HTTP vers une instance Ollama strictement locale (127.0.0.1/localhost)."""

    def __init__(
        self,
        model: str = DEFAULT_LLM_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout_seconds: float = DEFAULT_LLM_TIMEOUT,
        num_ctx: int = DEFAULT_NUM_CTX,
        num_predict: int = DEFAULT_NUM_PREDICT,
        temperature: float = DEFAULT_TEMPERATURE,
        allow_remote: bool = False,
    ) -> None:
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if not allow_remote and host not in _LOCAL_HOSTS:
            raise ValueError(
                f"URL non autorisée ({base_url}) : le LLM doit s'exécuter localement "
                "sur localhost ou 127.0.0.1."
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.temperature = temperature

    def _detect_installed_model(self) -> str | None:
        req = urllib.request.Request(url=f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list) or not models:
            return None
        installed = [
            str(item.get("name"))
            for item in models
            if isinstance(item, dict) and item.get("name")
        ]
        if not installed:
            return None
        for preferred in _PREFERRED_MODELS:
            for name in installed:
                if name == preferred or name.startswith(preferred):
                    return name
        return installed[0]

    def _post_chat(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": model_name,
            "stream": False,
            "keep_alive": "15m",
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "top_p": 0.85,
                "repeat_penalty": 1.12,
                "num_ctx": self.num_ctx,
                "num_predict": max_tokens if max_tokens is not None else self.num_predict,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LocalLLMError("Réponse Ollama inattendue : champ 'message.content' absent.")
        return message["content"]

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        try:
            return self._post_chat(self.model, system_prompt, user_prompt, max_tokens=max_tokens)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                fallback_model = self._detect_installed_model()
                if fallback_model and fallback_model != self.model:
                    self.model = fallback_model
                    try:
                        return self._post_chat(
                            self.model,
                            system_prompt,
                            user_prompt,
                            max_tokens=max_tokens,
                        )
                    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as retry_exc:
                        raise LocalLLMError(
                            f"Échec de communication avec Ollama ({self.base_url}) : {retry_exc}"
                        ) from retry_exc
            raise LocalLLMError(
                f"Échec HTTP Ollama ({self.base_url}) : {exc}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LocalLLMError(
                f"Échec de communication avec Ollama ({self.base_url}) : {exc}"
            ) from exc
