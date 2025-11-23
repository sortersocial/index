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

## Database (dbmate)

```bash
brew install dbmate                         # Install dbmate on macOS
sudo curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/latest/download/dbmate-linux-amd64 && sudo chmod +x /usr/local/bin/dbmate  # Install dbmate on Linux
scoop install dbmate                        # Install dbmate on Windows
export DATABASE_URL="sqlite:///path/to/database.db"     # Set database connection string
dbmate new create_table_name                # Create a new migration file
dbmate up                                   # Run all pending migrations
dbmate down                                 # Rollback the last migration
dbmate status                               # Show migration status
dbmate dump                                 # Dump the database schema
dbmate drop                                 # Drop the database
dbmate create                               # Create the database
```

## Running Applications

```bash
uvicorn src.main:app --reload               # Start FastAPI server with hot reload
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload  # Start server with custom host/port
python src/rank.py 10                       # Run rank centrality with 10 items
python src/rank.py 20 50                    # Run with 20 items and 50 extra comparisons
python src/rank.py 15 30 5                  # Run 5 iterations with 15 items and 30 extra comparisons
```

## Deployment (fly.io)

```bash
fly deploy                                  # Deploy the application
fly logs                                    # View application logs
fly ssh console                             # SSH into the running instance
fly status                                  # Check application status
fly scale count 1                           # Scale machines
fly secrets set DATABASE_URL="sqlite:///path/to/database.db"  # Set environment secrets
fly certs add index.sorter.social           # Add custom domain certificate
fly open                                    # Open the deployed app in browser
```

## Development Tools

```bash
black src/                                  # Format Python code
ruff check src/                             # Lint Python code
mypy src/                                   # Type check Python code
```
