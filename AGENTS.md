# AGENTS.md

## Project Overview

An email sorting application with the following components:

1. **FastAPI Web Application** - Web server with Postmark webhook integration for receiving emails
2. **Rank Centrality Algorithm** - Statistical algorithm for analyzing pairwise comparisons
3. **Database Layer** - PostgreSQL with dbmate migrations for data persistence

**Deployed at**: https://index.sorter.social (via fly.io in Ashburn, VA)
**Email**: Receives emails at anything@mail.sorter.social via Postmark webhooks

## Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [dbmate](https://github.com/amacneil/dbmate) for database migrations
- [fly.io CLI](https://fly.io/docs/hands-on/install-flyctl/) for deployment (optional)

## Setup

### Option 1: Using uv (Recommended)

```bash
# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

### Option 2: Using pip

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -e .
```

## Environment Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Required environment variables:
- `DATABASE_URL` - PostgreSQL connection string (Neon Postgres recommended)
- `POSTMARK_WEBHOOK_SECRET` - Optional secret for webhook verification

## Database Setup with dbmate

### Installing dbmate

```bash
# macOS
brew install dbmate

# Linux
sudo curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/latest/download/dbmate-linux-amd64
sudo chmod +x /usr/local/bin/dbmate

# Windows
scoop install dbmate
```

### Database Commands

```bash
# Set your database URL
export DATABASE_URL="postgresql://user:password@host:5432/database"

# Create a new migration
dbmate new create_table_name

# Run all pending migrations
dbmate up

# Rollback the last migration
dbmate down

# Show migration status
dbmate status

# Dump the database schema
dbmate dump

# Drop the database
dbmate drop

# Create the database
dbmate create
```

### Migration File Structure

Migrations are stored in `db/migrations/` with the format:
```
YYYYMMDDHHMMSS_migration_name.sql
```

Each migration file contains:
```sql
-- migrate:up
-- SQL statements for applying the migration

-- migrate:down
-- SQL statements for rolling back the migration
```

## Running the Applications

### 1. FastAPI Web Server (Local Development)

```bash
# Start the server with hot reload
uvicorn src.main:app --reload

# Or with custom host/port
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at:
- http://localhost:8000 - Main page
- http://localhost:8000/docs - API documentation (Swagger UI)
- http://localhost:8000/redoc - API documentation (ReDoc)
- http://localhost:8000/health - Health check endpoint
- http://localhost:8000/webhook/postmark - Postmark inbound webhook

### 2. Rank Centrality Script

This script implements a rank centrality algorithm for analyzing pairwise comparisons.

```bash
# Basic usage
python src/rank.py <num_items> [extra_comparisons] [iterations]

# Examples:
python src/rank.py 10                    # Test with 10 items
python src/rank.py 20 50                 # Test with 20 items and 50 extra comparisons
python src/rank.py 15 30 5               # Run 5 iterations with 15 items and 30 extra comparisons
```

**Parameters:**
- `num_items` (required) - Number of items to rank
- `extra_comparisons` (optional, default: 0) - Additional random comparisons beyond the spanning tree
- `iterations` (optional, default: 1) - Number of test iterations to run

**Output:**
The script outputs ranked items with their scores and scaled scores. Items are ranked from highest to lowest preference.

## Deployment (fly.io)

The application is deployed to fly.io with auto-stop/start (scale-to-zero).

```bash
# Deploy the application
fly deploy

# View logs
fly logs

# SSH into the running instance
fly ssh console

# Check app status
fly status

# Scale machines
fly scale count 1

# Set secrets (for DATABASE_URL, etc.)
fly secrets set DATABASE_URL="postgresql://..."

# Add custom domain
fly certs add index.sorter.social

# Open the deployed app
fly open
```

### Running Migrations on fly.io

```bash
# SSH into the fly.io machine
fly ssh console

# Run migrations
dbmate up
```

Or create a release command in `fly.toml` to run migrations automatically on deploy.

## Project Structure

```
.
├── src/
│   ├── __init__.py
│   ├── main.py           # FastAPI web application with webhook endpoints
│   ├── rank.py           # Rank centrality algorithm
│   └── templates/
│       └── index.html    # HTML template
├── db/
│   ├── migrations/       # dbmate migration files
│   └── schema.sql        # Auto-generated schema (managed by dbmate)
├── Dockerfile            # Container build configuration
├── fly.toml              # fly.io deployment configuration
├── .dockerignore         # Files to exclude from Docker build
├── .env.example          # Environment variable template
├── pyproject.toml        # Project configuration and dependencies
├── uv.lock               # Locked dependency versions
├── ideas/                # Design notes and planning
└── AGENTS.md             # This file
```

## Development Tools

The project is configured with:

- **Black** - Code formatter (line length: 88)
- **Ruff** - Fast Python linter
- **Mypy** - Static type checker

Run code quality checks:

```bash
# Format code
black src/

# Lint code
ruff check src/

# Type check
mypy src/
```

## Dependencies

Core dependencies:
- `fastapi` - Modern web framework for building APIs
- `jinja2` - Template engine for HTML rendering
- `numpy` - Numerical computing library for rank centrality
- `scipy` - Scientific computing library for matrix operations
- `uvicorn` - ASGI server for running FastAPI

Database dependencies:
- `sqlalchemy` - SQL toolkit and ORM
- `asyncpg` - Async PostgreSQL driver
- `psycopg2-binary` - Sync PostgreSQL driver

Email dependencies:
- `postmarker` - Python client for Postmark API (sending emails)

All dependencies are specified in `pyproject.toml` and managed by `uv`.

## API Endpoints

- `GET /` - Main HTML page
- `GET /health` - Health check for monitoring
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)
- `POST /webhook/postmark` - Postmark inbound email webhook

## Postmark Integration

### Inbound Email (Receiving)

The application receives emails via Postmark webhooks:

1. **Inbound Domain**: mail.sorter.social
2. **Webhook URL**: https://index.sorter.social/webhook/postmark
3. **Email Format**: anything@mail.sorter.social
4. **Payload**: Postmark sends JSON with email content, including:
   - From/To addresses
   - Subject and message body (text/HTML)
   - Headers and attachments
   - Message ID and timestamp

See src/main.py:51 for the webhook handler and Pydantic schema.

### Outbound Email (Sending)

The application can send emails and reply to received emails:

1. **Sender Domain**: mail.sorter.social (must be verified in Postmark)
2. **Threading Support**: Replies maintain email thread using In-Reply-To and References headers
3. **API**: Uses `postmarker` Python client
4. **Configuration**: Requires `POSTMARK_SERVER_TOKEN` environment variable

See `src/email_utils.py` for email sending utilities and `POSTMARK_OUTBOUND_SETUP.md` for detailed setup instructions.

## Database

**Recommended**: Neon Postgres (scale-to-zero, generous free tier)
- Region: us-east-1 or us-east-2 (low latency to fly.io iad region)
- Connection pooling: Built-in
- Autoscaling: Automatic with scale-to-zero

Alternative options:
- Supabase (free tier with PostgreSQL)
- Turso (SQLite with edge replication)

## Notes

- The application uses scale-to-zero on both fly.io and Neon for cost efficiency
- Postmark handles email receiving; the app processes via webhooks
- The rank centrality algorithm can be used for email sorting/prioritization
- dbmate provides language-agnostic, version-controlled database migrations
- DNS is managed via Cloudflare for sorter.social domain
