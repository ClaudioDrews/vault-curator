"""OpenRouter API client with async support, retry, and JSON parsing."""
import asyncio
import json
import logging

import httpx

import config

logger = logging.getLogger("curator.openrouter")


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or config.OPENROUTER_API_KEY).strip()
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY not configured")
        self.base = config.OPENROUTER_BASE
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.timeout = httpx.Timeout(config.HTTP_TIMEOUT)

    async def _request(self, endpoint, payload, retries=0):
        url = f"{self.base}{endpoint}"
        backoff = config.RETRY_BACKOFF
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload, headers=self.headers)
                    if resp.status_code == 200:
                        return resp.json()
                    error_body = resp.text[:200]
                    if resp.status_code == 429 and attempt < retries:
                        delay = backoff[min(attempt, len(backoff) - 1)]
                        logger.warning("Rate limited (429), retrying in %ds", delay)
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(f"HTTP {resp.status_code}: {error_body}")
            except httpx.RequestError as e:
                if attempt < retries:
                    delay = backoff[min(attempt, len(backoff) - 1)]
                    logger.warning("Request error, retrying in %ds: %s", delay, e)
                    await asyncio.sleep(delay)
                    continue
                raise OpenRouterError(str(e)) from e
        raise OpenRouterError(f"All {retries + 1} attempts failed")

    async def chat(self, messages, model=None, temperature=0.3, max_tokens=2048, response_format=None):
        payload = {
            "model": model or config.ENRICHMENT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        data = await self._request("/chat/completions", payload, retries=config.MAX_RETRIES)
        try:
            content = data["choices"][0]["message"]["content"]
            if content is None:
                raise OpenRouterError("Model returned content: null (known DeepSeek + json_object issue)")
            return content
        except (KeyError, IndexError) as e:
            raise OpenRouterError(f"Unexpected response shape: {e}") from e

    async def embed_single(self, text):
        payload = {
            "model": config.EMBEDDING_MODEL,
            "input": text,
        }
        data = await self._request("/embeddings", payload, retries=config.MAX_RETRIES)
        try:
            return data["data"][0]["embedding"]
        except (KeyError, IndexError) as e:
            raise OpenRouterError(f"Unexpected embedding response: {e}") from e

    async def embed_batch(self, texts):
        payload = {
            "model": config.EMBEDDING_MODEL,
            "input": texts,
        }
        data = await self._request("/embeddings", payload, retries=config.MAX_RETRIES)
        try:
            return [d["embedding"] for d in data["data"]]
        except (KeyError, IndexError) as e:
            raise OpenRouterError(f"Unexpected embedding response: {e}") from e