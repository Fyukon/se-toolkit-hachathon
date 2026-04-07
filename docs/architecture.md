# Architecture

## Components

- `backend`: API, sync, summaries, action parsing, applying changes.
- `bot`: Telegram bot for commands, notifications and fast entry points.
- `miniapp`: Telegram WebApp interface for rich flows and confirmations.
- `db`: PostgreSQL for users, events, tasks, summaries and change requests.

## Main flow

1. Telegram bot opens Mini App or triggers quick commands.
2. Mini App or bot calls backend endpoints.
3. Backend synchronizes with SingularityApp.
4. Backend stores normalized data in PostgreSQL.
5. Backend generates summaries or drafts changes.
6. Confirmed changes are applied back to SingularityApp.
