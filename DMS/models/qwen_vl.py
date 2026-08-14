"""通过 HTTP 调用远端 VLM（OpenRouter / OpenAI 等兼容接口）。"""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any, Optional

import numpy as np
import requests
from PIL import Image

_PRESET_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

_DEFAULT_MODELS = {
    "openrouter": "qwen/qwen2.5-vl-7b-instruct",
    "openai": "gpt-4o",
    "dashscope": "qwen2.5-vl-7b-instruct",
}


def _jpeg_b64(image: np.ndarray) -> str:
    img = Image.fromarray(image)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _detect_provider(provider: str | None) -> str:
    if provider:
        return provider.strip().lower()
    env = (os.environ.get("VLM_PROVIDER") or "").strip().lower()
    if env:
        return env
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("QWEN_BASE_URL"):
        return "openai"
    if os.environ.get("DASHSCOPE_API_KEY"):
        return "dashscope"
    return ""


def _resolve_base_url(base_url: str | None, provider: str) -> str:
    if base_url:
        return base_url.rstrip("/")
    env = (os.environ.get("QWEN_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").rstrip("/")
    if env:
        return env
    if provider in _PRESET_BASE_URLS:
        return _PRESET_BASE_URLS[provider]
    return ""


def _resolve_api_key(api_key: str | None, provider: str) -> str:
    if api_key is not None and api_key != "":
        return api_key
    # 按 provider 优先读对应 key
    order = {
        "openrouter": ("OPENROUTER_API_KEY", "QWEN_API_KEY", "OPENAI_API_KEY"),
        "openai": ("OPENAI_API_KEY", "QWEN_API_KEY"),
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "OPENAI_API_KEY"),
    }.get(provider, ("QWEN_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY"))
    for name in order:
        val = os.environ.get(name)
        if val:
            return val
    return ""


class QwenVLWrapper:
    """
    只走 HTTP Chat Completions（推荐 OpenRouter / OpenAI）。

    OpenRouter:
      export OPENROUTER_API_KEY=sk-or-...
      # 可选: export VLM_PROVIDER=openrouter
      # 可选: export QWEN_MODEL=qwen/qwen2.5-vl-7b-instruct

    OpenAI:
      export OPENAI_API_KEY=sk-...
      export VLM_PROVIDER=openai
      # 可选: export QWEN_MODEL=gpt-4o
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        max_retry: int = 3,
        timeout: float = 120.0,
    ):
        self.provider = _detect_provider(provider)
        self.base_url = _resolve_base_url(base_url, self.provider)
        if not self.base_url:
            raise RuntimeError(
                "未配置 VLM。请任选其一：\n"
                "  export OPENROUTER_API_KEY=sk-or-...\n"
                "  export OPENAI_API_KEY=sk-... && export VLM_PROVIDER=openai\n"
                "  或传入 base_url= / provider="
            )

        self.api_key = _resolve_api_key(api_key, self.provider or "openrouter")
        if not self.api_key:
            raise RuntimeError(
                "未找到 API Key。请设置 OPENROUTER_API_KEY 或 OPENAI_API_KEY（或 QWEN_API_KEY）。"
            )

        default_model = _DEFAULT_MODELS.get(self.provider, "qwen/qwen2.5-vl-7b-instruct")
        if "openrouter.ai" in self.base_url and self.provider != "openai":
            default_model = _DEFAULT_MODELS["openrouter"]
        self.model = model_name or os.environ.get("QWEN_MODEL") or default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retry = max_retry
        self.timeout = timeout
        self.total_tokens = 0

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if "openrouter.ai" in self.base_url:
            h.setdefault("HTTP-Referer", os.environ.get("OPENROUTER_REFERER", "https://localhost"))
            h.setdefault("X-Title", os.environ.get("OPENROUTER_TITLE", "DMS-AndroidWorld"))
        return h

    def health_check(self) -> dict[str, Any]:
        models_url = f"{self.base_url}/models"
        try:
            r = requests.get(models_url, headers=self._headers(), timeout=15)
            return {
                "ok": r.ok,
                "url": models_url,
                "status": r.status_code,
                "body": r.text[:500],
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "url": models_url, "error": repr(e)}

    def predict(self, text_prompt: str) -> tuple[str, Optional[bool], Any]:
        return self.predict_mm(text_prompt, [])

    def predict_mm(self, text_prompt: str, images: list[np.ndarray]) -> tuple[str, Optional[bool], Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{_jpeg_b64(image)}"},
                }
            )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        delay = 1.0
        last_err: Any = None
        for _ in range(self.max_retry):
            try:
                resp = requests.post(
                    self.chat_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                )
                data = resp.json()
                if resp.ok and "choices" in data:
                    usage = data.get("usage") or {}
                    self.total_tokens += int(usage.get("total_tokens") or 0)
                    return data["choices"][0]["message"]["content"], True, data
                last_err = data
            except Exception as e:  # noqa: BLE001
                last_err = e
            time.sleep(delay)
            delay *= 2
        return f"Error calling LLM via HTTP: {last_err}", None, last_err
