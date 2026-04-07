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

- Natural language changes to the schedule.
- Confirmation flow for write actions.
- Real LLM-generated summary text.
- Rich parsing of every SingularityApp entity beyond tasks.

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

Services:

- Backend API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Mini App dev server: `http://localhost:5173`

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
