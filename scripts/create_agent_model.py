"""Create the agent's Ollama model: qwen2.5:3b with a bigger context, temperature 0
and a limit on the length of each answer.

Ollama's default context is too small for the Deep Agent prompt plus two web
searches, and the OpenAI-compatible endpoint the agent uses cannot set it per
request; it also ignores the answer limit langchain-openai sends
(max_completion_tokens: one answer ran to 2412 tokens). So the settings are baked
into a derived model.

Safe to run twice. Usage: python scripts/create_agent_model.py
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import AGENT_BASE_MODEL, AGENT_MAX_TOKENS, AGENT_MODEL, AGENT_NUM_CTX  # noqa: E402
from app.vector_store import OLLAMA_HOST  # noqa: E402


def main() -> int:
    body = {
        "model": AGENT_MODEL,
        "from": AGENT_BASE_MODEL,
        "parameters": {"num_ctx": AGENT_NUM_CTX, "temperature": 0, "num_predict": AGENT_MAX_TOKENS},
        "stream": False,
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/create",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            status = json.load(response).get("status")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Ollama refused ({exc.code}): {detail}. Run: ollama pull {AGENT_BASE_MODEL}")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Cannot reach Ollama at {OLLAMA_HOST} ({exc}). Start it with: ollama serve")
        return 1
    print(f"Model {AGENT_MODEL} ready (from {AGENT_BASE_MODEL}, num_ctx {AGENT_NUM_CTX}, num_predict {AGENT_MAX_TOKENS}): {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
