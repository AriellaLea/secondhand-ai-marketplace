# Architecture – Second-Hand Marketplace with AI Agent

Oct 21, 2026 · @Ariella

## 1. Overview

&#91;embedded content: system architecture · 3 zones, 11 parts\]

A browser request enters Flask and becomes a command or a query; the agent works on the same data through its own MCP tools.

## 2. Three tiers

The system has three tiers, and each one only talks to its neighbour: the browser never touches a database directly.

| Tier | What it is | Technology | Rule |
| --- | --- | --- | --- |
| Presentation | Pages the user sees (Hebrew, right-to-left) | HTML templates, CSS | Shows data and sends forms. No business logic. |
| Logic | The Flask application: controllers, command handlers, query handlers | Python, Flask | All rules live here: who may do what, status changes, validation. |
| Data | Event store, read model, vector database | Neon PostgreSQL (cloud), Chroma (local folder `data/chroma/`) | Only the logic tier reads or writes it. The agent process uses it through its own tools. |

The AI agent is a fourth, separate process. It is not part of the web request cycle: it runs on its own and reaches the data through MCP tools (section 9).

## 3. Repository structure

One GitHub repository holds the specs, the code agent's rules and skills, the web app and the agent.

```
repo/
  docs/
    PRD.md
    architecture.md
    tests.md
  .claude/            (or .cursor/, depending on the code agent)
    rules/            our own Rule(s)
    skills/           Skills.sh skill + our own Skill
    commands/
  app/                Flask web application
    models/           entities and read models
    views/            HTML templates (Hebrew, RTL)
    controllers/      Flask routes: receive a request, call a handler, return a view
    commands/         command handlers (write side)
    queries/          query handlers (read side)
    events/           event types, event store, projections
    mcp_tools/        the two MCP tools exposed to the agent
  agent/              separate process: the Deep Agent
  .env.local          secrets (never committed)
  .gitignore
```

The folder names are a proposal; the split between `commands/` and `queries/` is the part that matters.

## 4. MVC

MVC splits the web app into three roles so that data, screens and request handling never get mixed in one file.

| Part | Role in our app | Example |
| --- | --- | --- |
| Model | Data and rules: entities (User, Listing, Assessment) and read models | A Listing with its current status |
| View | What is displayed: Hebrew HTML templates | The listings table, the dashboard |
| Controller | Receives the HTTP request, checks the user's role, calls a command or query handler, picks the view | `POST /listings` calls the publish-listing command |

A controller contains no business logic and no SQL. It only routes: a form submission becomes a command, a page load becomes a query.

## 5. CQRS

CQRS (Command Query Responsibility Segregation) means writing and reading use two separate paths: commands change the system, queries only read it.

|  | Commands (write side) | Queries (read side) |
| --- | --- | --- |
| Purpose | Change something | Return data, change nothing |
| Examples | Register seller, publish listing, record assessment, approve listing, reject listing | Search listings, listing details, listings table, dashboard counts |
| Output | One or more events saved in the event store | Rows from the read model |
| Validated by | Role and status rules from the PRD | Role visibility rules (a seller never sees the assessment) |

The read model is a table kept up to date from the events (a projection). Screens read from it, so they are fast and simple, and they never replay events themselves.

Flow: a controller sends a command, the command handler checks the rules and appends an event, a projection updates the read model, and later queries read that read model.

## 6. Event Sourcing

Instead of storing only the current status of a listing, we store every fact that happened to it as an event, and the status is rebuilt from those events. Events are never edited or deleted, only appended.

| Event | Raised when | Resulting status |
| --- | --- | --- |
| Listing created | A seller publishes a listing | Pending evaluation |
| Listing evaluated | The agent saves its assessment | Evaluated |
| Listing approved | A moderator approves | Approved |
| Listing rejected | A moderator rejects, with a reason | Rejected |

Worked example: listing 12 has three events in order: created, evaluated, approved. Replaying them gives status Approved, and the history also shows when each step happened and who did it. This history is the audit trail the moderator and the oral exam can point to.

The read model holds the current status so screens do not replay events on every page load. If the read model is ever wrong, it can be dropped and rebuilt from the event log.

## 7. Database tables

Four tables in the cloud database; the first is the write side, the others are read models. The vector database is separate (section 8).

| Table | Side | Main fields | Purpose |
| --- | --- | --- | --- |
| events | Write (event store) | id, listing id, event type, payload (JSON), actor id, created at | Append-only log of everything that happened |
| users | Read model | id, name, email, password hash, role (seller or moderator) | Authentication and roles |
| listings | Read model | id, seller id, title, description, category, price, status, rejection reason, created at | Search, details and the listings table |
| assessments | Read model | listing id, score, three sub-scores and their justifications, recommendation, confidence, market price min and max, similar listing ids, reasoning, evaluated at | Shown to moderators only |

Passwords are stored as hashes, never as plain text. The dashboard counts by status and category are computed from the listings table.

## 8. AI agent

The agent is an independent process, started separately from the Flask app, that keeps checking for listings in status Pending evaluation. It never approves or rejects: it only records an assessment for the moderator.

For each pending listing it:

1. Reads the listing through an MCP tool.
2. Searches the vector database (RAG) for similar listings: about 30 sample listings plus approved ones.
3. Searches the web with Tavily for the new price of the item.
4. Produces the assessment: score (50/25/25 across three criteria, as in the PRD), recommendation, price range and new-item price, similar listing ids, reasoning, confidence. The model judges whether the description fits the title; the program scores and writes every text (`app/pricing.py`, `app/listing_quality.py`).
5. Saves it through a second MCP tool, which raises the Listing evaluated event.

How it runs (code in `agent/`):

- A Python loop (`agent/__main__.py`) calls `get_pending_listing` every 10 seconds. For each listing it starts a fresh Deep Agent (`agent/runner.py`) with the listing in its first message, a 10-minute limit (about 4 minutes on the 8 GB Mac) and a step limit.
- The agent sees three tools: `search_similar_listings` (RAG, a local tool), `tavily_search` (Tavily MCP) and `save_assessment` (our MCP tool), and decides when to call each. The Deep Agents file tools, sub-agents and `write_todos` are hidden: a 3B model gets lost among them, and its steps are fixed.
- The model sees a reduced `save_assessment` with two fields: `web_prices` (every price of the item it read in the web results) and `description_matches_title` (true or false). It writes no text, and its first message holds the title, description and category but not the price: when it saw the price it picked the web price closest to it (6500 for a 6000 listing). In real runs `qwen2.5:3b` copied a similar listing's price as the market range, invented ranges (500–10,000), compared prices wrongly, and slipped Greek, Cyrillic or Chinese letters into its Hebrew (every time it wrote "קטגוריה"), so the program does the rest and then calls our MCP `save_assessment` with every field.
- Price checks and scoring in the program (`agent/tools.py`, rules in `app/pricing.py`): a web price is kept only if it appears in the web results the model read (`2,490`, `2490`, `2.490` and `1,290.00` are understood), the others are ignored and logged; their median is the new-item price; the program computes the three sub-scores (quality from the description's word count and the model's answer: 25, 15 or 5), writes their Hebrew reasons and builds the reasoning (the three reasons and the recommendation). With no verified price the model is told once to search again; if there is still none, the listing is saved with a neutral price score and low confidence.
- Other guards in the program, not in the prompt: `save_assessment` is refused unless the similar-listing search ran and a web search returned results; the program fills in `listing_id` and the similar listing ids (those the RAG returned with a similarity of at least 0.55: a small model invents ids); a web search must contain at least half of the listing title's words, as whole words (a one-letter Hebrew prefix is fine; numbers do not count): the model searched with a similar listing's title, and "ספרים" in a 7-book set's title once passed for "ספר"; similar listings are searched in the listing's own category only (a baby chair came up as similar to a book); missing or invalid fields get a short hint; a `save_assessment` called together with other tools is refused with the reason, since it was written before their results were known (Ollama ignores `parallel_tool_calls`); at most 2 web searches per listing; each model answer is limited to 1000 tokens (the model once generated 2412 tokens for 10 minutes); the limit is `num_predict` in the derived model, since Ollama ignores the `max_completion_tokens` that `langchain-openai` sends.
- A 3B model often stops after a refusal: if it stops without saving while both searches succeeded, the program reminds it once to call `save_assessment` (same conversation, kept by an in-memory checkpointer).
- If the web search or the model fails, or the agent stops without saving, nothing is saved: the listing stays Pending evaluation. Its id goes into `exclude_ids` so the queue moves on, and it is tried again 5 minutes later. If the database cannot be read, `--once` stops with "Could not read the pending listings", not as if the queue were empty.
- At start the agent checks that Ollama answers, that both models exist and that `TAVILY_API_KEY` and `DATABASE_URL` are set. If the agent service account is missing it stops with a clear message.
- Every tool call is logged to the terminal and to `logs/agent.log` (not committed).
- Approved listings join the vector database when a moderator approves them (`app/commands/decide_listing.py`, after the approval is committed). If Ollama is down the approval stands, the moderator is warned, and `scripts/index_approved_listings.py` adds the missing ones (upsert, safe to re-run).
- Known limitation: within one category, the 0.55 similarity threshold can still let a different item through when titles share a word (a baby high chair matched an office chair, "כיסא"). Similarity of meaning is not the same item either: one Harry Potter book was compared with a used 7-book set at 150 ₪. This only weighs on the 25 points of price vs similar listings; the 50 points against the new price are not affected. Tuning it needs new measurements on the sample listings.

Building blocks:

- Deep Agent infrastructure (`deepagents`, tool use and middleware), with the LLM `qwen2.5:3b` served locally by Ollama. The agent uses a derived model, `qwen2.5:3b-agent` (context 8192, temperature 0, at most 1000 tokens per answer), created by `scripts/create_agent_model.py`; `AGENT_MODEL` can name another one.
- The LLM is called through Ollama's OpenAI-compatible endpoint (`/v1`) with `langchain-openai`, not through the `ollama` package, which hangs.
- RAG pipeline: load, split, embed with the same embedding model (`bge-m3` via Ollama) for indexing and querying, store, retrieve.
- Vector database: Chroma, persisted in `data/chroma/` (not committed; rebuilt with `scripts/load_sample_listings.py`). Code in `app/vector_store.py`.
- MCP servers: ours (`python -m app.mcp_tools.server`) and Tavily (`npx -y tavily-mcp@0.2.22`), both over stdio, each with one session kept open for the whole run.

Run it:

```
python scripts/create_agent_user.py    # once per database
python scripts/upgrade_assessments_table.py  # once, on a database created before fix K
python scripts/create_agent_model.py   # once per machine
python -m agent                        # or: python -m agent --once
```

The models are chosen to fit the computer that runs them: a Mac with 8 GB of RAM and no dedicated GPU (section 11).

## 9. MCP

MCP (Model Context Protocol) is the standard way the agent calls tools. Each tool is a Python function exposed with FastMCP; its docstring tells the LLM when and how to use it.

| Tool | Built with | What it does |
| --- | --- | --- |
| `get_pending_listing(exclude_ids=[])` | Our own tool (FastMCP), tested in MCP Inspector | Returns the oldest listing in status Pending evaluation (id, title, description, price, category, created at), or null. Reads only, locks nothing. |
| `save_assessment(...)` | Our own tool (FastMCP), tested in MCP Inspector | Takes the three sub-scores with a one-line reason each, the market price range and new-item price (all three empty when no web price was found), the similar listing ids and the Hebrew reasoning; the agent's program fills them all. The program adds up the score and derives the recommendation and the confidence, then raises the Listing evaluated event. Refused if the listing is not Pending evaluation or any field is invalid; then nothing is saved. |
| Web search | Tavily MCP service | Finds market prices for similar items on the web |

The two own tools are the two Tools required by the assignment. The agent process loads them with `load_mcp_tools`: the program's loop calls `get_pending_listing`, and the LLM decides when to call `save_assessment` and `tavily_search`.

Implementation:

- Server: `app/mcp_tools/server.py`, built with the official `mcp` SDK (`FastMCP`, version 1.x because `langchain-mcp-adapters` requires it). It runs over **stdio**: the agent starts it as a subprocess with `python -m app.mcp_tools.server`, so it opens no network port.
- The server is a thin adapter, like a controller: each tool opens its own database session, calls one handler and returns JSON. The rules live in `app/queries/get_pending_listing.py` (query) and `app/commands/record_assessment.py` (command).
- Validation errors go back to the model as MCP tool errors, in English, so it can fix its call.
- The Listing evaluated event stores the computed score, recommendation and confidence too, so a replay gives back what was decided at the time even if the thresholds change.
- The event's actor is the agent's service account (`agent@system.local`, role `agent`), created by `scripts/create_agent_user.py`. The agent process never logs in with it.
- Manual check: `npx @modelcontextprotocol/inspector .venv/bin/python -m app.mcp_tools.server`.

## 10. Security

- Passwords are hashed before storage.
- Secrets (database connection string, Tavily key) live in `.env.local`, listed in `.gitignore`, never committed.
- Every controller checks the logged-in user's role on the server; hiding a button is not enough. The approve and reject commands check the role and the status again.
- No CSRF protection (out of the course's scope). A page on another site could make a logged-in moderator's browser send an approve or reject; the fix would be the session cookie set to `SameSite=Lax`, or a CSRF token in every form.
- Only moderators can read assessments and call approve or reject; sellers get no route to them, and query handlers drop the agent score from what they return to a seller.
- The agent's service account (role `agent`) has a random password that is never shown, and the login refuses any role other than seller or moderator.
- Registration only creates sellers; moderators have no sign-up form and are created directly in the database by a small script (hashed password). A moderator logs in on the same login page as sellers, and the server reads the role from the users table to decide which pages are available.
- All database access uses parameterized queries.

## 11. Technical decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Web framework | Flask | Required by the assignment |
| Patterns | MVC, CQRS, Event Sourcing | Required; listing status is a natural fit for events |
| Cloud database | Neon PostgreSQL | Cloud database as required by the assignment (Somee.com was suggested); free tier, standard PostgreSQL |
| Agent infrastructure | Deep Agents with RAG and Tavily | Required |
| Tool protocol | MCP, two own tools built in MCP Studio | Required |
| Interface | Hebrew, right-to-left | Requirement of the course |
| Agent LLM | `qwen2.5:3b` via Ollama | Small enough to run locally on 8 GB of RAM |
| Embedding model | `bge-m3` via Ollama, same model for indexing and searching | Multilingual, handles Hebrew and English listings |
| Vector database | Chroma, saved in `data/chroma/` | Simple local persistence, no extra server |

Still to decide:

- [x] Ollama LLM model: `qwen2.5:3b`
- [x] Embedding model: `bge-m3`
- [x] Vector database: Chroma
- [ ] Language of the documents (confirm with the lecturer)
- [ ] Skills.sh skill, own Skill and own Rule
