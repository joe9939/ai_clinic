# AI Clinic - Model Adapters
# Abstracts the patient (target model) and doctor (judge model) behind a common interface

import asyncio, httpx


_RETRYABLE = (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError,
              httpx.ReadError, httpx.WriteError)


def _is_rate_limit(exc: Exception) -> bool:
    """Check if an exception is an HTTP 429 rate limit."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    return False


async def retry_chat(chat_fn, prompt: str, max_retries: int = 3) -> str:
    """Wrap a chat function with retry logic for transient errors."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await chat_fn(prompt)
        except _RETRYABLE as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = 1.5 ** (attempt + 1)  # 1.5, 2.25, 3.375...
                await asyncio.sleep(wait)
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    wait = 2.0 ** (attempt + 1)  # 2, 4, 8...
                    await asyncio.sleep(wait)
            else:
                raise  # non-retryable HTTP error
        except Exception:
            raise  # unknown error, don't retry
    raise last_exc


class _BaseModel:
    """Shared async HTTP client to reuse connections."""

    def __init__(self, api_key: str, model: str, base_url: str, temperature: float):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))

    async def chat(self, prompt: str) -> str:
        async def _call(p: str) -> str:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": p}],
                    "temperature": self._temperature
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        return await retry_chat(_call, prompt)

    async def close(self):
        await self._client.aclose()


class PatientModel(_BaseModel):
    """The model being examined. Could be any API-compatible LLM."""

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.deepseek.com/v1"):
        super().__init__(api_key, model, base_url, temperature=0.0)

    @property
    def name(self) -> str:
        return self._model


class DoctorModel(_BaseModel):
    """The judge model that diagnoses the patient."""

    def __init__(self, api_key: str, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com/v1"):
        super().__init__(api_key, model, base_url, temperature=0.2)
