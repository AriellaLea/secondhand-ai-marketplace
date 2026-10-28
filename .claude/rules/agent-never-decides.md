---
paths:
  - "agent/**"
  - "app/mcp_tools/**"
  - "app/commands/**"
  - "app/events/**"
---

# The AI agent never approves or rejects a listing

The agent only gives an opinion; the decision belongs to a human moderator (PRD F7 and F8).

- Never give the agent a tool, MCP or local, that changes a listing's status other than
  through the Listing evaluated event (`save_assessment`).
- The agent reaches the data only through its MCP tools, never through the database directly.
- The approve and reject commands (`app/commands/decide_listing.py`) always check that the
  actor is a moderator; never let them accept the agent's service account.
- The agent's service account (role `agent`) can never log in.
- After any change in `agent/`, `app/mcp_tools/`, `app/commands/` or `app/events/`, the tests
  T-AGENT-7 (the agent's only event is Listing evaluated) and T-F8-5 (only a moderator
  decides) must still pass.
