# AGENTS.md

## Setup

```bash
uv sync                                    # Install dependencies using uv
source .venv/bin/activate                  # Activate virtual environment (macOS/Linux)
.venv\Scripts\activate                     # Activate virtual environment (Windows)
python3 -m venv .venv                      # Create virtual environment (pip alternative)
pip install -e .                           # Install dependencies using pip
cp .env.example .env                        # Create environment file from template
```

## Running Applications

```bash
uv run uvicorn src.main:app --reload        # Start FastAPI server with hot reload (using uv)
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload  # Start server with custom host/port
uv run python src/rank.py 10                # Run rank centrality with 10 items
uv run python src/rank.py 20 50             # Run with 20 items and 50 extra comparisons
uv run python src/rank.py 15 30 5           # Run 5 iterations with 15 items and 30 extra comparisons
```

## Deployment (fly.io)

```bash
fly deploy                                  # Deploy the application
fly logs                                    # View application logs
fly ssh console                             # SSH into the running instance
fly status                                  # Check application status
fly scale count 1                           # Scale machines
fly certs add index.sorter.social           # Add custom domain certificate
fly open                                    # Open the deployed app in browser
```

## Development Tools

```bash
black src/                                  # Format Python code
ruff check src/                             # Lint Python code
mypy src/                                   # Type check Python code
```
