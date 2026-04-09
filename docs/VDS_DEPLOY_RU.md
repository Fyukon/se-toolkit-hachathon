# Деплой на VDS

Этот проект можно поднять на одном VDS через Docker Compose. В production используется:

- `db` — PostgreSQL
- `backend` — FastAPI API
- `backend-init` — одноразовая инициализация таблиц
- `bot` — Telegram bot
- `miniapp` — собранный React frontend
- `caddy` — reverse proxy и HTTPS

## Что уже сделано в коде

- backend, bot и miniapp упакованы в контейнеры;
- для production есть [`docker-compose.prod.yml`](/home/alex/PycharmProjects/se-toolkit-hachathon/docker-compose.prod.yml);
- Mini App в production теперь собирается в статические файлы и отдаётся через `nginx`;
- внешний HTTPS трафик принимает `Caddy`, он же проксирует:
  - `/api/*` -> backend
  - `/` -> miniapp

## Что нужно сделать вручную

1. Подготовить VDS:
   - установить Docker и Docker Compose plugin;
   - открыть порты `80` и `443` в firewall/security group;
   - привязать домен или поддомен к IP VDS.

2. Склонировать репозиторий на сервер.

3. Создать `.env` на основе [`.env.example`](/home/alex/PycharmProjects/se-toolkit-hachathon/.env.example).

4. Заполнить production-значения:
   - `APP_DOMAIN=your-domain.example`
   - `BACKEND_CORS_ORIGINS=https://your-domain.example`
   - `VITE_BACKEND_URL=https://your-domain.example/api`
   - `TELEGRAM_WEBAPP_URL=https://your-domain.example`
   - `TELEGRAM_BOT_TOKEN=<реальный токен>`
   - `POSTGRES_PASSWORD=<сильный пароль>`
   - `LLM_API_KEY=<OpenRouter API key>`
   - `LLM_MODEL=google/gemma-4-26b-a4b-it`
   - `LLM_BASE_URL=https://openrouter.ai/api/v1`
   - при желании `LLM_SITE_URL=https://your-domain.example`
   - при необходимости `BACKEND_DEBUG=false`

5. Запустить production stack:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Если база новая и таблиц ещё нет, один раз отдельно инициализировать схему:

```bash
docker compose -f docker-compose.prod.yml run --rm --profile manual-init backend-init
```

6. Проверить:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs backend --tail=100
docker compose -f docker-compose.prod.yml logs bot --tail=100
```

7. Проверить backend через внешний домен:

```bash
curl https://your-domain.example/api/health
```

8. В `@BotFather` указать Mini App URL:
   - `https://your-domain.example`

## Если backend не видит Postgres внутри Docker

Если внутри контейнера `backend` имя `db` резолвится, но соединение на `5432` всё равно уходит в timeout, это уже не проблема приложения, а проблема bridge-сети Docker на хосте.

Обходной путь:

1. в `.env` поставить:

```env
POSTGRES_HOST=host.docker.internal
```

2. перезапустить стек.

В compose уже добавлен `host-gateway`, так что backend и `backend-init` смогут ходить к опубликованному на хосте Postgres через `5432`.

Если даже это не помогает локально, можно вообще обойтись без Postgres для dev-режима и включить SQLite:

```env
DATABASE_URL_OVERRIDE=sqlite+pysqlite:////app/runtime/local.db
```

После этого:

```bash
docker compose up --build
docker compose run --rm --profile manual-init backend-init
```

Для production на VDS этот fallback лучше не использовать.

## Полезные команды

Пересборка:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Остановка:

```bash
docker compose -f docker-compose.prod.yml down
```

Просмотр логов:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f bot
docker compose -f docker-compose.prod.yml logs -f caddy
```

## Ограничения текущей Version 2

- day/week summary пока строятся только по данным SingularityApp API, которые доступны через текущий task flow;
- не все поля `priority` приходят от SingularityApp для всех задач;
- LLM в action parsing используется только для понимания команды; confirm/apply по-прежнему контролируется backend;
- action UI и Telegram flow уже поддерживают `draft -> confirm/cancel`, но parser пока покрывает только `move_task`, `create_task`, `complete_task`.
