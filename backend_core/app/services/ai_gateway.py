"""Шлюз интеграции с интеллектуальным микросервисом.

Реализует паттерны надежной интеграции ИИ: тайм-аут, повтор с экспоненциальной
задержкой и автоматический выключатель (Circuit Breaker), который при серии
отказов временно прекращает обращения и сразу возвращает ответ 503.
"""
import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.core.logging_setup import request_id_var

logger = logging.getLogger("backend_core.ai_gateway")


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.reset_timeout:
            return "half-open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        half_open = self.state == "half-open"
        self.failures += 1
        if half_open or self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


class AIGateway:
    RETRIES = 2
    BACKOFF = 0.5

    def __init__(self) -> None:
        self.breaker = CircuitBreaker()

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=settings.AI_SERVICE_URL, verify=settings.TLS_CA_FILE, timeout=timeout)

    async def _post(self, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not self.breaker.allow():
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Интеллектуальный сервис временно отключен после серии сбоев. Повторите попытку через 30 секунд.",
            )
        headers = {"X-Request-ID": request_id_var.get()}
        last_error: Exception | None = None
        for attempt in range(self.RETRIES + 1):
            try:
                async with self._client(timeout) as client:
                    response = await client.post(path, json=payload, headers=headers)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError("ошибка сервера", request=response.request, response=response)
                if response.status_code >= 400:
                    self.breaker.success()
                    detail = response.json().get("detail", response.text)
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"ИИ-сервис отклонил запрос: {detail}")
                self.breaker.success()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                logger.warning(
                    "Сбой обращения к ИИ-сервису",
                    extra={"path": path, "attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < self.RETRIES:
                    await asyncio.sleep(self.BACKOFF * (2 ** attempt))
        self.breaker.failure()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Интеллектуальный сервис недоступен: {last_error}")

    async def benchmark(self, vectors: list[list[float]], target_k: int | None) -> dict[str, Any]:
        payload = {"vectors": vectors, "target_k": target_k}
        return await self._post("/api/v1/clusterize/benchmark", payload, settings.AI_TIMEOUT_SECONDS)

    async def assign(self, vectors: list[list[float]], scaler: dict, centroids: list[dict]) -> list[int]:
        payload = {"vectors": vectors, "scaler": scaler, "centroids": centroids}
        data = await self._post("/api/v1/clusterize/assign", payload, 120.0)
        return data["labels"]

    async def health(self) -> str:
        try:
            async with self._client(5.0) as client:
                response = await client.get("/health")
            return "ok" if response.status_code == 200 else f"ошибка {response.status_code}"
        except httpx.HTTPError as exc:
            return f"недоступен ({exc.__class__.__name__})"


ai_gateway = AIGateway()
