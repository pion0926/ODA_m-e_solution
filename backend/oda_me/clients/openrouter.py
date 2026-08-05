from __future__ import annotations

from ..core import *

class OpenRouterClient:
    """OpenRouter 호출을 위한 최소 클라이언트."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("OPENROUTER_MODEL", "google/gemini-3.1-flash-lite")
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.app_title = os.getenv("OPENROUTER_APP_TITLE", "ODA ImpactOps Prototype")
        self.referer = os.getenv("OPENROUTER_REFERER", "http://127.0.0.1:8001")

    def status(self) -> dict:
        return {
            "provider": "openrouter",
            "configured": bool(self.api_key),
            "model": self.model,
            "baseUrl": self.base_url,
            "appTitle": self.app_title,
            "referer": self.referer,
        }

    def build_messages(self, task: str, context: dict) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a senior Korean ODA evaluation team lead with deep KOICA final evaluation experience. "
                    "Write in formal Korean report style using '~함', '~음', '~평가됨'. "
                    "Use OECD DAC criteria, KOICA final evaluation FAQ guidance, provided templates, sample reports as RAG references, "
                    "and uploaded evidence excerpts. Treat templates and samples as structure/style guidance only; never copy their text verbatim. "
                    "Write a new final report grounded in the current project's data, uploaded evidence, and explicit gaps. Distinguish confirmed evidence from gaps. "
                    "Do not invent unverifiable facts; when evidence is insufficient, write concrete follow-up data requests."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"task": task, "context": context}, ensure_ascii=False),
            },
        ]

    def request_chat_completion(self, messages: list[dict]) -> dict:
        if not self.api_key:
            return {"implemented": True, "ok": False, "error": "OPENROUTER_API_KEY is not configured", "status": self.status()}
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": self.referer,
                "X-Title": self.app_title,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=45) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"implemented": True, "ok": True, "status": self.status(), "content": content, "raw": data}
        except error.URLError as exc:
            return {"implemented": True, "ok": False, "status": self.status(), "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"implemented": True, "ok": False, "status": self.status(), "error": str(exc)}


OPENROUTER = OpenRouterClient()

