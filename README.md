# se-toolkit-hachathon

Telegram bot and Telegram Mini App for syncing SingularityApp tasks, storing them locally, and generating day/week summaries.

## Product context

- End user: student or knowledge worker who keeps tasks in SingularityApp.
- Problem: it is inconvenient to manually inspect the calendar and task list every time you want a quick overview of the day or week.
- Solution: connect a SingularityApp API token once, sync tasks into the service, then get compact summaries through Telegram or the Mini App.

## Version 1 scope

Implemented:

- FastAPI backend with PostgreSQL connection.
- Manual connection flow through SingularityApp API token.
- Full sync endpoint for tasks.
- Day and week summaries based on synced tasks.
- Telegram bot commands `/connect`, `/sync`, `/day`, `/week`.
- Telegram Mini App for connect, sync, day summary, and week summary.
- Docker Compose setup with db, backend, backend-init, bot, and miniapp.

Not implemented yet:

- Real LLM-generated summary text.
- Rich parsing of every SingularityApp entity beyond tasks.
- Full-fledged LLM parser instead of the current deterministic Version 2 parser.

## Version 2 current backend scope

The repository now includes an initial Version 2 action pipeline:

- `POST /actions/parse` — convert a natural-language command into a draft
- `GET /actions/{id}` — inspect a draft
- `POST /actions/{id}/confirm` — apply a confirmed draft to SingularityApp
- `POST /actions/{id}/cancel` — cancel a draft

Currently supported action intents:

- `move_task`
- `create_task`
- `complete_task`

The parser now supports an OpenRouter-backed LLM parse step with deterministic fallback. The confirmation and apply flow stays backend-controlled.

Recommended LLM setup:

- `LLM_API_KEY=<OpenRouter API key>`
- `LLM_MODEL=google/gemma-4-26b-a4b-it`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`

## SingularityApp token

Version 1 uses a REST API token from SingularityApp, not OAuth.

According to SingularityApp documentation, API tokens are created in the account dashboard and can be scoped to entities such as tasks. Save a token with task read access and use it in `/auth/connect` or in the Mini App.

## Local run

1. Copy `.env.example` to `.env`.
2. Put real values into:
   - `TELEGRAM_BOT_TOKEN`
   - `SINGULARITY_API_TOKEN` or provide the token via `/connect`
   - `VITE_BACKEND_URL`
3. Start the stack:

```bash
docker compose up --build
```

If you start with a fresh PostgreSQL volume, initialize the schema once:

```bash
docker compose run --rm --profile manual-init backend-init
```

If `backend` resolves `db` but still gets `connection timeout expired`, your Docker bridge network is likely broken on the host. In that case:

1. set `POSTGRES_HOST=host.docker.internal` in `.env`
2. restart the stack

If Telegram bot cannot reach backend and shows `Server disconnected without sending a response`, use the same workaround for bot -> backend:

```env
BACKEND_INTERNAL_URL=http://host.docker.internal:8000
```

If that still does not work locally, use a file-backed SQLite override for development:

```env
DATABASE_URL_OVERRIDE=sqlite+pysqlite:////app/runtime/local.db
```

Then restart the stack and initialize the schema once:

```bash
docker compose up --build
docker compose run --rm --profile manual-init backend-init
```

Services:

- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Mini App dev server: `http://localhost:5173`

## Production / VDS

For a server deployment use [`docker-compose.prod.yml`](/home/alex/PycharmProjects/se-toolkit-hachathon/docker-compose.prod.yml).

Production stack:

- `db` — PostgreSQL
- `backend` — FastAPI
- `backend-init` — database initialization
- `bot` — Telegram bot
- `miniapp` — static frontend served by nginx
- `caddy` — HTTPS reverse proxy

The production proxy serves:

- `https://your-domain.example/` -> Mini App
- `https://your-domain.example/api/*` -> backend

Detailed VDS instructions are in [`docs/VDS_DEPLOY_RU.md`](/home/alex/PycharmProjects/se-toolkit-hachathon/docs/VDS_DEPLOY_RU.md).

## Main API flow

### 1. Connect account

```bash
curl -X POST http://localhost:8000/auth/connect \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": "123456789",
    "singularity_api_token": "YOUR_TOKEN",
    "timezone": "Europe/Moscow"
  }'
```

### 2. Run sync

```bash
curl -X POST http://localhost:8000/sync/full \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": "123456789",
    "timezone": "Europe/Moscow"
  }'
```

### 3. Fetch summaries

```bash
curl "http://localhost:8000/summary/day?telegram_id=123456789"
curl "http://localhost:8000/summary/week?telegram_id=123456789"
```

## Telegram bot

After you set a real `TELEGRAM_BOT_TOKEN`, the bot supports:

- `/start`
- `/connect <singularity_api_token>`
- `/sync`
- `/day`
- `/week`
- `/action <command>`
- `/confirm <id>`
- `/cancel_action <id>`

It also sends a keyboard button that opens the Mini App URL from `TELEGRAM_WEBAPP_URL`.

## Tests

Backend tests cover:

- sync upsert logic;
- datetime parsing;
- deterministic summary generation;
- basic user resolution and apply-changes contract.

Run locally from the repo root:

```bash
PYTHONPATH=backend pytest backend/tests
```
