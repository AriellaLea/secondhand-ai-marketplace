# Second-hand AI marketplace

A second-hand marketplace in Hebrew (right to left) where every listing is checked by an AI
agent before a human moderator approves or rejects it.

Specifications live in `docs/`: [PRD](docs/PRD.md), [architecture](docs/Architecture.md) and
[test plan](docs/tests.md). The code follows **MVC**, **CQRS** and **Event Sourcing**.

## What the app does

| Who | What they can do |
| --- | --- |
| Seller | Sign up, publish listings, search the approved listings of all sellers, follow the status of their own listings and read the reason when one is rejected |
| Moderator | See every listing with the agent's score, read the agent's assessment, approve or reject (with a reason), see the event history of a listing and the dashboard |
| AI agent | Evaluates every new listing on its own and saves an assessment; it never approves or rejects |

A listing goes through these statuses: **Pending evaluation → Evaluated → Approved or Rejected**.
Each step is stored as an event (who did what and when), and the moderator sees that history
on the listing's page.

## The AI agent

The agent is a separate process (`python -m agent`) that checks the database every 10 seconds
for listings in status Pending evaluation. For each listing it starts a fresh
[Deep Agent](https://github.com/langchain-ai/deepagents) with the local model `qwen2.5:3b`
(Ollama), which works with three tools:

1. **`search_similar_listings`** (RAG): the listing's title and description are embedded with
   `bge-m3` and compared in **Chroma** with about 30 sample listings and every approved
   listing, in the same category.
2. **`tavily_search`** (Tavily, over MCP): finds the price of the item new on the web.
3. **`save_assessment`** (our own MCP tool): saves the assessment, which raises the
   Listing evaluated event.

**The model reads and judges, the program computes and writes.** The model never sees the
listing's price and writes no text. It only reports the prices it read on the web and whether
the description is about the item in the title. The program then:

- keeps only the web prices that really appear in the search results, and takes their
  median as the new-item price;
- scores three criteria:

  | Criterion | Points | Rule |
  | --- | --- | --- |
  | Price vs market | 50 | at most 80% of the new price: 50; up to the new price: 25; above: 0 |
  | Price vs similar listings | 25 | up to 1.2 times their median: 25; up to 1.5 times: 12; above: 0 |
  | Listing quality | 25 | from the description's length and the model's answer: 25, 15 or 5 |

- writes every Hebrew sentence for the moderator, and derives the recommendation
  (70 or more: approve; 40–69: manual review; below 40: reject) and the confidence.

Why: real runs showed that a 3B model compares numbers badly, anchors on the price it sees
and slips Chinese or Greek letters into Hebrew. Other guards in the code: nothing is saved
without a successful similar-listing search and web search; the search must use the listing's
own title; if anything fails, the listing stays Pending evaluation and is retried 5 minutes
later. Details: [Architecture §8](docs/Architecture.md).

## Setup

You need Python 3.11, Node.js (for the Tavily MCP server, started with `npx`),
[Ollama](https://ollama.com), a [Neon](https://neon.tech) PostgreSQL database and a
[Tavily](https://tavily.com) API key.

1. Install the dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create `.env.local` in the project root (it is in `.gitignore`, never commit it):

   ```
   DATABASE_URL=postgresql://...      # Neon connection string
   SECRET_KEY=...                     # any long random string
   TAVILY_API_KEY=tvly-...
   ```

3. Check the database connection and create the accounts that have no sign-up form:

   ```bash
   python scripts/check_db.py
   python scripts/create_moderator.py --name "..." --email "..." --password "..."
   python scripts/create_agent_user.py           # the agent's service account (cannot log in)
   python scripts/upgrade_assessments_table.py   # only for a database created before 28/10
   ```

4. Prepare Ollama (models) and Chroma (vector database):

   ```bash
   ollama pull bge-m3                              # embeddings
   ollama pull qwen2.5:3b                          # the agent's model
   python scripts/create_agent_model.py            # qwen2.5:3b-agent: context 8192, temperature 0, 1000 tokens max
   python scripts/load_sample_listings.py --reset  # 30 sample listings into data/chroma/
   ```

   `data/chroma/` is local and not committed. `python scripts/index_approved_listings.py`
   adds the approved listings again (for example after a reset, or if Ollama was down when a
   listing was approved).

## Run

Two terminals, Ollama running:

```bash
python run.py          # terminal 1: the web app, http://127.0.0.1:5000/
python -m agent        # terminal 2: the agent, evaluates new listings until Ctrl+C
```

`python -m agent --once` evaluates what is pending now and stops. The agent logs every tool
call to the terminal and to `logs/agent.log`.

Optional checks:

```bash
python scripts/try_similar.py --title "iPhone 13" --description "black, 128GB" -k 3
npx @modelcontextprotocol/inspector .venv/bin/python -m app.mcp_tools.server   # our MCP tools
```

## Tests

```bash
python -m pytest -q
```

About 200 tests, on a temporary SQLite file (never the cloud database), with a fake model, a
fake Tavily and a fake embedder, so they need neither Ollama nor the internet. The manual test
plan is in [docs/tests.md](docs/tests.md).

## How we built it

One feature at a time, each one planned, built, tested and committed before the next:

| Step | What | Tools |
| --- | --- | --- |
| 1 | PRD, architecture and test plan in `docs/` | Markdown |
| 2 | Flask skeleton and F1 sign-up / login with two roles (MVC + CQRS) | Flask, SQLAlchemy, **Neon** PostgreSQL |
| 3 | F2 publish a listing, stored as events | Event Sourcing (`events` table + projections) |
| 4 | F3 search, F4 listing details, F5 listings table, F6 dashboard | CQRS read models |
| 5 | Vector database of 30 sample listings | **Ollama** (`bge-m3`) + **Chroma** |
| 6 | Two own MCP tools: `get_pending_listing`, `save_assessment` | **MCP** (official SDK, FastMCP), MCP Inspector |
| 7 | F7 AI agent as a separate process, then real-run fixes (the program scores, the model judges) | **Deep Agents**, Ollama (`qwen2.5:3b`), RAG, **Tavily** over MCP |
| 8 | F8 moderator decision and event history | Event Sourcing, Chroma (approved listings) |

Working method, with Claude Code:

- **Skills from [Skills.sh](https://skills.sh)** (in `.agents/skills/`): `grilling`
  (mattpocock/skills) to plan every feature with numbered questions before coding, and
  `mcp-builder` to design the MCP tools.
- **Our own Skill** `new-feature` (`.claude/skills/new-feature/`): our steps from the docs to
  the commit.
- **Our own Rule** `agent-never-decides` (`.claude/rules/`): the AI agent never approves or
  rejects a listing; the decision commands accept a moderator only.
- `CLAUDE.md`: the project rules, the current status and every design decision.

## Layout

| Path | Role |
| --- | --- |
| `app/models/` | Read models (listings, assessments, users) and the event table |
| `app/views/` | HTML templates (Hebrew, RTL) |
| `app/controllers/` | Flask routes only |
| `app/commands/` | Write side: publish, record assessment, approve, reject |
| `app/queries/` | Read side: search, details, table, dashboard, history |
| `app/events/` | Event types, append-only store, projections |
| `app/pricing.py`, `app/listing_quality.py` | The agent's scoring rules |
| `app/vector_store.py` | Chroma + Ollama embeddings |
| `app/mcp_tools/` | Our MCP server (`get_pending_listing`, `save_assessment`) |
| `agent/` | The AI agent process |
| `scripts/` | Setup and maintenance scripts |
| `docs/` | PRD, architecture, tests |
