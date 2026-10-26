# Second-hand AI marketplace

Hebrew RTL Flask marketplace where sellers publish listings and an AI agent assesses them before a moderator decides.

Specs live in `docs/` (PRD, architecture, tests). Code follows **MVC**, **CQRS**, and **Event Sourcing**.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Ensure `.env.local` exists in the project root and contains `DATABASE_URL` (Neon PostgreSQL). Do not commit this file.

3. Check the database connection:

```bash
python scripts/check_db.py
```

4. Run the web app:

```bash
python run.py
```

Open http://127.0.0.1:5000/ — you should see the Hebrew home page (RTL).

## Vector database (similar listings)

Requires [Ollama](https://ollama.com) running locally with the embedding model:

```bash
ollama pull bge-m3
python scripts/load_sample_listings.py --reset   # embed data/sample_listings.json into data/chroma/
python scripts/try_similar.py                    # demo queries
python scripts/try_similar.py --title "iPhone 13" --description "black, 128GB" -k 3
```

`data/chroma/` is local and not committed; rerun the load script to rebuild it.

## Layout

| Path | Role |
| --- | --- |
| `app/models/` | Entities and read models |
| `app/views/` | HTML templates (Hebrew, RTL) |
| `app/controllers/` | Flask routes only |
| `app/commands/` | Write-side handlers |
| `app/queries/` | Read-side handlers |
| `app/events/` | Event types, store, projections |
| `app/mcp_tools/` | MCP tools for the agent |
| `agent/` | Separate Deep Agent process |
| `docs/` | PRD, architecture, tests |

## Tests

```bash
python -m pytest -q
```

Tests use a temporary SQLite file, never the cloud database.
