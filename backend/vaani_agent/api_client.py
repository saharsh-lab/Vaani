"""HTTP client for the Vaani API, used by every agent worker (CLI, voice, WhatsApp)."""

from typing import Any

import httpx

from vaani_agent.tools import TOOL_NAMES


class VaaniApi:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        business_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
            transport=transport,
        )
        if business_id:
            self.set_business(business_id)

    def set_business(self, business_id: str) -> None:
        self.http.headers["X-Business-Id"] = str(business_id)

    async def __aenter__(self) -> "VaaniApi":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.http.aclose()

    async def _json(self, method: str, url: str, **kwargs: Any) -> Any:
        response = await self.http.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    async def resolve_business(self, slug: str) -> dict:
        return await self._json("GET", f"/v1/businesses/{slug}")

    async def context(self) -> dict:
        return await self._json("GET", "/v1/agent/context")

    async def start_conversation(self, channel: str, customer_phone: str | None = None) -> dict:
        body = {"channel": channel, "customer_phone": customer_phone}
        return await self._json("POST", "/v1/conversations", json=body)

    async def resume_conversation(
        self, channel: str, customer_phone: str, idle_minutes: int = 30
    ) -> dict:
        body = {"channel": channel, "customer_phone": customer_phone, "idle_minutes": idle_minutes}
        return await self._json("POST", "/v1/conversations/resume", json=body)

    async def save_turn(self, conversation_id: str, **turn: Any) -> None:
        await self._json("POST", f"/v1/conversations/{conversation_id}/turns", json=turn)

    async def end_conversation(self, conversation_id: str, **fields: Any) -> None:
        await self._json("POST", f"/v1/conversations/{conversation_id}/end", json=fields)

    async def call_tool(self, name: str, args: dict) -> dict:
        """Run a tool. Never raises: errors come back as a dict the LLM can act on."""
        if name not in TOOL_NAMES:
            return {"error": "unknown_tool", "message": f"There is no tool called {name}."}
        try:
            response = await self.http.post(f"/v1/tools/{name}", json=args)
        except httpx.HTTPError:
            return {
                "error": "tool_unavailable",
                "message": "The booking system isn't responding. Apologise and offer a callback.",
            }
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_success:
            return data
        if isinstance(data.get("detail"), list):  # FastAPI request validation error
            problems = "; ".join(
                f"{'.'.join(str(p) for p in d['loc'][1:])}: {d['msg']}" for d in data["detail"]
            )
            return {"error": "invalid_arguments", "message": problems}
        return {"error": data.get("error", f"http_{response.status_code}"), **data}
