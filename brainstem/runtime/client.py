"""Small standard-library client used by the CLI to reach the runtime service."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RuntimeUnavailable(RuntimeError):
    pass


class RuntimeClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8280") -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> Any:
        request = Request(
            self.base_url + path,
            method=method,
            headers={"Content-Type": "application/json"},
            data=json.dumps(data).encode() if data is not None else None,
        )
        try:
            with urlopen(request, timeout=125) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            detail = json.loads(exc.read()).get("detail", str(exc))
            raise RuntimeError(detail) from exc
        except (URLError, OSError) as exc:
            raise RuntimeUnavailable(
                f"BRAINSTEM runtime unavailable at {self.base_url}"
            ) from exc

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health")

    def models(self) -> list[dict[str, Any]]:
        return self.request("GET", "/models")

    def create_session(
        self, model: str | None = None, repository: str | None = None
    ) -> dict[str, Any]:
        return self.request(
            "POST", "/sessions", {"model": model, "repository": repository}
        )

    def session(self, session_id: str) -> dict[str, Any]:
        return self.request("GET", f"/sessions/{session_id}")

    def chat(self, session_id: str, message: str) -> dict[str, Any]:
        return self.request(
            "POST", "/chat", {"session_id": session_id, "message": message}
        )

    def switch(self, session_id: str, model: str) -> dict[str, Any]:
        return self.request("POST", f"/sessions/{session_id}/model", {"model": model})
