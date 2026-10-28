"""The agent's chat model: the local Ollama model through its OpenAI-compatible endpoint."""

import httpx
from langchain_openai import ChatOpenAI

from agent.config import AGENT_MAX_TOKENS, AGENT_MODEL, LISTING_TIMEOUT_SECONDS
from app.vector_store import OLLAMA_HOST


def make_llm() -> ChatOpenAI:
    # Plain HTTP to Ollama (/v1); the `ollama` Python package hangs. The key is unused.
    # trust_env=False: a system proxy must not intercept calls to the local Ollama.
    return ChatOpenAI(
        model=AGENT_MODEL,
        base_url=f"{OLLAMA_HOST}/v1",
        api_key="ollama",
        temperature=0,
        max_tokens=AGENT_MAX_TOKENS,  # Ollama ignores it: num_predict in the derived model does the job
        timeout=LISTING_TIMEOUT_SECONDS,
        max_retries=0,  # a failed call fails the listing; it is retried later
        http_client=httpx.Client(trust_env=False, timeout=LISTING_TIMEOUT_SECONDS),
        http_async_client=httpx.AsyncClient(trust_env=False, timeout=LISTING_TIMEOUT_SECONDS),
    )
