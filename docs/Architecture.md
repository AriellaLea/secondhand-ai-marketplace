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
| assessments | Read model | listing id, score, three sub-scores, recommendation, market price range, similar listing ids, reasoning, confidence | Shown to moderators only |

Passwords are stored as hashes, never as plain text. The dashboard counts by status and category are computed from the listings table.

## 8. AI agent

The agent is an independent process, started separately from the Flask app, that keeps checking for listings in status Pending evaluation. It never approves or rejects: it only records an assessment for the moderator.

For each pending listing it:

1. Reads the listing through an MCP tool.
2. Searches the vector database (RAG) for similar listings: about 30 sample listings plus approved ones.
3. Searches the web with Tavily for market prices of similar items.
4. Produces the assessment: score (50/25/25 across three criteria, as in the PRD), recommendation, price range, similar listing ids, reasoning, confidence.
5. Saves it through a second MCP tool, which raises the Listing evaluated event.

If the web search fails, the assessment says so plainly and is still saved.

Building blocks:

- Deep Agent infrastructure (planning and tool use), with the LLM `qwen2.5:3b` served locally by Ollama.
- RAG pipeline: load, split, embed with the same embedding model (`bge-m3` via Ollama) for indexing and querying, store, retrieve.
- Vector database: Chroma, persisted in `data/chroma/` (not committed; rebuilt with `scripts/load_sample_listings.py`). Code in `app/vector_store.py`.

The models are chosen to fit the computer that runs them: a Mac with 8 GB of RAM and no dedicated GPU (section 11).

## 9. MCP

MCP (Model Context Protocol) is the standard way the agent calls tools. Each tool is a Python function exposed with FastMCP; its docstring tells the LLM when and how to use it.

| Tool | Built with | What it does |
| --- | --- | --- |
| Get pending listing | MCP Studio, our own tool | Returns the next listing in status Pending evaluation |
| Save assessment | MCP Studio, our own tool | Stores the assessment and raises the Listing evaluated event |
| Web search | Tavily MCP service | Finds market prices for similar items on the web |

The two own tools are the two Tools required by the assignment. The agent loads them with `load_mcp_tools` and decides when to call each one.

## 10. Security

- Passwords are hashed before storage.
- Secrets (database connection string, Tavily key) live in `.env.local`, listed in `.gitignore`, never committed.
- Every controller checks the logged-in user's role on the server; hiding a button is not enough.
- Only moderators can read assessments and call approve or reject; sellers get no route to them.
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
