## 0. What you are building

KAI — a self-hosted, private, Jarvis-style personal AI assistant.
Runs entirely on my home server. No cloud LLM calls. No third-party data storage.

Owner: single user (me). No multi-tenancy. Ever.

Version 1 scope = **Tasks 1–8 only**. Nothing more.
I will hand you Tasks 9–20 one at a time, later. Build V1 so those slot in cleanly.

---

## 1. Hard rules

1. **One task at a time.** Never start the next task unprompted.
2. **No cloud inference.** All model calls hit local Ollama.
3. **No telemetry.** No analytics SDKs. No external logging services.
4. **No secrets in code.** Everything via `.env`. Ship `.env.example`.
5. **Modular.** Every feature is a self-contained module. Adding Task 12 must not touch Task 3's code.
6. **Migrations, not drops.** Schema changes go through Alembic. Never wipe my data.
7. **Ask before deleting.** Any destructive operation needs my explicit confirmation.
8. **Working code only.** If you cannot verify it runs, say so plainly.

---

## 2. Stack (fixed — do not substitute)

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI + Uvicorn |
| DB | SQLite + SQLAlchemy 2.x + Alembic |
| LLM runtime | Ollama, OpenAI-compatible `/v1` endpoint |
| Chat model | env `KAI_MODEL`, default `qwen3:8b` |
| Embeddings | `nomic-embed-text` via Ollama |
| Vector store | Qdrant (added Task 10, not before) |
| Scheduler | APScheduler, `SQLAlchemyJobStore` |
| Push | ntfy (self-hosted or ntfy.sh topic) |
| Frontend | Vanilla JS PWA. No React. No build step. |
| Networking | Tailscale tailnet. No public ports. |
| Packaging | Docker + docker-compose |

Python deps: `fastapi uvicorn sqlalchemy alembic httpx pydantic pydantic-settings apscheduler python-dotenv pytest`.
Add nothing else without telling me why.

---

## 3. Directory layout

```
kai/
├── AGENTS.md
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── alembic/
├── tests/
└── app/
    ├── main.py              # FastAPI app factory
    ├── config.py            # pydantic-settings
    ├── db/
    │   ├── base.py
    │   ├── session.py
    │   └── models/          # one file per domain
    ├── llm/
    │   ├── client.py        # Ollama wrapper
    │   ├── loop.py          # tool-calling agent loop
    │   ├── prompt.py        # system prompt builder
    │   └── registry.py      # tool registration
    ├── modules/             # one folder per feature
    │   └── <feature>/
    │       ├── models.py
    │       ├── service.py
    │       ├── tools.py     # LLM-facing tools
    │       └── router.py    # HTTP routes
    ├── services/
    │   ├── notify.py
    │   ├── scheduler.py
    │   └── memory.py
    ├── api/
    └── static/              # PWA
```

---

## 4. Module contract

Every new feature module exposes:

```python
# app/modules/<feature>/tools.py
TOOLS: list[ToolSpec]   # JSON-schema tool definitions + handlers
```

`app/llm/registry.py` auto-discovers `TOOLS` from every folder in `app/modules/`.
Adding a feature = adding a folder. Zero edits to the loop.

Router registration follows the same auto-discovery pattern.

---

## 5. Tool-calling conventions

- Tools use OpenAI-style function schemas.
- Every tool has: clear `description`, typed params, sensible defaults.
- Handlers are sync or async. Return JSON-serialisable dicts.
- On malformed tool call: retry once with the parse error fed back. Then fail gracefully in plain language.
- Cap loop at 8 tool iterations per turn.
- Log every tool call to a `tool_calls` table. I want an audit trail.

---

## 6. KAI's persona

Write this into the system prompt.

- Addresses me by name. Never "user".
- Dry, understated wit. Confident. Never sycophantic.
- Short answers by default. Expands only when asked.
- Never opens with "Certainly!" or "I'd be happy to".
- States facts. Flags uncertainty once, briefly.
- Proactive but not naggy. Interrupts only for: reminders due, schedule conflicts, missed commitments, genuinely relevant news.
- Remembers everything. References past context naturally.
- Pushes back when I am making a bad call.

Persona lives in `app/llm/persona.md`, loaded at runtime. Editable without redeploy.

---

## 7. Time & data

- Store all timestamps UTC. Render in `KAI_TZ` (default `Asia/Kolkata`).
- Natural-language time parsing must handle: "tomorrow 7am", "in 20 mins", "every weekday 6pm", "next Monday".
- SQLite file at `/data/kai.db`, bind-mounted. Nightly backup to `/data/backups/`, keep 30.
- Nothing leaves the server. Ever.

---

## 8. Config (`.env.example`)

```
KAI_OWNER_NAME=
KAI_TZ=Asia/Kolkata
KAI_MODEL=qwen3:8b
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
DATABASE_URL=sqlite:////data/kai.db
NTFY_URL=https://ntfy.sh
NTFY_TOPIC=
API_TOKEN=
LOG_LEVEL=INFO
```

---

## 9. How I want you to work

For each task:

1. Restate task in 2 lines. Confirm scope.
2. List files you will create or edit.
3. Build it.
4. Run it. Show me it works — tests, curl output, or screenshots.
5. Write a short walkthrough artifact: what changed, how to test, what is next.
6. Stop. Wait for me.

If a task conflicts with an earlier decision, tell me before coding.
If I ask for something dumb, say so.

---

## 10. Definition of done for V1

- `docker compose up` starts everything clean.
- I open the PWA over Tailscale on my phone. It works.
- I say "remind me to call mom at 6pm". Phone buzzes at 6pm.
- I say "add buy milk to my list". It persists across restart.
- Conversation history survives restart.
- `/health` returns green.
- README explains setup in under 10 steps.
