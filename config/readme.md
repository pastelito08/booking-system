# Booking System API

A REST API for reserving resources (rooms, courts, equipment) for a time slot,
built with Django REST Framework and PostgreSQL. Double bookings are prevented
**at the database level**, not just in Python code.

## Features

- JWT authentication (register, login, token refresh)
- Resources that staff manage and users browse
- Bookings with status flow: `pending` -> `confirmed` / `cancelled`
- Availability endpoint showing booked and free slots for a day
- Users see and cancel only their own bookings; staff see and confirm all
- Validation: no past bookings, end after start, maximum 8 hours
- Filtering and search, pagination
- Interactive Swagger documentation
- 27 automated tests

## How double booking is prevented

Two layers protect every resource:

1. **Serializer validation** checks for overlapping bookings and returns a
   clear error message (`This time slot is already booked.`).
2. **PostgreSQL `ExclusionConstraint`** rejects overlapping time ranges for the
   same resource, even if two requests arrive at the same instant (a race
   condition that Python-only checks cannot stop). The API catches the
   resulting `IntegrityError` and returns a normal `400` response.

Cancelled bookings are excluded from the constraint, so a cancelled slot can be
booked again. Back-to-back bookings (14:00-16:00 and 16:00-18:00) are allowed.

## Tech stack

Python, Django, Django REST Framework, PostgreSQL, SimpleJWT, django-filter,
drf-spectacular

## Getting started

**Requirements:** Python 3.12+, PostgreSQL

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Create a database named `bookingdb` in PostgreSQL, then copy the example
environment file and fill in your values:

```bash
copy .env.example .env         # macOS/Linux: cp .env.example .env
```

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- API docs (Swagger): http://127.0.0.1:8000/api/docs/
- Admin: http://127.0.0.1:8000/admin/

## API endpoints

| Method | Endpoint | Description | Access |
|---|---|---|---|
| POST | `/api/auth/register/` | Create an account | Public |
| POST | `/api/auth/login/` | Get access and refresh tokens | Public |
| POST | `/api/auth/token/refresh/` | Get a new access token | Public |
| GET | `/api/resources/` | List resources (`?search=`) | Logged in |
| POST/PATCH/DELETE | `/api/resources/{id}/` | Manage resources | Staff |
| GET | `/api/resources/{id}/availability/?date=YYYY-MM-DD` | Booked and free slots | Logged in |
| GET | `/api/bookings/` | Your bookings (`?status=`, `?resource=`) | Logged in |
| POST | `/api/bookings/` | Create a booking | Logged in |
| PATCH | `/api/bookings/{id}/` | Edit your booking | Owner / staff |
| POST | `/api/bookings/{id}/cancel/` | Cancel a booking | Owner / staff |
| POST | `/api/bookings/{id}/confirm/` | Confirm a pending booking | Staff |

Authenticated requests need the header `Authorization: Bearer <access_token>`.

### Example

```http
POST /api/bookings/
{
  "resource": 1,
  "start_time": "2026-11-10T14:00:00Z",
  "end_time": "2026-11-10T16:00:00Z",
  "notes": "Team meeting"
}
```

Sending an overlapping slot returns `400`:

```json
{"non_field_errors": ["This time slot is already booked."]}
```

## Running the tests

```bash
python manage.py test
```

The suite covers overlap rules, back-to-back bookings, cancellation, the
database constraint on its own, permissions, availability and registration.

## Project structure

```
config/      project settings and root URLs
users/       custom user model, registration
bookings/    models, serializers, views, tests
```

## Roadmap

- Docker and docker-compose
- GitHub Actions CI
- Email notifications with Celery
- Recurring bookings
- Per-resource opening hours


# Booking System API

A REST API for reserving resources (rooms, courts, equipment) for a time slot, built with **Django REST Framework** and **PostgreSQL**.

Double bookings are prevented **at the database level**, not only in Python code. Emails are sent in the background with **Celery + Redis**, and the whole stack starts with one command using **Docker Compose**.

## Table of contents

1. [Features](#features)
2. [Tech stack and packages](#tech-stack-and-packages)
3. [How double booking is prevented](#how-double-booking-is-prevented)
4. [Booking lifecycle](#booking-lifecycle)
5. [Project structure](#project-structure)
6. [Run with Docker (recommended)](#run-with-docker-recommended)
7. [Run locally without Docker](#run-locally-without-docker)
8. [Environment variables](#environment-variables)
9. [API endpoints](#api-endpoints)
10. [Using the API](#using-the-api)
11. [Celery: background and scheduled tasks](#celery-background-and-scheduled-tasks)
12. [Rate limiting](#rate-limiting)
13. [Tests](#tests)
14. [API documentation](#api-documentation)
15. [Design decisions and known limitations](#design-decisions-and-known-limitations)
16. [Interview questions and answers](#interview-questions-and-answers)

---

## Features

- JWT authentication: register, login, token refresh
- Resources that staff manage and users browse (search supported)
- Bookings with a status flow: `pending` -> `confirmed` / `cancelled` -> `completed`
- Availability endpoint showing booked and free slots for a day
- Users see and cancel only their own bookings; staff see, confirm and delete all
- Validation: no past bookings, end after start, maximum 8 hours, active resources only
- **Double-booking protection** with a PostgreSQL exclusion constraint
- **Background emails** on booking created, confirmed and cancelled (Celery + Redis)
- **Scheduled job** that marks finished confirmed bookings as `completed` (Celery Beat)
- **Rate limiting**: 10 requests per hour, with a clear message afterwards
- Filtering, search and pagination
- Interactive Swagger documentation
- Automated test suite
- Docker Compose setup (web, PostgreSQL, Redis, Celery worker, Celery Beat)

## Tech stack and packages

| Package / tool | Purpose in this project |
|---|---|
| **Python 3.12** | Language |
| **Django 6.1** | Web framework, ORM, admin, migrations |
| **Django REST Framework** | Serializers, viewsets, routers, permissions, throttling |
| **djangorestframework-simplejwt** | JWT login (`access` and `refresh` tokens) |
| **django-filter** | Filtering, for example `?status=pending&resource=1` |
| **drf-spectacular** | Generates the OpenAPI schema and Swagger UI |
| **psycopg2-binary** | Driver connecting Python to PostgreSQL |
| **python-decouple** | Reads secrets from `.env` or environment variables |
| **Celery** | Runs tasks in the background and on a schedule |
| **redis** (Python client) | Lets Celery talk to Redis |
| **PostgreSQL 16** | Database (needed for the exclusion constraint) |
| **Redis 7** | Message broker (the queue between Django and the Celery worker) |
| **Docker and Docker Compose** | Packages and starts the whole stack |

Django 6.1 note: email is configured with the `MAILERS` setting, which replaces the older `EMAIL_BACKEND` setting.

## How double booking is prevented

Two layers protect every resource:

1. **Serializer validation** checks for overlapping bookings and returns a clear error (`This time slot is already booked.`).
2. **PostgreSQL `ExclusionConstraint`** rejects overlapping time ranges for the same resource, even if two requests arrive at the same instant. This is a race condition that Python-only checks cannot stop. The API catches the resulting `IntegrityError` and returns a normal `400` response.

Details:

- The constraint uses `tstzrange(start_time, end_time)` with the `&&` (overlaps) operator and `resource` equality. It needs the `btree_gist` extension, enabled in the first migration with `BtreeGistExtension()`.
- Cancelled bookings are excluded from the constraint, so a cancelled slot can be booked again.
- Back-to-back bookings (14:00-16:00 and 16:00-18:00) are allowed, because PostgreSQL ranges include the start and exclude the end.
- A `CheckConstraint` also guarantees `end_time > start_time`.

## Booking lifecycle

```
            user creates            staff confirms            Celery Beat, after end time
(request) --------------> pending ---------------> confirmed --------------------------> completed
                             |                         |
                             +---- user/staff cancels -+----> cancelled (slot is free again)
```

| Status | Meaning |
|---|---|
| `pending` | Requested, waiting for approval. The slot is held |
| `confirmed` | Approved by staff |
| `cancelled` | Called off. Kept for history, and the slot becomes free |
| `completed` | Confirmed booking whose end time has passed (set automatically) |

Users cannot set `status` or `user` themselves. Both are read-only in the serializer.

## Project structure

```
bookingsystem/
├── config/
│   ├── settings.py        # settings, DRF, JWT, Celery, MAILERS, throttling
│   ├── urls.py            # root URLs, Swagger, auth
│   ├── celery.py          # Celery app
│   ├── exceptions.py      # custom 429 (throttled) message
│   └── __init__.py        # loads Celery on startup
├── users/                 # custom user model, registration
├── bookings/
│   ├── models.py          # Resource, Booking, constraints
│   ├── serializers.py     # validation and overlap check
│   ├── views.py           # viewsets, permissions, availability, cancel, confirm
│   ├── tasks.py           # Celery tasks (emails, auto-complete)
│   ├── urls.py            # router
│   └── tests.py           # test suite
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example           # copy to .env and fill in
├── requirements.txt
└── manage.py
```

## Run with Docker (recommended)

**You need:** Docker Desktop (Windows/macOS) or Docker Engine (Linux). Nothing else: no Python, PostgreSQL or Redis installation.

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
docker compose up --build
```

This starts five containers:

| Container | Runs |
|---|---|
| `web` | The Django API on http://localhost:8000 (runs `migrate` first) |
| `db` | PostgreSQL 16 with an empty `bookingdb` |
| `redis` | Redis, the task queue |
| `worker` | Celery worker (sends emails, runs tasks) |
| `beat` | Celery Beat (scheduler for periodic tasks) |

Then, in a second terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

Open:

- API docs (Swagger): http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/

**Useful commands**

```bash
docker compose up -d                       # start in the background
docker compose logs -f worker              # watch the Celery worker (emails print here)
docker compose exec web python manage.py test   # run the tests inside the container
docker compose down                        # stop (data is kept)
docker compose down -v                     # stop and delete the database volume
```

**Good to know**

- Anyone running the project with Docker gets their **own empty database**, built from the migrations. Your local data is never shared.
- By default emails are **printed in the worker logs** (console backend). To send real email, set `EMAIL_USER` and `EMAIL_PASSWORD` (see below).
- The `db` and `redis` ports are not published to your computer, so they will not clash with a PostgreSQL or Redis already installed on it.

## Run locally without Docker

**Requirements:** Python 3.12+, PostgreSQL, and a Redis server (on Windows the easiest way is a Redis container: `docker run --name booking-redis -p 6379:6379 -d redis:7`).

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

1. Create a PostgreSQL database named `bookingdb`.
2. Copy the example environment file and fill in your values:

   ```bash
   copy .env.example .env     # macOS/Linux: cp .env.example .env
   ```

3. Set up the database and create an admin user:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. Start the three processes, each in its own terminal (virtual environment active):

   ```bash
   python manage.py runserver
   celery -A config worker --pool=solo -l info
   celery -A config beat -l info
   ```

`--pool=solo` is needed for the Celery worker on Windows. On Linux and macOS you can omit it.

## Environment variables

Real values go in `.env` (never committed). `.env.example` shows the names.

| Variable | Example | Meaning |
|---|---|---|
| `SECRET_KEY` | long random string | Django secret key |
| `DEBUG` | `True` | Debug mode (use `False` in production) |
| `DB_NAME` | `bookingdb` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | `your-password` | Database password |
| `DB_HOST` | `localhost` (`db` in Docker) | Database host |
| `DB_PORT` | `5432` | Database port |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` (`redis://redis:6379/0` in Docker) | Where the Celery queue lives |
| `EMAIL_USER` | `you@gmail.com` | Optional: sender address for real emails |
| `EMAIL_PASSWORD` | Gmail app password | Optional: leave empty to print emails in the console |

Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## API endpoints

| Method | Endpoint | Description | Access |
|---|---|---|---|
| POST | `/api/auth/register/` | Create an account | Public |
| POST | `/api/auth/login/` | Get `access` and `refresh` tokens | Public |
| POST | `/api/auth/token/refresh/` | Get a new access token | Public |
| GET | `/api/resources/` | List resources (`?search=`) | Logged in |
| POST | `/api/resources/` | Create a resource | Staff |
| GET | `/api/resources/{id}/` | One resource | Logged in |
| PATCH / PUT | `/api/resources/{id}/` | Edit a resource | Staff |
| DELETE | `/api/resources/{id}/` | Delete (blocked with `400` if it has bookings) | Staff |
| GET | `/api/resources/{id}/availability/?date=YYYY-MM-DD` | Booked and free slots (09:00-18:00) | Logged in |
| GET | `/api/bookings/` | Your bookings (`?status=`, `?resource=`) | Logged in |
| POST | `/api/bookings/` | Create a booking | Logged in |
| GET | `/api/bookings/{id}/` | One booking | Owner / staff |
| PATCH | `/api/bookings/{id}/` | Edit a booking | Owner / staff |
| POST | `/api/bookings/{id}/cancel/` | Cancel a booking | Owner / staff |
| POST | `/api/bookings/{id}/confirm/` | Confirm a pending booking | Staff |
| DELETE | `/api/bookings/{id}/` | Permanently delete a booking | Staff |

Authenticated requests need the header `Authorization: Bearer <access_token>`.

## Using the API

**1. Register**

```http
POST /api/auth/register/
{"username": "ram", "email": "ram@example.com", "password": "StrongPass#2026"}
```

**2. Log in** and copy the `access` token

```http
POST /api/auth/login/
{"username": "ram", "password": "StrongPass#2026"}
```

**3. Create a booking** (a staff user must create the resource first)

```http
POST /api/bookings/
Authorization: Bearer <access_token>

{
  "resource": 1,
  "start_time": "2026-11-12T14:00:00+05:45",
  "end_time": "2026-11-12T16:00:00+05:45",
  "notes": "Team meeting"
}
```

The booking starts as `pending`, and a confirmation email is queued in the background.

**4. Overlapping slot returns `400`**

```json
{"non_field_errors": ["This time slot is already booked."]}
```

**5. Check availability**

```http
GET /api/resources/1/availability/?date=2026-11-12
```

```json
{
  "resource": 1,
  "date": "2026-11-12",
  "booked": [{"start": "...T14:00:00+05:45", "end": "...T16:00:00+05:45"}],
  "free": [
    {"start": "...T09:00:00+05:45", "end": "...T14:00:00+05:45"},
    {"start": "...T16:00:00+05:45", "end": "...T18:00:00+05:45"}
  ]
}
```

**6. Cancel or confirm**

```http
POST /api/bookings/5/cancel/     # owner or staff
POST /api/bookings/5/confirm/    # staff only
```

Tip: access tokens last 1 hour by default in this project's settings (adjust `SIMPLE_JWT` in `settings.py`). Use `/api/auth/token/refresh/` with your `refresh` token to get a new one.

## Celery: background and scheduled tasks

**Why Celery?** Sending an email can take seconds and can fail. Doing it inside the request would make the user wait. Instead, the view puts a small message in Redis and answers immediately. A separate **worker** process picks the message up and does the work.

```
Django view --(.delay)--> Redis (queue) --> Celery worker --> sends the email
     |
     +--> responds to the user immediately

Celery Beat (scheduler) --every 10 min--> Redis --> worker --> complete_past_bookings()
```

| Piece | Role |
|---|---|
| **Django** | Takes the request and queues tasks |
| **Redis** | The broker: the queue between Django and the worker |
| **Celery worker** | A separate process that runs the tasks |
| **Celery Beat** | Scheduler that queues periodic tasks |

**Tasks** (`bookings/tasks.py`):

| Task | Triggered by | What it does |
|---|---|---|
| `send_booking_email(booking_id, event)` | Booking created, confirmed, cancelled | Emails the booking owner (skips users with no email) |
| `complete_past_bookings()` | Celery Beat, every 10 minutes | Sets `confirmed` bookings whose end time passed to `completed` |

Design notes:

- Tasks receive only the booking **id**, not the object. Queued messages should stay small, and the task loads fresh data when it runs.
- Emails are queued with `transaction.on_commit(...)`, so the worker never runs before the booking is saved.
- The schedule lives in `CELERY_BEAT_SCHEDULE` in `settings.py`.
- In tests, `CELERY_TASK_ALWAYS_EAGER=True` runs tasks immediately, so Redis is not needed.

**Real emails with Gmail:** turn on 2-Step Verification, create an app password, then set `EMAIL_USER` and `EMAIL_PASSWORD` in `.env`. Restart the worker (it reads settings only at startup). Without them, emails print in the worker terminal.

## Rate limiting

All endpoints are limited to **10 requests per hour** (per user when logged in, per IP address when anonymous). The 11th request returns `429 Too Many Requests`:

```json
{
  "detail": "Request limit reached (10 requests per hour). Please try again after 1 hour.",
  "retry_after_seconds": 3541
}
```

The values are set in `DEFAULT_THROTTLE_RATES` in `settings.py`, and the message comes from `config/exceptions.py`. Counters live in the cache. 10 per hour is strict, so raise it (for example `1000/hour`) if you test heavily, and restart the server to reset the counters in development.

## Tests

```bash
python manage.py test                 # locally
docker compose exec web python manage.py test   # inside Docker
```

Django creates a temporary `test_bookingdb`, runs the tests, and deletes it, so your real data is never touched. The suite covers:

- Overlapping, identical, back-to-back, cancelled-slot and different-resource bookings
- The PostgreSQL constraint on its own, bypassing the serializer
- Validation: past dates, end before start, 8-hour limit, inactive resources
- Permissions: users see only their own bookings, only staff can confirm or delete
- Availability, registration, login and weak passwords
- Rate limiting and the custom 429 message
- Booking emails and the auto-complete task

## API documentation

Interactive Swagger UI is generated from the code by drf-spectacular:

- Swagger UI: `/api/docs/`
- Raw OpenAPI schema: `/api/schema/`

To call protected endpoints from Swagger, log in through `POST /api/auth/login/`, click **Authorize**, and paste the `access` token (without the word `Bearer`).

## Design decisions and known limitations

**Decisions**

- Bookings are **cancelled, not deleted**, so history is kept. Only staff can hard-delete.
- `Resource` uses `on_delete=PROTECT` on bookings, so a resource with bookings cannot be deleted. Set `is_active=false` to hide it instead.
- `get_queryset` filters bookings by user, so other people's bookings return `404`, which does not reveal that they exist.
- Secrets live in environment variables, never in the repository.

**Known limitations**

- Opening hours (09:00-18:00) are global, not per resource.
- A confirmed booking can still be edited with `PATCH`.
- The "no past dates" check also blocks editing the notes of a booking that already started.
- The default throttle cache is per process. With several server workers, use Redis as the Django cache so counters are shared.
- The development server (`runserver`) is used in Docker. A production setup should use Gunicorn, `DEBUG=False`, and `ALLOWED_HOSTS`.

**Possible next steps:** per-resource opening hours, recurring bookings, token blacklist for logout, payments, GitHub Actions CI, deployment.

---

## Interview questions and answers

### Project and design

**1. Explain this project in one minute.**
It is a REST API where users reserve resources such as rooms for a time slot. The key problem is preventing double bookings, which I solve with serializer validation plus a PostgreSQL exclusion constraint. It also has JWT auth, role-based permissions, background emails with Celery and Redis, a scheduled job that completes finished bookings, rate limiting, tests, Swagger docs and a Docker Compose setup.

**2. How do you prevent double booking?**
Two layers. The serializer queries for overlapping non-cancelled bookings and returns a friendly `400`. The database also has an `ExclusionConstraint` using `tstzrange` and the overlap operator, scoped to the same resource, so even two simultaneous requests cannot both succeed.

**3. Why is checking in Python not enough?**
It is a race condition (check-then-insert). Two requests can both run the check before either inserts, see no conflict, and both insert. A database constraint is checked atomically at insert time, so it is the only reliable guard.

**4. What happens when the constraint rejects the second request?**
PostgreSQL raises an `IntegrityError`. In `perform_create`, I wrap the save in `transaction.atomic()`, catch the error, and raise a DRF `ValidationError`, so the client gets a normal `400` instead of a `500`.

**5. How is the overlap test written, and why are back-to-back bookings allowed?**
Two ranges overlap when `existing.start < new.end` and `existing.end > new.start`. With strict inequalities, a booking ending at 16:00 and another starting at 16:00 do not overlap. PostgreSQL ranges are half-open (start included, end excluded), so the constraint agrees.

**6. Why PostgreSQL and not SQLite?**
Exclusion constraints, range types and the `btree_gist` extension are PostgreSQL features. SQLite cannot enforce this rule at the database level.

**7. What is `btree_gist` and why was it needed?**
The constraint combines a range overlap (`&&`) with plain equality on `resource_id`. GiST indexes need an operator class for equality on ordinary types, and `btree_gist` provides it. I enable it with `BtreeGistExtension()` at the top of the first migration, before the table is created.

**8. Why does a cancelled booking not block the slot?**
The constraint has `condition=~Q(status="cancelled")`, so cancelled rows are ignored. The row stays for history, but the slot becomes free.

**9. Why use a `status` field instead of deleting bookings?**
To keep history for reports, disputes and refunds, and to show users their past bookings. Cancelling is a status change, and deleting is restricted to staff.

**10. Why `DecimalField` for price?**
Floats cannot represent many decimal values exactly (`0.1 + 0.2` gives `0.30000000000000004`). Decimal is exact, which matters for money.

### Django and DRF

**11. What is a serializer?**
It validates incoming data and converts it into Python objects to save, and it converts model instances back to JSON. `ModelSerializer` generates fields from the model.

**12. What is the difference between `validate_<field>` and `validate`?**
`validate_<field>` checks one field. `validate` runs after all fields pass and is used for rules that compare fields, like end after start and the overlap check.

**13. Why are `user` and `status` read-only?**
So clients cannot book on behalf of another user or confirm their own booking. The view sets `user` from `request.user`, and status changes only through the cancel and confirm actions.

**14. Authentication versus authorization?**
Authentication answers "who are you" (the JWT). Authorization answers "what may you do" (permissions: `IsAuthenticated`, `IsAdminUser`, my `IsAdminOrReadOnly`, and `get_queryset` filtering).

**15. How do users only see their own bookings?**
`get_queryset` filters by `request.user` unless the user is staff. Because every endpoint, including detail, cancel and PATCH, uses that queryset, another user's booking returns `404`.

**16. What is `is_staff` versus `is_superuser`?**
`is_staff` allows access to staff-only features (my API checks this). `is_superuser` grants all permissions. `createsuperuser` sets both. Being logged in does not make someone staff.

**17. What is the N+1 query problem and how did you avoid it?**
Listing N bookings and then accessing each booking's resource and user triggers one query per row. `select_related("resource", "user")` fetches them in the same SQL query with a join.

**18. Why do you use `@action`?**
It adds custom endpoints to a ViewSet beyond CRUD, such as `cancel`, `confirm` and `availability`. The router generates their URLs automatically.

**19. Why did you set `http_method_names`?**
To control which HTTP methods a viewset accepts. It originally blocked `PUT` and `DELETE` for bookings, and now allows `DELETE` for staff only through `get_permissions`.

**20. What does a router do?**
It generates the URL patterns for a ViewSet (list, detail and custom actions), so I don't write each URL by hand. Because my ViewSets define `get_queryset()` instead of `queryset`, I must pass `basename`.

**21. Why a custom user model from the start?**
Switching `AUTH_USER_MODEL` after the first migration is painful. Defining `users.User(AbstractUser)` early lets me add fields later without migration problems.

**22. How are passwords stored?**
Hashed, never in plain text. I use `create_user()` in the register serializer, which hashes the password. The password field is `write_only`, so it is never returned.

**23. How did you handle timezones?**
`USE_TZ=True`, so datetimes are stored in UTC in the database and are timezone-aware. Clients can send an offset (`+05:45`), and I convert with `timezone.localtime()` when formatting times for emails.

**24. How does the availability endpoint work?**
It builds the day's window (09:00-18:00), loads non-cancelled bookings that touch it, sorts by start time, and walks through them with a cursor. A gap between the cursor and the next start is a free slot, and anything left before closing is free too. Bookings are clipped to the window with `max` and `min`.

### JWT, throttling and security

**25. How does JWT authentication work?**
The client logs in and receives a signed `access` token and a `refresh` token. It sends the access token in the `Authorization: Bearer` header. The server verifies the signature and expiry without a session lookup. When the access token expires, the refresh token gets a new one.

**26. Why are access tokens short-lived?**
A stolen access token is only dangerous until it expires. A longer-lived refresh token keeps users logged in.

**27. How would you implement a real logout with JWT?**
Enable SimpleJWT's token blacklist and blacklist the refresh token on logout. Otherwise logout is just the client deleting its tokens.

**28. How does throttling work, and what are its limits here?**
DRF counts requests per user (or IP for anonymous requests) in the cache and returns `429` over the limit. The default local-memory cache is per process, so with several workers the counters are not shared. In production I would use Redis as the cache.

**29. What security measures does the project have?**
Hashed passwords, JWT auth, permission classes, per-user querysets, read-only sensitive fields, password validation, rate limiting, secrets in environment variables, `.env` in `.gitignore`, and database constraints as a last line of defense.

### Celery and Redis

**30. What is Celery and why did you use it?**
A task queue. Sending email inside the request would slow it down and make it fail when the mail server is down. With Celery, the request queues the task and returns immediately, and a worker sends the email separately.

**31. What does Redis do here?**
It is the broker: the shared queue where Django leaves task messages and the worker picks them up. It stores queued tasks and results temporarily, not business data. Bookings live in PostgreSQL.

**32. What does `.delay()` do?**
It does not run the function. It serializes the task name and arguments, puts a message in the broker, and returns immediately. A worker later executes it.

**33. Why do tasks receive an id instead of the booking object?**
Messages must be small and serializable, and the object could be stale by the time the task runs. The task reloads fresh data from the database.

**34. Why `transaction.on_commit`?**
Without it, the worker might run before the booking transaction is committed and not find the row. `on_commit` queues the task only after the data is saved.

**35. What is Celery Beat?**
A scheduler process that puts periodic tasks on the queue (here, `complete_past_bookings` every 10 minutes). Workers then execute them. It runs as its own process.

**36. What happens if the worker is down?**
Messages wait in Redis and are processed when the worker starts. The API still works.

**37. What if the email task fails?**
It fails in the worker without affecting the user's request. I could add retries with `autoretry_for` and exponential backoff.

**38. How do you test Celery tasks?**
With `CELERY_TASK_ALWAYS_EAGER=True`, tasks run synchronously in the test process, with no Redis. Django's test runner captures sent emails in `mail.outbox`. For `on_commit` callbacks I use `captureOnCommitCallbacks(execute=True)`.

**39. Why `.update()` in `complete_past_bookings`?**
It changes all matching rows in a single SQL statement, which is much faster than loading and saving each object. It skips `save()` and signals, which I do not need here.

### Docker

**40. What is Docker and why did you use it?**
Docker packages an app with its dependencies into a container that runs the same way on any machine. It lets anyone start the whole project with `docker compose up`, without installing Python, PostgreSQL or Redis.

**41. Image versus container?**
An image is a built template (the recipe plus ingredients). A container is a running instance of an image.

**42. What do the Dockerfile and `docker-compose.yml` do?**
The Dockerfile describes how to build the Django image (base Python image, install requirements, copy code). Compose defines and starts several containers together (web, db, redis, worker, beat) and connects them on a network.

**43. How does the `web` container find the database?**
Compose puts containers on one network where each service name is a hostname. That is why `DB_HOST=db` and `redis://redis:6379/0` work.

**44. What is a volume and why is it used for PostgreSQL?**
A volume stores data outside the container's lifecycle. Without `pgdata`, the database would be lost whenever the container is recreated. `docker compose down -v` deletes it.

**45. Does someone running my project via Docker use my database?**
No. They get a fresh, empty database in their own volume, built from the migrations. My data stays on my machine, and `.env` is not in the repository.

**46. Why does `depends_on` use a health check for PostgreSQL?**
`depends_on` alone only waits for the container to start, not for the database to accept connections. A health check (`pg_isready`) makes `web` wait until PostgreSQL is ready, so `migrate` does not fail.

### Testing and quality

**47. How did you test the project?**
With Django's `APITestCase`: 'force_authenticate' for different users, a helper that builds future time slots, and tests for overlap rules, permissions, validation, availability, throttling, emails and the scheduled task. One test creates overlapping rows directly in the ORM to prove the database constraint works without the serializer.

**48. Why clear the cache in `setUp`?**
Throttle counters live in the cache and survive between tests. Without `cache.clear()`, later tests would randomly get `429`.

**49. Postman versus automated tests?**
Postman is for exploring and demos. Automated tests are repeatable, fast, run on a clean database, and can run in CI on every push. Both are useful, but only tests protect against regressions.

### Scaling and improvements

**50. How would you scale this?**
Run several Gunicorn workers behind a reverse proxy, use Redis as the shared cache for throttling, add database indexes (already on resource and times), use connection pooling, add more Celery workers, and cache availability results.

**51. What would you improve next?**
Per-resource opening hours, recurring bookings created atomically, payments with Stripe, a token blacklist, GitHub Actions CI, production settings (Gunicorn, `DEBUG=False`, `ALLOWED_HOSTS`), and monitoring for failed Celery tasks.

**52. What are the weaknesses of the current design?**
Global opening hours, editable confirmed bookings, a strict global throttle, a development server in Docker, and a per-process throttle cache. I know about them and can explain how to fix each.

---

## License

