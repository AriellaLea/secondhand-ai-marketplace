"""Evaluate one listing with a fresh Deep Agent (tool use)."""

import asyncio
import logging
from typing import Callable

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent, register_harness_profile
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from agent.config import LISTING_TIMEOUT_SECONDS, RECURSION_LIMIT, SAVE_REMINDERS
from agent.prompt import SYSTEM_PROMPT, listing_message
from agent.tools import ListingRun, build_tools, text_of
from app.vector_store import find_similar_listings

log = logging.getLogger("agent")

SAVE_REMINDER = "You have not saved the assessment yet. Call save_assessment now."

# Only our three tools: a 3B model gets lost among the built-in file tools and
# sub-agents, so they are hidden (ChatOpenAI = "openai"). write_todos is not added:
# the steps are fixed, and the model only called it empty, after saving.
register_harness_profile(
    "openai",
    HarnessProfile(
        excluded_tools=frozenset({"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute"}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)


class SaveTooEarlyMiddleware(AgentMiddleware):
    """Flag a save_assessment the model calls together with other tools: it was written
    before their results were known, so save_assessment refuses it and says why.
    (Ollama ignores parallel_tool_calls=False.)"""

    def __init__(self, run: ListingRun):
        super().__init__()
        self.run = run

    def after_model(self, state, runtime):
        message = state["messages"][-1]
        if isinstance(message, AIMessage) and len(message.tool_calls) > 1:
            names = {call["name"] for call in message.tool_calls}
            self.run.save_too_early = "save_assessment" in names and len(names) > 1
        return None


def _short(value, limit: int = 160) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _log_update(update: dict) -> None:
    """One log line per tool call, tool result and final model message."""
    for node in update.values():
        messages = node.get("messages", []) if isinstance(node, dict) else []
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    log.info("  → %s(%s)", call["name"], _short(call["args"]))
                if not message.tool_calls and message.content:
                    log.info("  model: %s", _short(message.content))
            elif isinstance(message, ToolMessage):
                log.info("  ← %s: %s", message.name, _short(text_of(message.content)))


async def evaluate_listing(
    listing: dict,
    mcp_tools: dict[str, BaseTool],
    llm: BaseChatModel,
    similar: Callable = find_similar_listings,
) -> ListingRun:
    """Run the agent on one listing. Success means run.saved is set; nothing is saved otherwise."""
    run = ListingRun(listing)
    agent = create_deep_agent(
        model=llm,
        tools=build_tools(run, mcp_tools, similar),
        system_prompt=SYSTEM_PROMPT,
        middleware=[SaveTooEarlyMiddleware(run)],
        checkpointer=InMemorySaver(),  # keeps the conversation for a reminder
    )
    config = {"recursion_limit": RECURSION_LIMIT, "configurable": {"thread_id": listing["id"]}}

    async def go() -> None:
        message = HumanMessage(listing_message(listing))
        for reminders in range(SAVE_REMINDERS + 1):
            async for update in agent.astream({"messages": [message]}, config=config, stream_mode="updates"):
                _log_update(update)
            if reminders == SAVE_REMINDERS or not run.can_still_save():
                return
            log.info("  (stopped without saving: reminded to call save_assessment)")
            message = HumanMessage(SAVE_REMINDER)

    try:
        await asyncio.wait_for(go(), LISTING_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        run.fail(f"Timed out after {LISTING_TIMEOUT_SECONDS} s.")
    except Exception as exc:  # the model failed (Ollama down, step limit reached…)
        run.fail(f"Agent failed: {type(exc).__name__}: {_short(exc, 300)}")
    if run.saved is None and not run.errors:
        run.fail("The agent stopped without saving an assessment.")
    return run
