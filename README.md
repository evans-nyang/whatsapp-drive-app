# whatsapp-drive-app

Event-driven service that receives images via WhatsApp and stores them in Google Drive.
WhatsApp is only used for receiving media and sending confirmations — all processing,
storage, logging, and notification logic lives in independent backend services connected
through RabbitMQ.

## Architecture

```
WhatsApp Business API
        |  (webhook: image message)
        v
FastAPI webhook service  --(publish: media.received)-->  RabbitMQ (topic exchange: media.events)
                                                                 |
                                          -----------------------------------------
                                          |                                       |
                                          v                                       v
                               Media processing worker                Notification worker
                               (consumes media.received)               (consumes media.uploaded /
                                          |                              media.failed)
                    downloads from WhatsApp, uploads to                          |
                    Google Drive, writes metadata to Postgres                    v
                    publishes media.uploaded / media.failed          sends confirmation via
                                                                       WhatsApp Business API
```

Every service is stateless and independently scalable:

- **webhook service** — verifies signatures, dedupes via Redis, publishes an event. Never
  talks to Google Drive or WhatsApp media endpoints directly. Responds in milliseconds.
- **media worker** — the only service that talks to Google Drive. Pulls jobs off the queue,
  does the download/upload, records status in Postgres.
- **notification worker** — the only service that sends WhatsApp messages back to users.
  Fully decoupled so a WhatsApp API hiccup never blocks storage.

## Project structure

```
whatsapp-drive-app/
├── app/
│   ├── config.py              # pydantic-settings, all config from env vars
│   ├── logging_config.py      # loguru setup (structured JSON logs)
│   ├── schemas.py             # pydantic event schemas shared across services
│   ├── db/
│   │   ├── base.py            # SQLAlchemy declarative base
│   │   ├── models.py          # User, MediaEvent ORM models
│   │   └── session.py         # async engine + session factory
│   ├── messaging/
│   │   └── rabbitmq.py        # connection, exchange, publish/consume helpers
│   ├── cache/
│   │   └── redis_client.py    # redis connection factory
│   ├── services/
│   │   ├── whatsapp_client.py # WhatsApp Cloud API wrapper (media + send message)
│   │   └── drive_client.py    # Google Drive upload wrapper
│   ├── webhook/
│   │   ├── main.py            # FastAPI app — the only HTTP-facing service
│   │   └── security.py        # HMAC signature verification
│   └── workers/
│       ├── media_worker.py        # consumes media.received
│       └── notification_worker.py # consumes media.uploaded / media.failed
├── migrations/                # Alembic migrations
│   ├── env.py
│   └── versions/0001_initial.py
├── tests/
│   └── test_webhook.py
├── docker-compose.yml
├── Dockerfile.webhook
├── Dockerfile.worker
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Local development

1. Copy the environment template and fill in real credentials:

   ```bash
   cp .env.example .env
   ```

   You'll need:
   - `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`,
     `WHATSAPP_PHONE_NUMBER_ID` — from the Meta App Dashboard.
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — path to a Google service account key with Drive
     API access (or use OAuth per-user, see `app/services/drive_client.py` docstring).

2. Bring up the whole stack:

   ```bash
   docker compose up --build
   ```

   This starts Postgres, Redis, RabbitMQ (with management UI on `:15672`), the webhook
   service (`:8000`), the media worker, and the notification worker.

3. Run migrations (first time, or after changing models):

   ```bash
   docker compose exec webhook alembic upgrade head
   ```

4. Expose your local webhook to the internet for Meta to reach it (e.g. `ngrok http 8000`),
   and register `https://<your-tunnel>/webhook` plus your `WHATSAPP_VERIFY_TOKEN` in the
   Meta App Dashboard.

## Running tests

```bash
pip install -r requirements.txt
pytest tests/
```

## Scaling in production

- Run `webhook`, `media-worker`, and `notification-worker` as separate deployments/services
  (Kubernetes Deployments, Cloud Run services, ECS services — whatever your platform is).
  Scale each independently based on its own load (webhook scales with WhatsApp traffic,
  media worker scales with queue depth).
- Use managed Postgres, Redis, and RabbitMQ (e.g. Cloud SQL, Memorystore, CloudAMQP) rather
  than self-hosting in production.
- Run `alembic upgrade head` as a one-off migration job/init container in CI/CD — never on
  application boot, to avoid multiple replicas racing to migrate simultaneously.
- Point Loguru at stdout only (already the default here) and let your platform's log
  aggregator (Cloud Logging, CloudWatch, etc.) collect it centrally.
