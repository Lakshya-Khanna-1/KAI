import asyncio
import json
import logging
import sys
from typing import Any, AsyncGenerator, Dict, List, Union
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaConnectionError(Exception):
    """Raised when communication with the local Ollama server fails."""
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        default_model: str = settings.KAI_MODEL,
        default_embed_model: str = settings.OLLAMA_EMBED_MODEL,
        default_keep_alive: str = settings.OLLAMA_KEEP_ALIVE,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.default_embed_model = default_embed_model
        self.default_keep_alive = default_keep_alive
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def check_reachability(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/models")
                return response.status_code == 200
        except Exception:
            return False

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        json_payload: Dict[str, Any] | None = None,
        stream: bool = False,
    ) -> Union[httpx.Response, AsyncGenerator[bytes, None]]:
        """Helper to execute HTTP requests with exponential backoff retries."""
        url = f"{self.base_url}{endpoint}"
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                if stream:
                    client = httpx.AsyncClient(timeout=self.timeout_seconds)
                    req = client.build_request(method, url, json=json_payload)
                    response = await client.send(req, stream=True)
                    if response.status_code != 200:
                        content = await response.aread()
                        await response.aclose()
                        await client.aclose()
                        raise OllamaConnectionError(
                            f"Ollama returned HTTP {response.status_code}: {content.decode('utf-8', errors='ignore')}"
                        )
                    return response, client
                else:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        response = await client.request(method, url, json=json_payload)
                        if response.status_code != 200:
                            raise OllamaConnectionError(
                                f"Ollama returned HTTP {response.status_code}: {response.text}"
                            )
                        return response
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exception = exc
                logger.warning(
                    f"Attempt {attempt}/{self.max_retries} failed to reach Ollama at {url}: {exc}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

        raise OllamaConnectionError(
            f"Could not connect to local Ollama server at '{self.base_url}'. "
            f"Please ensure Ollama is running and accessible. Error details: {last_exception}"
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        tools: List[Dict[str, Any]] | None = None,
        keep_alive: str | None = None,
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        Send a chat completion request to the OpenAI-compatible Ollama endpoint.
        If stream=True, returns an AsyncGenerator yielding text deltas.
        If stream=False, returns the complete response dictionary.
        """
        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_gpu": 999, # Strictly force all layers to GPU to prevent CPU fallback
                "num_ctx": 8192 # Lock context window to guarantee it fits entirely inside 12GB VRAM
            },
            "keep_alive": keep_alive or self.default_keep_alive,
        }
        if tools:
            payload["tools"] = tools

        if not stream:
            response = await self._request_with_retry("POST", "/chat/completions", json_payload=payload)
            return response.json()

        # Streaming response
        response, client = await self._request_with_retry("POST", "/chat/completions", json_payload=payload, stream=True)

        async def stream_generator() -> AsyncGenerator[str, None]:
            try:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
            finally:
                await response.aclose()
                await client.aclose()

        return stream_generator()

    async def embed(
        self,
        input_text: Union[str, List[str]],
        model: str | None = None,
    ) -> Dict[str, Any]:
        """Generate text embeddings using OpenAI-compatible /embeddings endpoint."""
        payload = {
            "model": model or self.default_embed_model,
            "input": input_text,
            "options": {
                "num_gpu": 999,
                "num_ctx": 8192
            }
        }
        response = await self._request_with_retry("POST", "/embeddings", json_payload=payload)
        return response.json()

    async def list_models(self) -> List[Dict[str, Any]]:
        """List models available on the local Ollama instance."""
        try:
            response = await self._request_with_retry("GET", "/models")
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error listing models from Ollama: {e}")
            return []

    @staticmethod
    def estimate_tokens(content: Union[str, List[Dict[str, Any]]]) -> int:
        """
        Estimate token count per string or list of message objects.
        Uses a standard ~4 chars/token heuristic with formatting overhead per message.
        """
        if isinstance(content, str):
            return max(1, len(content) // 4)

        total_chars = 0
        total_tokens = 0
        for msg in content:
            # Add message overhead (~4 tokens for role + formatting)
            total_tokens += 4
            msg_content = msg.get("content") or ""
            if isinstance(msg_content, str):
                total_chars += len(msg_content)
            elif isinstance(msg_content, list):
                for part in msg_content:
                    if isinstance(part, dict) and "text" in part:
                        total_chars += len(part["text"])

        total_tokens += total_chars // 4
        return max(1, total_tokens)


ollama_client = OllamaClient()


async def _cli_main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Hello KAI, introduce yourself briefly."
    print(f"--- Prompt: '{prompt}' ---")
    print("--- Streaming response from local model ---")
    try:
        stream = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        async for chunk in stream:
            try:
                sys.stdout.write(chunk)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(chunk.encode("utf-8", errors="replace"))
            sys.stdout.flush()
        print("\n--- End of Stream ---")
    except OllamaConnectionError as err:
        print(f"\nError: {err}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(_cli_main())
